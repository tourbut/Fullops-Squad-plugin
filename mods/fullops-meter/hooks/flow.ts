import type { FlowTask, Review, Worker } from '../types'
import { ago } from './meter'
import { STAGES, parseRecord, text } from './workers'

/** The task lifecycle of docs/flow-graph.md, in the node ids flow_state.py writes. */
export const NODES = ['intent', 'design', 'assign', 'build', 'report', 'review', 'merge', 'qa', 'done'] as const

/** A merged or done task stays on the tab this long, then leaves. */
export const KEEP_FINISHED_MS = 30 * 60_000

/** Round suffixes (`-FIX`, `-R2`, ...): a round or role-split key belongs to the task before it, as in harness_gate.base_key. */
const ROUND = /-(?:FIX|RECHECK|RETEST|LOWS|R\d+)(?=-|$)/i

export const baseKey = (key: string): string => {
  const match = ROUND.exec(key)
  return match !== null && match.index > 0 ? key.slice(0, match.index) : key
}

const REVIEW = /-REVIEW(?:-R\d+)?$/i

/** The task a key counts toward: a review key (`K-DEV-REVIEW-R2`) is task K's review, as in flow_state.task_of, which files it there. */
export const taskOf = (key: string, roles: readonly string[]): string => {
  const match = REVIEW.exec(key)
  if (match === null || match.index === 0) return baseKey(key)
  const head = key.slice(0, match.index)
  const role = roles.find(one => head.toUpperCase().endsWith(`-${one.toUpperCase()}`) && head.length > one.length + 1)
  return baseKey(role === undefined ? head : head.slice(0, -role.length - 1))
}

/** One `fullops-flow/<key>.json` record, or null when it is not one. */
export const parseFlow = (source: string): FlowTask | null => {
  const record = parseRecord(source)
  const key = text(record.key)
  const node = NODES.findIndex(name => name === record.node)
  if (key === '' || node === -1) return null
  const updated = Date.parse(text(record.updated))
  return {
    key,
    node,
    rounds: typeof record.rounds === 'number' ? record.rounds : 0,
    budget: typeof record.budget === 'number' ? record.budget : 2,
    updated: Number.isNaN(updated) ? 0 : updated,
  }
}

const isFinished = (task: FlowTask): boolean => task.node >= NODES.indexOf('merge')

/** Tasks under way, newest first, then the ones merged or done within KEEP_FINISHED_MS. */
export const visibleFlow = (tasks: readonly FlowTask[], now: number): FlowTask[] =>
  tasks
    .filter(task => !isFinished(task) || now - task.updated < KEEP_FINISHED_MS)
    .sort((a, b) => Number(isFinished(a)) - Number(isFinished(b)) || b.updated - a.updated)

export type Flag = { text: string; tone: 'warning' | 'error' }

/** The longest task key the row keeps, so the rail and the time still fit the 56-column pane. */
const KEY_COLUMNS = 24

export type FlowRow = {
  /** The task key, cut to KEY_COLUMNS. */
  key: string
  /** One mark per node: passed, current or ahead. */
  rail: ('passed' | 'current' | 'ahead')[]
  label: string
  when: string
  /** What holds the task, in words and colour together. */
  flags: Flag[]
  /** The assigned worker's inner stages, `dev ✔ explore ◉ build ○ verify ○ report`; empty when no worker is out for it. */
  inner: string
}

/** One task as the Flow tab draws it: the outer node rail, what holds it, and its worker's inner stages under it. */
export const flowRow = (task: FlowTask, reviews: readonly Review[], workers: readonly Worker[], roles: readonly string[], now: number): FlowRow => {
  const flags: Flag[] = []
  if (task.rounds > task.budget) flags.push({ text: `⚠ rounds ${task.rounds}/${task.budget}`, tone: 'warning' })
  // A task can hold several reviews and workers (a round, a review key), so any one of them can hold it.
  const open = reviews.filter(one => taskOf(one.key, roles) === task.key && one.state === 'recorded' && one.unresolved > 0)
  const worst = ['critical', 'high'].find(severity => open.some(one => one.worst === severity))
  if (worst !== undefined) flags.push({ text: `✖ review blocked · ${worst}`, tone: 'error' })
  const active = workers.filter(one => one.phase === 'active' && taskOf(one.key, roles) === task.key)
  if (active.some(one => one.needsAction)) flags.push({ text: '⚠ needs you', tone: 'warning' })
  if (active.some(one => !one.isLive)) flags.push({ text: '✖ agent gone', tone: 'error' })
  const worker = active[0]
  const inner =
    worker === undefined
      ? ''
      : `${worker.role} ${STAGES.map((stage, at) => `${at < worker.stage ? '✔' : at === worker.stage ? '◉' : '○'} ${stage}`).join(' ')}`
  return {
    key: task.key.length > KEY_COLUMNS ? `${task.key.slice(0, KEY_COLUMNS - 1)}…` : task.key,
    rail: NODES.map((_, at) => (at < task.node ? 'passed' : at === task.node ? 'current' : 'ahead')),
    label: NODES[task.node] ?? '',
    when: task.updated === 0 ? '' : `${ago(now - task.updated)} ago`,
    flags,
    inner,
  }
}
