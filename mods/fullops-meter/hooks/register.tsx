import { atom, read, update } from 'claude-code'
import type { EngineInterface, Register } from 'claude-code'

import type { Meter, Review, Sample, Tab, Ttl } from '../types'
import { accountOf, adviseCache, decideTtl, keepSamples, observeTtl, promptTokens } from './cache'
import type { Policy } from './cache'
import { MARKERS, branchOf, cardOf, parseConfig, reviewText, roleOf, spinnerText, summarizeReview } from './fullops'
import { bandLine, contextText, modelName, statusLine, workerBlock, workerLine } from './meter'
import { parseKeys, parseProgress, parseRows, parseRunId, reconcile } from './workers'

const meterAtom = atom({ plugin: 'fullops-meter', key: 'meter' } as const, null)
const nowAtom = atom({ plugin: 'fullops-meter', key: 'now' } as const, 0)
const isHiddenAtom = atom({ plugin: 'fullops-meter', key: 'isHidden' } as const, false)
const seenAtom = atom({ plugin: 'fullops-meter', key: 'seen' } as const, {})
const fullopsAtom = atom({ plugin: 'fullops-meter', key: 'fullops' } as const, null)
const tabAtom = atom({ plugin: 'fullops-meter', key: 'tab' } as const, 'workers')

const KEEP_SAMPLES = 50
const TICK_MS = 1000
const POLL_MS = 15_000
const COMMAND = 'meter'
const FULLOPS_COMMAND = 'fullops'
const PANE = 'fullops'
const CONFIG = '.fullops-squad/fullops.json'
const REVIEWS = '.fullops-squad/docs/evaluations/qa-reports'
const KEEP_REVIEWS = 8
/** Transcript rows read per active worker: enough to reach its last words past a run of tool calls. */
const PROGRESS_ROWS = 30
/** The dock width the pane asks for; the person can still drag it. */
const PANE_COLUMNS = 56
const TABS: readonly { tab: Tab; label: string; hotkey: string }[] = [
  { tab: 'workers', label: 'Workers', hotkey: 'w' },
  { tab: 'reviews', label: 'Reviews', hotkey: 'r' },
]
/** A prompt this small is not worth a notice when its cache lapses. */
const NOTICE_MIN_TOKENS = 20_000

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
  /** undefined: not read yet; null: auto-compaction is off. */
  compactAt: number | null | undefined
  isFirstPoll: boolean
  isFullOps: boolean
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
  const meter = patch((await read($, meterAtom)) ?? blank(now, shared))
  await update($, meterAtom, () => meter)
  await update($, nowAtom, () => now)

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

/** The lifetime to expect: the rules, then what the request timing proved. */
async function chooseTtl($: EngineInterface, shared: Shared): Promise<void> {
  const [force5m, ttlVariable, enable1h] = await Promise.all([
    $.env.get('FORCE_PROMPT_CACHING_5M').catch(() => undefined),
    $.env.get('CLAUDE_CODE_PROMPT_CACHE_TTL').catch(() => undefined),
    $.env.get('ENABLE_PROMPT_CACHING_1H').catch(() => undefined),
  ])
  const usage = await $.session.usage().catch(() => undefined)
  const setting = await readSetting($)
  const choice = decideTtl({
    option: shared.option,
    force5m,
    ttlVariable,
    enable1h,
    setting,
    account: accountOf(usage?.rateLimits ?? []),
  })
  shared.ttl = shared.observed ?? choice.ttl
  shared.ttlSource = shared.observed === undefined ? choice.source : `observed from request gaps (${choice.source}: ${choice.ttl})`
}

/** `promptCacheTtl` from the first settings file that sets it: local, project, then user. */
async function readSetting($: EngineInterface): Promise<unknown> {
  const home = await $.env.get('HOME').catch(() => undefined)
  const cwd = await $.session.cwd().catch(() => undefined)
  const files = [cwd && `${cwd}/.claude/settings.local.json`, cwd && `${cwd}/.claude/settings.json`, home && `${home}/.claude/settings.json`]
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
  const reading = await $.session.usage()
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
  step: { turnId: string; index: number; model: string; effort?: string | number },
  startedAt: number,
  usage: { model: string; input_tokens: number; output_tokens: number; cache_read_input_tokens: number; cache_creation_input_tokens: number },
): Promise<void> {
  const sample: Sample = {
    turnId: step.turnId,
    index: step.index,
    model: usage.model || step.model,
    startedAt,
    read: usage.cache_read_input_tokens,
    write: usage.cache_creation_input_tokens,
    fresh: usage.input_tokens,
    output: usage.output_tokens,
  }
  const before = (await read($, meterAtom))?.samples ?? []
  shared.observed = observeTtl(before[before.length - 1], sample, shared.observed)
  await chooseTtl($, shared)
  await commit($, shared, meter => ({
    ...meter,
    samples: keepSamples(meter.samples, sample, KEEP_SAMPLES),
    ttl: shared.ttl,
    ttlSource: shared.ttlSource,
    model: sample.model,
    effort: step.effort === undefined ? null : String(step.effort),
  }))
}

