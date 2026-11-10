import { atom, read, update } from 'claude-code'
import type { EngineInterface, Register, RenderElement, Timer } from 'claude-code'

import type { Decision, FlowTask, HookRun, IssueMode, Meter, Review, Sample, Tab, Ttl } from '../types'
import { accountOf, adviseCache, decideTtl, keepSamples, observeTtl, promptTokens } from './cache'
import type { Account, Policy, TtlInputs } from './cache'
import { HOOK_EVENTS, hookLines, hookOutcome, recordHookRun } from './hook-runs'
import { MARKERS, branchOf, cardOf, checkoutRole, commonDirOf, decisionLines, issueModeLine, issueModeState, parseConfig, parseDecision, parseIssueMode, reviewLine, sortReviews, spinnerText, summarizeReview } from './fullops'
import { flowRow, parseFlow, visibleFlow } from './flow'
import { bandLine, contextText, historyText, modelName, queuedText, statusLine, workerBlock, workerLine } from './meter'
import type { CardsProps } from './worker-cards'
import { STAGES, asRecord, noticesOf, parseProgress, parseRows, parseRunId, parseTasks, reconcile, stageOf, stageOfRecords, text } from './workers'

const meterAtom = atom({ plugin: 'fullops-meter', key: 'meter' } as const, null)
const nowAtom = atom({ plugin: 'fullops-meter', key: 'now' } as const, 0)
const isHiddenAtom = atom({ plugin: 'fullops-meter', key: 'isHidden' } as const, false)
const seenAtom = atom({ plugin: 'fullops-meter', key: 'seen' } as const, {})
const fullopsAtom = atom({ plugin: 'fullops-meter', key: 'fullops' } as const, null)
const tabAtom = atom({ plugin: 'fullops-meter', key: 'tab' } as const, 'workers')
const hooksAtom = atom({ plugin: 'fullops-meter', key: 'hooks' } as const, [])

const KEEP_SAMPLES = 50
const TICK_MS = 1000
const POLL_MS = 15_000
const COMMAND = 'meter'
const FULLOPS_COMMAND = 'fullops'
const PANE = 'fullops'
const CONFIG = '.fullops-squad/fullops.json'
const REVIEWS = '.fullops-squad/docs/evaluations/qa-reports'
const KEEP_REVIEWS = 8
/** Where decision.py keeps its records, under the git folder all checkouts share. */
const DECISIONS = 'fullops-decisions'
/** The issue auto mode summary issue_mode.py writes, under the same folder. */
const ISSUES = 'fullops-issues/status.json'
/** Where flow_state.py keeps each task's flow state, in the same shared git folder. */
const FLOW = 'fullops-flow'
/** How long a checkout's git folder locations are trusted: they move only when a worktree is moved or added again. */
const LOCATION_MS = 60_000
/** Transcript rows read per active worker: enough to reach its last words past a run of tool calls. */
const PROGRESS_ROWS = 30
/** The dock width the pane asks for; the person can still drag it. */
const PANE_COLUMNS = 56
const TABS: readonly { tab: Tab; label: string; hotkey: string }[] = [
  { tab: 'workers', label: 'Workers', hotkey: 'w' },
  { tab: 'reviews', label: 'Reviews', hotkey: 'r' },
  { tab: 'flow', label: 'Flow', hotkey: 'f' },
]
/** A prompt this small is not worth a notice when its cache lapses. */
const NOTICE_MIN_TOKENS = 20_000

/** Where a checkout keeps its git files. */
type Location = { gitDir: string; commonDir: string; readAt: number }

/** A record file as last read. */
type Kept<T> = { size: number; mtimeMs: number; value: T | null }

/** What the hooks share. Plain values, so a hook can hand it to a helper along with `$`. */
type Shared = {
  policy: Policy
  option: unknown
  showBand: boolean
  warnPercent: number
  ttl: Ttl
  ttlSource: string
  /** A lifetime the request timing proved; it beats every rule. */
  observed: Ttl | undefined
  /** The environment and settings the lifetime rules read, once a load. */
  ttlInputs: Omit<TtlInputs, 'option' | 'account'>
  /** The account kind from the last usage reading. */
  account: Account
  /** True while a poll of Orca runs, so a slow Orca does not pile polls up. */
  isPolling: boolean
  /** The timers this load started. */
  timers: Timer[]
  /** undefined: not read yet; null: auto-compaction is off. */
  compactAt: number | null | undefined
  /** When the last worker poll ran, so a stall is told of once, as it crosses the limit; 0 before any, which also marks the first poll. */
  lastPollAt: number
  isFullOps: boolean
  /** Each checkout read so far, by its root. */
  locations: Record<string, Location>
  decisionFiles: Map<string, Kept<Decision>>
  flowFiles: Map<string, Kept<FlowTask>>
  lastStatus: string
  hasWarnedContext: boolean
  /** The `startedAt` of the cache entry the "about to lapse" notice was shown for. */
  warnedEntry: number
}

