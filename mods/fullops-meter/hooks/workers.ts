import type { Progress, Seen, Worker } from '../types'

/** How long a finished dispatch stays on the list, so a result is seen before it leaves. */
export const KEEP_FINISHED_MS = 10 * 60_000

type Phase = Worker['phase']

/** Orca's worker and dispatch state, as `orca orchestration worker-list` reports them. */
export const phaseOf = (workerState: string, dispatchStatus: string): Phase => {
  if (workerState === 'stopped') return 'stopped'
  if (workerState === 'failed' || dispatchStatus === 'failed') return 'failed'
  if (workerState === 'succeeded' && dispatchStatus === 'completed') return 'done'
  // Anything else is still going: a state this mod does not know yet reads as running, not as finished.
  return 'active'
}

/** The task key a spec declares as `Task key: X`; empty when it declares none. */
export const declaredKey = (spec: string): string =>
  /\bTask\s+key\s*[:=]?\s*([A-Za-z0-9][A-Za-z0-9._-]*)/i.exec(spec)?.[1]?.replace(/\.$/, '') ?? ''

/** The task key a dispatch's spec carries: the declared one, else the spec's first word. */
export const keyOf = (spec: string): string => declaredKey(spec) || (/^\s*([A-Za-z0-9][A-Za-z0-9._-]*)/.exec(spec)?.[1] ?? '')

export type Row = {
  dispatchId: string
  taskId: string
  phase: Phase
  detail: string
  /** The worker's worktree path, as Orca reports it. */
  workspace: string
  activity: string
  isLive: boolean
  needsAction: boolean
}

/** A JSON object's fields; `{}` for anything else, arrays included. */
export const asRecord = (value: unknown): Record<string, unknown> =>
  typeof value === 'object' && value !== null && !Array.isArray(value) ? (value as Record<string, unknown>) : {}

export const text = (value: unknown): string => (typeof value === 'string' ? value : '')

/** The Orca run this coordinator is bound to, from `orca orchestration run-current --json`; null when none. */
export const parseRunId = (stdout: string): string | null => {
  let parsed: unknown
  try {
    parsed = JSON.parse(stdout)
  } catch {
    return null
  }
  const run = asRecord(asRecord(asRecord(parsed).result).run)
  const id = text(run.id) || text(run.runId)
  return id === '' ? null : id
}

/** The rows of `orca orchestration worker-list --json`; empty for anything that is not that. */
export const parseRows = (stdout: string): Row[] => {
  let parsed: unknown
  try {
    parsed = JSON.parse(stdout)
  } catch {
    return []
  }
  const workers = asRecord(asRecord(asRecord(parsed).result)).workers
  if (!Array.isArray(workers)) return []
  return workers.map(item => {
    const worker = asRecord(item)
    const projection = asRecord(worker.projection)
    const stage = asRecord(projection.stage)
    return {
      dispatchId: text(worker.dispatchId),
      taskId: text(worker.taskId),
      phase: phaseOf(text(worker.workerState), text(worker.dispatchStatus)),
      detail: text(stage.detail),
      workspace: text(asRecord(projection.workspace).id),
      activity: text(stage.activity),
      isLive: text(asRecord(projection.liveness).verdict) !== 'dead',
      needsAction: asRecord(projection.attention).requiresAction === true,
    }
  })
}

/** Task id to task key, from `orca orchestration task-list --json`. */
export const parseKeys = (stdout: string): Record<string, string> => {
  let parsed: unknown
  try {
    parsed = JSON.parse(stdout)
  } catch {
    return {}
  }
  const tasks = asRecord(asRecord(parsed).result).tasks
  const keys: Record<string, string> = {}
  if (Array.isArray(tasks)) {
    for (const item of tasks) {
      const task = asRecord(item)
      keys[text(task.id)] = keyOf(text(task.spec))
    }
  }
  return keys
}

/** `C:/.../repo/dev` or `<repoId>::C:/.../repo/dev` to `dev`. */
export const roleOf = (workspace: string): string => {
  const path = workspace.split('::').pop() ?? ''
  const name = path.replace(/[\\/]+$/, '').split(/[\\/]/).pop() ?? ''
  // review.py snapshots a reviewer's checkout as `.fullops-review-<id>`.
  return name.startsWith('.fullops-review-') ? 'reviewer' : name
}