/** The workers the coordinator's Orca run has: Orca's own listing, nothing is sent anywhere. */
async function pollWorkers($: EngineInterface, shared: Shared): Promise<void> {
  const run = await $.process.run(['orca', 'orchestration', 'run-current', '--json'], { timeoutMs: 15_000 }).catch(() => undefined)
  const runId = run === undefined || run.exitCode !== 0 ? null : parseRunId(run.stdout)
  if (runId === null) {
    await commit($, shared, meter => ({ ...meter, workers: null }))
    return
  }
  const [list, tasks] = await Promise.all([
    $.process.run(['orca', 'orchestration', 'worker-list', '--run', runId, '--limit', '100', '--json'], { timeoutMs: 20_000 }),
    $.process.run(['orca', 'orchestration', 'task-list', '--run', runId, '--json'], { timeoutMs: 20_000 }),
  ]).catch(() => [undefined, undefined] as const)
  if (list === undefined || tasks === undefined || list.exitCode !== 0) return

  const now = await $.clock.now()
  const keys = parseKeys(tasks.stdout)
  const merged = reconcile(await read($, seenAtom), parseRows(list.stdout), keys, now, shared.isFirstPoll)
  shared.isFirstPoll = false
  await update($, seenAtom, () => merged.seen)
  await update($, fullopsAtom, before => (before === null ? null : { ...before, keys }))
  const before = (await read($, meterAtom))?.workers ?? []
  const workers = await Promise.all(
    merged.workers.map(async worker => {
      const kept = before.find(old => old.dispatchId === worker.dispatchId)?.progress ?? null
      if (worker.phase !== 'active') return { ...worker, progress: kept }
      const out = await $.process
        .run(['orca', 'orchestration', 'worker-read', '--dispatch', worker.dispatchId, '--source', 'transcript', '--limit', String(PROGRESS_ROWS), '--json'], { timeoutMs: 15_000 })
        .catch(() => undefined)
      return { ...worker, progress: (out?.exitCode === 0 ? parseProgress(out.stdout) : null) ?? kept }
    }),
  )
  await commit($, shared, meter => ({ ...meter, workers }))
}

/** The checkout's branch, from `.git/HEAD`; a worktree's `.git` is a file naming its own git folder. */
async function readBranch($: EngineInterface): Promise<string | null> {
  const pointer = await $.fs.read('.git').catch(() => null)
  const gitDir = pointer === null ? '.git' : /^gitdir:\s*(.+)$/m.exec(pointer)?.[1]?.trim()
  if (gitDir === undefined) return null
  return branchOf(await $.fs.read(`${gitDir}/HEAD`).catch(() => ''))
}

/** The newest review folders, each with what its files say. */
async function readReviews($: EngineInterface): Promise<Review[]> {
  const entries = await $.fs.list(REVIEWS).catch(() => [])
  const folders = entries
    .filter(entry => entry.kind === 'dir' && entry.name.endsWith('-review'))
    .sort((a, b) => b.mtimeMs - a.mtimeMs)
    .slice(0, KEEP_REVIEWS)
  return Promise.all(
    folders.map(async folder => {
      const dir = `${REVIEWS}/${folder.name}`
      const result = await $.fs.read(`${dir}/result.json`).catch(() => null)
      let marker = null
      for (const [file, name] of MARKERS) {
        if (await $.fs.exists(`${dir}/${file}`).catch(() => false)) {
          marker = name
          break
        }
      }
      return summarizeReview(folder.name.slice(0, -'-review'.length), result, marker, folder.mtimeMs)
    }),
  )
}