const blank = (now: number, shared: Shared): Meter => ({
  at: now,
  context: { tokens: null, window: null, percent: null, compactAt: null },
  samples: [],
  ttl: shared.ttl,
  ttlSource: shared.ttlSource,
  model: null,
  effort: null,
  costUsd: null,
  fiveHour: null,
  workers: null,
})

/** Writes a change to the meter, which redraws the hint line, then the notices. */
async function commit($: EngineInterface, shared: Shared, patch: (meter: Meter) => Meter): Promise<void> {
  const now = await $.clock.now()
  // The patch runs on the stored value inside the update, so concurrent commits do not drop each other's writes.
  await update($, meterAtom, stored => patch(stored ?? blank(now, shared)))
  await update($, nowAtom, () => now)
  const meter = (await read($, meterAtom)) ?? blank(now, shared)

  shared.lastStatus = statusLine(meter, now)

  const percent = meter.context.percent
  if (percent !== null) {
    if (percent >= shared.warnPercent && !shared.hasWarnedContext) {
      shared.hasWarnedContext = true
      $.ui.toast(`Context is ${percent}% full. Compact or prepare a new session.`)
    } else if (percent < shared.warnPercent - 5) {
      shared.hasWarnedContext = false
    }
  }
}

/** The environment and settings the lifetime rules read: read once a load, as they do not change mid-session. */
async function readTtlInputs($: EngineInterface, shared: Shared): Promise<void> {
  const [force5m, ttlVariable, enable1h] = await Promise.all([
    $.env.get('FORCE_PROMPT_CACHING_5M').catch(() => undefined),
    $.env.get('CLAUDE_CODE_PROMPT_CACHE_TTL').catch(() => undefined),
    $.env.get('ENABLE_PROMPT_CACHING_1H').catch(() => undefined),
  ])
  shared.ttlInputs = { force5m, ttlVariable, enable1h, setting: await readSetting($) }
}

/** The lifetime to expect: the rules, then what the request timing proved. No I/O, so it can run every request. */
function chooseTtl(shared: Shared): void {
  const choice = decideTtl({ option: shared.option, ...shared.ttlInputs, account: shared.account })
  shared.ttl = shared.observed ?? choice.ttl
  shared.ttlSource = shared.observed === undefined ? choice.source : `observed from request gaps (${choice.source}: ${choice.ttl})`
}

/** `promptCacheTtl` from the first settings file that sets it: local, project, then user. */
async function readSetting($: EngineInterface): Promise<unknown> {
  const [configDir, home, profile] = await Promise.all([
    $.env.get('CLAUDE_CONFIG_DIR').catch(() => undefined),
    $.env.get('HOME').catch(() => undefined),
    $.env.get('USERPROFILE').catch(() => undefined),
  ])
  // Native Windows often has no HOME; CLAUDE_CONFIG_DIR moves the user folder altogether.
  const userDir = configDir || ((home || profile) && `${home || profile}/.claude`)
  const cwd = await $.session.cwd().catch(() => undefined)
  const files = [cwd && `${cwd}/.claude/settings.local.json`, cwd && `${cwd}/.claude/settings.json`, userDir && `${userDir}/settings.json`]
  for (const file of files) {
    if (!file) continue
    try {
      const value: unknown = JSON.parse(await $.fs.read(file)).promptCacheTtl
      if (value === '5m' || value === '1h') return value
    } catch {
      // missing or unreadable: the next file
    }
  }
  return undefined
}

/** After each main-loop turn: the context window, the cost and the rate limit. */
async function readContext($: EngineInterface, shared: Shared): Promise<void> {
  // No reading (no response yet, an engine error) leaves the meter as it was; the hooks calling this must go on.
  const reading = await $.session.usage().catch(() => undefined)
  if (reading === undefined) return
  const account = accountOf(reading.rateLimits)
  // A lifetime proven under the old account kind (plan usage run out, or restored) no longer holds.
  if (account !== shared.account) shared.observed = undefined
  shared.account = account
  chooseTtl(shared)
  // The compaction point is a local estimate and does not move within a session, so it is read once.
  if (shared.compactAt === undefined) {
    const full = await $.session.usage({ breakdown: 'summary' }).catch(() => undefined)
    shared.compactAt = full?.context.breakdown?.autoCompactThreshold ?? null
  }
  const model = await $.session.model().catch(() => null)
  await commit($, shared, meter => ({
    ...meter,
    model: model ?? meter.model,
    context: {
      tokens: reading.context.tokens ?? null,
      window: reading.context.window ?? null,
      percent: reading.context.percent ?? null,
      compactAt: shared.compactAt ?? null,
    },
    costUsd: reading.cost?.usd ?? null,
    fiveHour: reading.rateLimits.find(limit => limit.kind === 'five_hour')?.percentUsed ?? null,
  }))
}