/**
 * Merges a fresh listing into what was seen before and says which workers to show.
 * Dispatches that were already finished when the mod first looked are old news and never show;
 * one that finishes after that shows for KEEP_FINISHED_MS.
 */
export const reconcile = (
  seen: Seen,
  rows: readonly Row[],
  keys: Readonly<Record<string, string>>,
  now: number,
  isFirst: boolean,
): { seen: Seen; workers: Worker[] } => {
  // Only the dispatches in this listing are kept, so `seen` does not grow across runs.
  const next: Seen = {}
  const workers: Worker[] = []
  for (const row of rows) {
    const before = seen[row.dispatchId]
    const isBaseline = before?.isBaseline ?? (isFirst && row.phase !== 'active')
    const since = before !== undefined && before.phase === row.phase ? before.since : now
    next[row.dispatchId] = { phase: row.phase, since, isBaseline }
    const isShown = row.phase === 'active' || (!isBaseline && now - since <= KEEP_FINISHED_MS)
    if (isShown) {
      workers.push({
        dispatchId: row.dispatchId,
        role: roleOf(row.workspace),
        key: keys[row.taskId] ?? '',
        phase: row.phase,
        detail: row.detail,
        since,
        activity: row.activity,
        isLive: row.isLive,
        needsAction: row.needsAction,
        stage: row.phase === 'done' ? STAGES.length : 0,
        progress: null,
      })
    }
  }
  // Active first, then the most recent change.
  workers.sort((a, b) => Number(b.phase === 'active') - Number(a.phase === 'active') || b.since - a.since)
  return { seen: next, workers }
}

const STEPS = 6
const SAID_CHARS = 120

/** One tool call as a short step: the tool, then what it touched. */
export const stepOf = (name: string, input: Record<string, unknown>): string => {
  const path = text(input.file_path) || text(input.path) || text(input.notebook_path)
  if (path !== '') return `${name} ${path.split(/[\\/]/).pop()}`
  const what = text(input.description) || text(input.command).split('\n')[0] || text(input.pattern) || text(input.prompt).split('\n')[0]
  return what === undefined || what === '' ? name : `${name}: ${what.length > 60 ? `${what.slice(0, 59)}…` : what}`
}

/** A worker's latest words and tool calls, from `orca orchestration worker-read --source transcript --json`. */
export const parseProgress = (stdout: string): Progress | null => {
  let parsed: unknown
  try {
    parsed = JSON.parse(stdout)
  } catch {
    return null
  }
  const messages = asRecord(asRecord(asRecord(parsed).result).transcript).messages
  if (!Array.isArray(messages)) return null
  let said = ''
  let at = 0
  const steps: string[] = []
  for (const item of messages) {
    const message = asRecord(item)
    if (typeof message.timestamp === 'number') at = Math.max(at, message.timestamp)
    if (message.role !== 'assistant' || !Array.isArray(message.blocks)) continue
    for (const raw of message.blocks) {
      const block = asRecord(raw)
      if (block.type === 'text' && text(block.text).trim() !== '') said = text(block.text).trim().split(/\r?\n/)[0] ?? ''
      if (block.type === 'tool-call') steps.push(stepOf(text(block.name), asRecord(block.input)))
    }
  }
  return {
    said: said.length > SAID_CHARS ? `${said.slice(0, SAID_CHARS - 1)}…` : said,
    steps: steps.slice(-STEPS),
    at,
  }
}

/** A worker's main steps, in order; `done` follows the last. */
export const STAGES = ['explore', 'build', 'verify', 'report'] as const

/** The stage one tool call belongs to, by what it does. */
export const stageOfStep = (step: string): number => {
  if (/worker_done|work\.py finish|orca_wait|orchestration (send|reply)|archive|completion report/i.test(step)) return 3
  if (/^Bash\b/.test(step) && /\b(tests?|lint|gate|checks?|verify|validate|pytest|tsc|make)\b/i.test(step)) return 2
  if (/^(Edit|Write|MultiEdit|NotebookEdit)\b/.test(step)) return 1
  return 0
}

/** The furthest stage a worker reached: it never goes back, as a worker re-reads files while it tests. */
export const stageOf = (steps: readonly string[], before: number): number =>
  steps.reduce((furthest, step) => Math.max(furthest, stageOfStep(step)), before)