/** The role and reviews, read from the repository's own files. */
async function readFullOps($: EngineInterface): Promise<void> {
  const config = parseConfig(await $.fs.read(CONFIG).catch(() => ''))
  if (config === null) return
  const role = roleOf(config, await readBranch($))
  const reviews = await readReviews($)
  await update($, fullopsAtom, before => ({ role, reviews, keys: before?.keys ?? {} }))
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
    $.ui.toast('Prompt cache expires soon. Keep working to keep it; after expiry the whole prompt is rewritten.')
  }
  const text = statusLine(meter, now)
  // An expired cache has nothing left to count: leave the last frame alone.
  if (text === shared.lastStatus && advice.state !== 'warm' && advice.state !== 'soon') return
  shared.lastStatus = text
  await update($, nowAtom, () => now)
}

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
      warnMs: (typeof options.warnSeconds === 'number' ? options.warnSeconds : 60) * 1000,
      compactAtTokens: typeof options.compactAtTokens === 'number' ? options.compactAtTokens : 100_000,
    },
    option: options.cacheTtl,
    showBand: options.showBand !== false,
    warnPercent: typeof options.warnContextPercent === 'number' ? options.warnContextPercent : 80,
    ttl: '5m',
    ttlSource: 'default',
    observed: undefined,
    compactAt: undefined,
    isFirstPoll: true,
    isFullOps: false,
    lastStatus: '',
    hasWarnedContext: false,
    warnedEntry: 0,
  }

  on('session.start', async ($, e, next) => {
    const started = await next(e)
    // The meter is not reset here: a reload runs session.start again, and `$.state` is the session's own anyway.
    // 0.2.0 pinned its line with $.ui.status, which the engine prefixes with the plugin name; clear what it left.
    $.ui.status(undefined)
    shared.isFullOps = await $.fs.exists('.fullops-squad/fullops.json').catch(() => false)
    await chooseTtl($, shared)
    await readContext($, shared)
    await $.command
      .register({ name: COMMAND, description: 'Model, context, cache and worker status (hide/show toggles the band)', argumentHint: '[hide|show]' })
      .catch(() => undefined)

    $.clock.every(TICK_MS, () => tick($, shared))
    if (shared.isFullOps) {
      await $.command
        .register({ name: FULLOPS_COMMAND, description: 'Open the FullOps pane: workers and reviews' })
        .catch(() => undefined)
      await readFullOps($)
      await pollWorkers($, shared)
      $.clock.every(POLL_MS, async () => {
        await readFullOps($)
        await pollWorkers($, shared)
      })
    }

    return started
  })

  // Only the main loop: a subagent's requests have a cache prefix of their own.
  on('turn.step', async function* ($, e, next) {
    if (e.agentId !== undefined) return yield* next(e)
    const startedAt = await $.clock.now()
    const result = yield* next(e)
    if (result.usage !== undefined && result.usage !== null) {
      await record($, shared, { turnId: e.turnId, index: e.index, model: e.model, effort: e.effort }, startedAt, result.usage)
    }
    return result
  })

  // `/model` switches between turns; without this the line keeps the old name until the next reply.
  on('classic.PostModelSwitch', async ($, e, next) => {
    await commit($, shared, meter => ({ ...meter, model: e.to_model }))
    return next(e)
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
    return { text: details(await read($, meterAtom), now, shared.policy) }
  })

  on('command.run', { command: FULLOPS_COMMAND }, async $ => {
    await readFullOps($)
    await $.ui.open({ id: PANE, title: 'FullOps', columns: PANE_COLUMNS })
    return { text: 'FullOps pane opened. w and r switch tabs while it has focus.' }
  })

  on('ui.render', { component: 'Pane', requestId: PANE }, async ($, e) => {
    const { Box, Button, Text } = $.ui.resolve(e)
    const fullops = await read($, fullopsAtom)
    const meter = await read($, meterAtom)
    const tab = await read($, tabAtom)
    const now = (await read($, nowAtom)) || (await $.clock.now())

    let rows: { head: string; lines: string[] }[]
    const plain = (texts: string[]) => texts.map(head => ({ head, lines: [] }))
    if (fullops === null) rows = plain(['This repository has no .fullops-squad/fullops.json.'])
    else if (tab === 'reviews') rows = plain(fullops.reviews.length === 0 ? ['No review records yet.'] : fullops.reviews.map(reviewText))
    else if (meter?.workers === null || meter?.workers === undefined) rows = plain(['No Orca run is bound to this session.'])
    else rows = meter.workers.length === 0 ? plain(['No workers out.']) : meter.workers.map(worker => workerBlock(worker, now))

    return (
      <Box flexDirection="column">
        <Box>
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
        {rows.map(row => (
          <Box flexDirection="column" marginTop={row.lines.length > 0 ? 1 : 0}>
            <Text>{row.head}</Text>
            {row.lines.map(line => (
              <Text dimColor>  {line}</Text>
            ))}
          </Box>
        ))}
      </Box>
    )
  })

  // The footer's mode labels: which FullOps role this session plays.
  on('ui.render', { component: 'SessionMode' }, async ($, e, next) => {
    const fullops = await read($, fullopsAtom)
    if (fullops === null) return next(e)
    return next({ ...e, props: { ...e.props, modes: [...e.props.modes, `fullops ${fullops.role}`] } })
  })

  // A FullOps step run through Bash draws as one card in place of its long command.
  on('ui.render', { component: 'ToolUse' }, async ($, e, next) => {
    if (e.props.tool !== 'Bash' || !shared.isFullOps) return next(e)
    const command = (e.props.input as { command?: unknown } | null)?.command
    const card = typeof command === 'string' ? cardOf(command, (await read($, fullopsAtom))?.keys ?? {}) : null
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