/** One main-loop request finished: keep what the cache did with it. */
async function record(
  $: EngineInterface,
  shared: Shared,
  step: { model: string; effort?: string | number },
  startedAt: number,
  usage: { model: string; input_tokens: number; cache_read_input_tokens: number; cache_creation_input_tokens: number },
): Promise<void> {
  const sample: Sample = {
    model: usage.model || step.model,
    startedAt,
    read: usage.cache_read_input_tokens,
    write: usage.cache_creation_input_tokens,
    fresh: usage.input_tokens,
  }
  const before = (await read($, meterAtom))?.samples ?? []
  shared.observed = observeTtl(before[before.length - 1], sample, shared.observed)
  chooseTtl(shared)
  await commit($, shared, meter => ({
    ...meter,
    samples: keepSamples(meter.samples, sample, KEEP_SAMPLES),
    ttl: shared.ttl,
    ttlSource: shared.ttlSource,
    model: sample.model,
    effort: step.effort === undefined ? null : String(step.effort),
  }))
}

/** Orca 1.4.246+ prints a concise view without the fields read here unless --full; an older Orca rejects the flag. */
// shortcut: an Orca without --full is asked twice per call; keep the answer in Shared if that ever costs.
const orca = async ($: EngineInterface, argv: readonly string[], timeoutMs: number) => {
  const full = await $.process.run(['orca', 'orchestration', ...argv, '--full', '--json'], { timeoutMs })
  return full.exitCode === 0 ? full : $.process.run(['orca', 'orchestration', ...argv, '--json'], { timeoutMs })
}

/** The workers the coordinator's Orca run has: Orca's own listing, nothing is sent anywhere. */
async function pollWorkers($: EngineInterface, shared: Shared): Promise<void> {
  // A mod's child process may not carry Orca's launch token, and without it Orca cannot tell which terminal asks:
  // name this session's terminal outright (Orca still checks it against the token when one is there).
  const handle = await $.env.get('ORCA_TERMINAL_HANDLE')
  const from = handle === undefined || handle === '' ? [] : ['--from', handle]
  const run = await orca($, ['run-current', ...from], 15_000).catch(() => undefined)
  const runId = run === undefined || run.exitCode !== 0 ? null : parseRunId(run.stdout)
  if (runId === null) {
    await commit($, shared, meter => ({ ...meter, workers: null }))
    return
  }
  const [list, tasks] = await Promise.all([
    orca($, ['worker-list', '--run', runId, '--limit', '100'], 20_000),
    // --brief caps each spec at 160 characters: the key is declared at its start.
    orca($, ['task-list', '--run', runId, '--brief'], 20_000),
  ]).catch(() => [undefined, undefined] as const)
  if (list === undefined || tasks === undefined || list.exitCode !== 0) return

  const now = await $.clock.now()
  // A failed listing keeps the tasks already known, so the cards do not lose their task names for a poll.
  const known = await read($, fullopsAtom)
  const rows = parseRows(list.stdout)
  const sent = new Set(rows.map(row => row.taskId))
  const { keys, queued } = tasks.exitCode === 0 ? parseTasks(tasks.stdout, sent) : { keys: known?.keys ?? {}, queued: known?.queued ?? [] }
  const seen = await read($, seenAtom)
  const merged = reconcile(seen, rows, keys, now, shared.lastPollAt === 0)
  await update($, seenAtom, () => merged.seen)
  await update($, fullopsAtom, before => (before === null ? null : { ...before, keys, queued }))
  const before = (await read($, meterAtom))?.workers ?? []
  const workers = await Promise.all(
    merged.workers.map(async worker => {
      const old = before.find(one => one.dispatchId === worker.dispatchId)
      const kept = old?.progress ?? null
      // Workers kept from an older load carry no stage.
      const reached = Math.max(worker.stage, old?.stage ?? 0)
      if (worker.phase !== 'active') return { ...worker, stage: reached, stageAt: old?.stageAt ?? worker.since, progress: kept }
      const workspace = rows.find(row => row.dispatchId === worker.dispatchId)?.workspace ?? ''
      // shortcut: `since` is when this mod first saw the dispatch, so records a worker wrote before a reload
      // or a late install are missed and the word rules stand in; carry the dispatch time from Orca to do better.
      const [out, recorded] = await Promise.all([
        $.process
          .run(['orca', 'orchestration', 'worker-read', '--dispatch', worker.dispatchId, '--source', 'transcript', '--limit', String(PROGRESS_ROWS), '--json'], { timeoutMs: 15_000 })
          .catch(() => undefined),
        readRecordStage($, shared, workspace, worker.role, worker.since),
      ])
      const progress = (out?.exitCode === 0 ? parseProgress(out.stdout) : null) ?? kept
      const stage = stageOf(progress?.steps ?? [], Math.max(reached, recorded))
      // Workers kept from an older load carry no stageAt.
      const stageAt = stage > (old?.stage ?? 0) ? now : (old?.stageAt ?? worker.since)
      return { ...worker, stage, stageAt, progress }
    }),
  )
  await commit($, shared, meter => ({ ...meter, workers }))
  // The coordinator waits in the background, so what finished, asks for someone or stalls is told without the pane.
  for (const line of noticesOf(seen, workers, shared.lastPollAt, now)) $.ui.toast(line)
  shared.lastPollAt = now
}

/** One refresh of the repository and Orca state; skipped while the previous one still runs. */
async function poll($: EngineInterface, shared: Shared): Promise<void> {
  if (shared.isPolling) return
  shared.isPolling = true
  try {
    await readFullOps($, shared)
    await pollWorkers($, shared)
  } finally {
    shared.isPolling = false
  }
}

/** The git folder a checkout uses and the one all its checkouts share: a worktree's `.git` is a file naming its own, the main checkout's is the folder. */
async function locate($: EngineInterface, shared: Shared, root: string): Promise<Location> {
  const now = await $.clock.now()
  const known = shared.locations[root]
  if (known !== undefined && now - known.readAt < LOCATION_MS) return known
  const pointer = await $.fs.read(`${root}/.git`).catch(() => null)
  const named = pointer === null ? undefined : /^gitdir:\s*(.+)$/m.exec(pointer)?.[1]?.trim()
  const gitDir = named === undefined ? `${root}/.git` : /^([A-Za-z]:)?[\\/]/.test(named) ? named : `${root}/${named}`
  const commonDir = commonDirOf(gitDir, await $.fs.read(`${gitDir}/commondir`).catch(() => null))
  return (shared.locations[root] = { gitDir, commonDir, readAt: now })
}

/** The records in a shared git folder. Answered decisions and merged tasks pile up there, so a file is read again only when its listing changes. */
async function readRecords<T>(
  $: EngineInterface,
  kept: Map<string, Kept<T>>,
  folder: string,
  isRecord: (name: string) => boolean,
  parse: (source: string) => T | null,
): Promise<T[]> {
  const files = (await $.fs.list(folder).catch(() => [])).filter(entry => entry.kind === 'file' && isRecord(entry.name))
  const records: T[] = []
  for (const { name, size, mtimeMs } of files) {
    const path = `${folder}/${name}`
    let file = kept.get(path)
    if (file?.size !== size || file.mtimeMs !== mtimeMs) {
      const source = await $.fs.read(path).catch(() => null)
      // A failed read says nothing of the file, so the next refresh tries again.
      if (source === null) continue
      file = { size, mtimeMs, value: parse(source) }
      kept.set(path, file)
    }
    if (file.value !== null) records.push(file.value)
  }
  return records
}

/** The stage a worker's own checkout proves: the gate files lint.py leaves and the archived completion report. */
async function readRecordStage($: EngineInterface, shared: Shared, workspace: string, role: string, since: number): Promise<number> {
  const root = workspace.split('::').pop() ?? ''
  if (root === '') return 0
  const [gate, logs] = await Promise.all([
    $.fs.list(`${(await locate($, shared, root)).gitDir}/fullops-gate`).catch(() => []),
    $.fs.list(`${root}/.fullops-squad/handovers/logs`).catch(() => []),
  ])
  return stageOfRecords(gate, logs, role, since)
}

/** The newest review folders, each with what its files say. */
async function readReviews($: EngineInterface): Promise<Review[]> {
  const entries = await $.fs.list(REVIEWS).catch(() => [])
  // A listing gives a folder no time (mtimeMs 0), so each review folder is looked up on its own.
  const dated = await Promise.all(
    entries
      .filter(entry => entry.kind === 'dir' && entry.name.endsWith('-review'))
      .map(async entry => ({ name: entry.name, mtimeMs: (await $.fs.stat(`${REVIEWS}/${entry.name}`).catch(() => null))?.mtimeMs ?? 0 })),
  )
  const folders = dated.sort((a, b) => b.mtimeMs - a.mtimeMs).slice(0, KEEP_REVIEWS)
  return Promise.all(
    folders.map(async folder => {
      const dir = `${REVIEWS}/${folder.name}`
      const result = await $.fs.read(`${dir}/result.json`).catch(() => null)
      const names = new Set((await $.fs.list(dir).catch(() => [])).map(entry => entry.name))
      const marker = MARKERS.find(([file]) => names.has(file))?.[1] ?? null
      return summarizeReview(folder.name.slice(0, -'-review'.length), result, marker, folder.mtimeMs)
    }),
  )
}

/** The open decisions `decision.py` keeps in the folder every checkout shares, so a new session sees the old ones. */
async function readDecisions($: EngineInterface, shared: Shared, commonDir: string): Promise<Decision[]> {
  const decisions = await readRecords($, shared.decisionFiles, `${commonDir}/${DECISIONS}`, name => /^D\d+\.json$/.test(name), parseDecision)
  return decisions.sort((a, b) => a.askedAt - b.askedAt || a.id.localeCompare(b.id))
}

/** Each task's flow state the coordinator hook keeps in the folder every checkout shares. */
async function readFlow($: EngineInterface, shared: Shared, commonDir: string): Promise<FlowTask[]> {
  return readRecords($, shared.flowFiles, `${commonDir}/${FLOW}`, name => name.endsWith('.json'), parseFlow)
}

/** The issue auto mode summary `issue_mode.py` keeps beside its state, in the folder every checkout shares. */
async function readIssueMode($: EngineInterface, commonDir: string): Promise<IssueMode | null> {
  return parseIssueMode(await $.fs.read(`${commonDir}/${ISSUES}`).catch(() => ''))
}

/** The role, reviews, open decisions, task flow and issue mode, read from the repository's own files. */
async function readFullOps($: EngineInterface, shared: Shared): Promise<void> {
  const config = parseConfig(await $.fs.read(CONFIG).catch(() => ''))
  if (config === null) return
  const { gitDir, commonDir } = await locate($, shared, '.')
  // HEAD is read every time: a checkout can switch branch at any moment, and the role follows it.
  const role = checkoutRole(config, branchOf(await $.fs.read(`${gitDir}/HEAD`).catch(() => '')))
  const [reviews, decisions, flow, issues] = await Promise.all([readReviews($), readDecisions($, shared, commonDir), readFlow($, shared, commonDir), readIssueMode($, commonDir)])
  const roles = Object.keys(config.roles)
  await update($, fullopsAtom, before => ({ role, roles, reviews, decisions, flow, issues, keys: before?.keys ?? {}, queued: before?.queued ?? [] }))
}

/** Redraws the countdown and gives the "about to lapse" notice once per cache entry. */
async function tick($: EngineInterface, shared: Shared): Promise<void> {
  const meter = await read($, meterAtom)
  const latest = meter?.samples[meter.samples.length - 1]
  if (meter === null || latest === undefined) return

  const now = await $.clock.now()
  const advice = adviseCache(latest, meter.ttl, now, shared.policy)
  if (advice.state === 'soon' && shared.warnedEntry !== latest.startedAt && promptTokens(latest) >= NOTICE_MIN_TOKENS) {
    shared.warnedEntry = latest.startedAt
    $.ui.toast(
      advice.shouldCompact
        ? 'Prompt cache expires soon. Stepping away? Run /compact now: after expiry, the whole conversation is reread at full price.'
        : 'Prompt cache expires soon. Keep working to keep it; after expiry the whole prompt is reread at full price.',
    )
  }
  const text = statusLine(meter, now)
  // An expired cache has nothing left to count: leave the last frame alone.
  if (text === shared.lastStatus && advice.state !== 'warm' && advice.state !== 'soon') return
  shared.lastStatus = text
  await update($, nowAtom, () => now)
}

/** The shell command a Bash tool call runs; empty for any other tool, which `cardOf` turns down. */
const bashCommand = (tool: string, input: unknown): string => (tool === 'Bash' ? text(asRecord(input).command) : '')

/** The text `/meter` answers with. */
const details = (meter: Meter | null, now: number, policy: Policy): string => {
  if (meter === null) return 'No data yet. It appears after the first response.'
  const lines = [
    `model ${modelName(meter.model)} · effort ${meter.effort ?? '-'}`,
    `${contextText(meter.context)}${meter.context.compactAt === null ? '' : ` · auto-compact at ${meter.context.compactAt} tokens`}`,
    `cache TTL ${meter.ttl} (${meter.ttlSource})`,
    bandLine(meter, now, policy),
  ]
  const workers = workerLine(meter.workers, now)
  return workers === '' ? lines.join('\n') : [...lines, workers].join('\n')
}

export const register: Register = (on, options) => {
  const shared: Shared = {
    policy: {
      warnMs: (typeof options.warnSeconds === 'number' ? options.warnSeconds : 300) * 1000,
      compactAtTokens: typeof options.compactAtTokens === 'number' ? options.compactAtTokens : 100_000,
    },
    option: options.cacheTtl,
    showBand: options.showBand !== false,
    warnPercent: typeof options.warnContextPercent === 'number' ? options.warnContextPercent : 80,
    ttl: '5m',
    ttlSource: 'default',
    observed: undefined,
    ttlInputs: {},
    account: 'other',
    isPolling: false,
    timers: [],
    compactAt: undefined,
    lastPollAt: 0,
    isFullOps: false,
    locations: {},
    decisionFiles: new Map(),
    flowFiles: new Map(),
    lastStatus: '',
    hasWarnedContext: false,
    warnedEntry: 0,
  }

  on('session.start', async ($, e, next) => {
    const started = await next(e)
    // The meter is not reset here: a reload runs session.start again, and `$.state` is the session's own anyway.
    shared.isFullOps = await $.fs.exists(CONFIG).catch(() => false)
    await $.command
      .register({ name: COMMAND, description: 'Model, context, cache and worker status (hide/show toggles the band, history lists the requests)', argumentHint: '[hide|show|history]' })
      .catch(() => undefined)
    if (shared.isFullOps) {
      await $.command
        .register({ name: FULLOPS_COMMAND, description: 'Open the FullOps pane: workers, reviews or task flow above, decisions waiting for you below' })
        .catch(() => undefined)
    }

    // session.start can run more than once in a load: one set of timers only.
    for (const timer of shared.timers.splice(0)) timer.cancel()
    shared.timers.push($.clock.every(TICK_MS, () => tick($, shared)))
    if (shared.isFullOps) shared.timers.push($.clock.every(POLL_MS, () => poll($, shared)))

    await readTtlInputs($, shared)
    await readContext($, shared)
    // Not awaited: a slow or hung Orca must not hold the session's start.
    if (shared.isFullOps) void poll($, shared)

    return started
  })

  // Only the main loop: a subagent's requests have a cache prefix of their own.
  on('turn.step', async function* ($, e, next) {
    if (e.agentId !== undefined) return yield* next(e)
    const startedAt = await $.clock.now()
    const result = yield* next(e)
    if (result.usage !== undefined && result.usage !== null) {
      await record($, shared, { model: e.model, effort: e.effort }, startedAt, result.usage)
    }
    return result
  })

  // `/model` switches between turns; without this the line keeps the old name until the next reply.
  on('classic.PostModelSwitch', async ($, e, next) => {
    await commit($, shared, meter => ({ ...meter, model: e.to_model }))
    return next(e)
  })

  // FullOps Squad's settings hooks (done_gate, flow_gate, ...) run inside these classic events; the pane shows each run and its verdict.
  let hookSeq = 0
  on('classic.*', async ($, e, next) => {
    const event = next.event.slice('classic.'.length)
    if (!shared.isFullOps || !HOOK_EVENTS.has(event)) return next(e)
    const run: HookRun = { id: `h${++hookSeq}`, event, startedAt: await $.clock.now(), endedAt: null, status: 'running', detail: '' }
    await update($, hooksAtom, list => recordHookRun(list, run))
    try {
      const result = await next(e)
      const endedAt = await $.clock.now()
      await update($, hooksAtom, list => recordHookRun(list, hookOutcome(run, result, endedAt)))
      return result
    } catch (error) {
      const endedAt = await $.clock.now()
      await update($, hooksAtom, list => recordHookRun(list, { ...run, endedAt, status: 'blocked', detail: String(error) }))
      throw error
    }
  })

  on('turn.complete', async ($, e, next) => {
    if (e.agentId === undefined) await readContext($, shared)

    return next(e)
  })

  on('command.run', { command: COMMAND }, async ($, e) => {
    const argument = e.args.trim().toLowerCase()
    if (argument === 'hide' || argument === 'show') {
      await update($, isHiddenAtom, () => argument === 'hide')
      return { text: argument === 'hide' ? 'Band hidden. Run /meter show to bring it back.' : 'Band shown.' }
    }
    const now = await $.clock.now()
    const meter = await read($, meterAtom)
    if (argument === 'history') return { text: meter === null ? 'No data yet. It appears after the first response.' : historyText(meter, now) }
    return { text: details(meter, now, shared.policy) }
  })

  on('command.run', { command: FULLOPS_COMMAND }, async $ => {
    await readFullOps($, shared)
    await $.ui.open({ id: PANE, title: 'FullOps', columns: PANE_COLUMNS })
    return { text: 'FullOps pane opened. w, r and f switch tabs while it has focus.' }
  })

  on('ui.render', { component: 'Pane', requestId: PANE }, async ($, e) => {
    const elements = $.ui.resolve(e)
    const { Box, Button, Text } = elements
    // The animated cards need a surface that runs surface modules (terminal, desktop); the rest get text.
    const Client = 'Client' in elements ? elements.Client : undefined
    const fullops = await read($, fullopsAtom)
    const meter = await read($, meterAtom)
    const tab = await read($, tabAtom)
    const now = (await read($, nowAtom)) || (await $.clock.now())
    const workers = meter?.workers ?? null
    // The top half clips what does not fit; the tab row must never be the part squeezed away.
    const tabs = (
      <Box flexShrink={0}>
        {TABS.map(item => (
          <Button
            key={item.tab}
            label={item.label}
            hotkey={item.hotkey}
            variant={item.tab === tab ? 'primary' : 'secondary'}
            onPress={() => update($, tabAtom, () => item.tab)}
          />
        ))}
        <Text dimColor> {fullops === null ? '' : `role ${fullops.role}`}</Text>
      </Box>
    )
    // Tasks the coordinator has not sent out yet; state from an older load carries no list.
    const queued = tab === 'workers' && fullops !== null && workers !== null ? queuedText(fullops.queued ?? []) : ''
    const queue = queued === '' ? null : <Text dimColor>{queued}</Text>
    // The pane is tall: workers or reviews take the top half, the decisions waiting on the person the bottom.
    const decisions = fullops?.decisions ?? []
    const hooks = fullops === null ? [] : hookLines(await read($, hooksAtom), now)
    const issues = fullops?.issues ?? null
    const issueState = issues === null ? null : issueModeState(issues, now)
    const lower = (
      <Box flexDirection="column">
        {issues !== null && (
          <Box marginBottom={1}>
            <Text color={issueState === 'on' ? 'success' : issueState === 'paused' ? 'warning' : undefined} dimColor={issueState === 'off'}>
              {issueState === 'on' ? '● ' : '○ '}
              {issueModeLine(issues, now)}
            </Text>
          </Box>
        )}
        <Text bold>{decisions.length === 0 ? 'Decisions' : `Decisions waiting for you (${decisions.length})`}</Text>
        {decisions.length === 0 && <Text dimColor>{fullops === null ? '' : 'No decisions waiting.'}</Text>}
        {decisions.map(decision => {
          const block = decisionLines(decision, now)
          return (
            <Box key={decision.id} flexDirection="column" marginTop={1}>
              <Text color="claude" bold>
                {block.head}
              </Text>
              {block.lines.map((line, n) => (
                <Text key={`d-${n}`} dimColor={n > 0}>
                  {'  '}
                  {line}
                </Text>
              ))}
            </Box>
          )
        })}
        {fullops !== null && (
          <Box flexDirection="column" marginTop={1}>
            <Text bold>Hooks</Text>
            {hooks.length === 0 && <Text dimColor>No hook runs yet.</Text>}
            {hooks.map((line, n) => (
              <Box key={`h-${n}`} flexDirection="column">
                <Box>
                  <Text color={line.tone}>{line.icon} </Text>
                  <Text>{line.text}</Text>
                </Box>
                {line.detail !== '' && <Text dimColor>{`  ${line.detail}`}</Text>}
              </Box>
            ))}
          </Box>
        )}
      </Box>
    )
    const halves = (upper: RenderElement) => (
      <Box flexDirection="column" height="100%">
        <Box flexDirection="column" height="50%" overflow="hidden">
          {upper}
        </Box>
        <Box flexDirection="column" flexGrow={1} overflow="hidden">
          <Text dimColor>{'─'.repeat(PANE_COLUMNS)}</Text>
          {lower}
        </Box>
      </Box>
    )

    if (fullops !== null && tab === 'workers' && workers !== null && Client !== undefined) {
      const cards: CardsProps = {
        now,
        stages: [...STAGES],
        workers: workers.map(w => ({
          id: w.dispatchId,
          role: w.role,
          key: w.key,
          phase: w.phase,
          // Workers kept from an older load carry no stage.
          stage: w.stage ?? 0,
          since: w.since,
          stageAt: w.stageAt ?? w.since,
          lastAt: w.progress?.at ?? 0,
          needsAction: w.needsAction === true,
          isLive: w.isLive !== false,
          said: w.progress?.said ?? '',
        })),
      }
      return halves(
        <Box flexDirection="column">
          {tabs}
          <Client key="workers" module="./worker-cards.tsx" props={cards} />
          {queue}
        </Box>
      )
    }

    if (fullops !== null && tab === 'reviews') {
      const reviews = sortReviews(fullops.reviews)
      return halves(
        <Box flexDirection="column">
          {tabs}
          <Text dimColor>Independent reviews before merge (review.py). Open findings first.</Text>
          {reviews.length === 0 && <Text>No review records yet.</Text>}
          {reviews.map(review => {
            const line = reviewLine(review, now)
            return (
              <Box key={review.key} flexDirection="column" marginTop={1} flexShrink={0}>
                <Box>
                  <Text color={line.tone} bold>
                    {line.icon}{' '}
                  </Text>
                  <Text bold>{review.key}</Text>
                  <Text color={line.tone}> {line.state}</Text>
                  <Text dimColor>{line.when === '' ? '' : ` · ${line.when}`}</Text>
                </Box>
                {line.detail !== '' && <Text dimColor>{`  ${line.detail}`}</Text>}
              </Box>
            )
          })}
        </Box>
      )
    }

    if (fullops !== null && tab === 'flow') {
      const tasks = visibleFlow(fullops.flow ?? [], now)
      return halves(
        <Box flexDirection="column">
          {tabs}
          <Text dimColor>Each task's stage, kept by the coordinator's hook. Under it, its worker.</Text>
          {tasks.length === 0 && <Text>No task in the flow yet.</Text>}
          {tasks.map(one => {
            const row = flowRow(one, fullops.reviews, workers ?? [], fullops.roles ?? [], now)
            return (
              <Box key={one.key} flexDirection="column" marginTop={1} flexShrink={0}>
                <Box>
                  <Text bold>{row.key} </Text>
                  {row.rail.map((mark, at) => (
                    <Text key={`n${at}`} color={mark === 'passed' ? 'success' : mark === 'current' ? 'claude' : 'inactive'} bold={mark === 'current'}>
                      {mark === 'passed' ? '✔' : mark === 'current' ? '◉' : '○'}
                    </Text>
                  ))}
                  <Text color="claude"> {row.label}</Text>
                  <Text dimColor>{row.when === '' ? '' : ` · ${row.when}`}</Text>
                </Box>
                {row.flags.map((flag, n) => (
                  <Text key={`f${n}`} color={flag.tone}>{`  ${flag.text}`}</Text>
                ))}
                {row.inner !== '' && <Text dimColor>{`  ${row.inner}`}</Text>}
              </Box>
            )
          })}
        </Box>
      )
    }

    let rows: { head: string; lines: string[] }[]
    const plain = (texts: string[]) => texts.map(head => ({ head, lines: [] }))
    if (fullops === null) rows = plain(['This repository has no .fullops-squad/fullops.json.'])
    else if (meter?.workers === null || meter?.workers === undefined) rows = plain(['No Orca run is bound to this session.'])
    else rows = meter.workers.length === 0 ? plain(['No workers out.']) : meter.workers.map(worker => workerBlock(worker, now))

    return halves(
      <Box flexDirection="column">
        {tabs}
        {rows.map((row, at) => (
          <Box key={`row-${at}`} flexDirection="column" marginTop={row.lines.length > 0 ? 1 : 0}>
            <Text>{row.head}</Text>
            {row.lines.map((line, n) => (
              <Text key={`line-${n}`} dimColor>
                {'  '}
                {line}
              </Text>
            ))}
          </Box>
        ))}
        {queue}
      </Box>
    )
  })

  // The footer's mode labels: which FullOps role this session plays.
  on('ui.render', { component: 'SessionMode' }, async ($, e, next) => {
    const fullops = await read($, fullopsAtom)
    if (fullops === null) return next(e)
    const issues = fullops.issues ? [`issues ${issueModeState(fullops.issues, await $.clock.now())}`] : []
    return next({ ...e, props: { ...e.props, modes: [...e.props.modes, `fullops ${fullops.role}`, ...issues] } })
  })

  // The engine folds read-only calls into one count line (`Ran 1 shell command`), which never reaches the
  // ToolUse hook below; a group holding a FullOps step is unfolded so its card shows.
  on('ui.render', { component: 'ToolGroup' }, async ($, e, next) => {
    if (e.props.isExpanded || !shared.isFullOps) return next(e)
    const keys = (await read($, fullopsAtom))?.keys ?? {}
    const hasStep = e.props.calls.some(call => cardOf(bashCommand(call.tool, call.input), keys) !== null)
    return next(hasStep ? { ...e, props: { ...e.props, isExpanded: true } } : e)
  })

  // A FullOps step run through Bash draws as one card in place of its long command.
  on('ui.render', { component: 'ToolUse' }, async ($, e, next) => {
    if (!shared.isFullOps) return next(e)
    const card = cardOf(bashCommand(e.props.tool, e.props.input), (await read($, fullopsAtom))?.keys ?? {})
    if (card === null) return next(e)

    const { Box, Text } = $.ui.resolve(e)
    const state = e.props.isInterrupted ? ' interrupted' : e.props.isErrored ? ' failed' : e.props.isRunning ? ' running' : ''
    return (
      <Box>
        <Text bold>FullOps </Text>
        <Text>{card}</Text>
        <Text dimColor>{state}</Text>
      </Box>
    )
  })

  // While the coordinator works, the spinner says what is still out.
  on('ui.render', { component: 'Spinner' }, async ($, e, next) => {
    const fullops = await read($, fullopsAtom)
    const extra = fullops === null ? '' : spinnerText((await read($, meterAtom))?.workers ?? null, fullops.reviews)
    if (extra === '') return next(e)
    return next({ ...e, props: { ...e.props, suffix: `… · ${extra}` } })
  })

  // The hint line under the prompt draws `tail` dim after its own text, with no plugin prefix.
  on('ui.render', { component: 'PromptHint' }, async ($, e, next) => {
    const meter = await read($, meterAtom)
    if (meter === null) return next(e)
    const now = (await read($, nowAtom)) || meter.at
    return next({ ...e, props: { ...e.props, tail: ` · ${statusLine(meter, now)}` } })
  })

  on('ui.render', { component: 'AbovePrompt' }, async ($, e, next) => {
    const meter = await read($, meterAtom)

    if (!shared.showBand || e.props.hasSurvey || meter === null || (await read($, isHiddenAtom))) {
      return next(e)
    }

    // The status line already carries model, context and cache; the band only adds coor workers.
    const now = (await read($, nowAtom)) || meter.at
    const workers = workerLine(meter.workers, now)
    if (workers === '') return next(e)

    const { Box, Button, Text } = $.ui.resolve(e)
    return (
      <Box>
        <Text dimColor>{workers} </Text>
        <Button key="hide" label="Hide" onPress={() => update($, isHiddenAtom, () => true)} />
      </Box>
    )
  })
}
