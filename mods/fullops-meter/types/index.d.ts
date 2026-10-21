/** The prompt cache's lifetime: 5 minutes by default, 1 hour where the account or settings ask for it. */
export type Ttl = '5m' | '1h'

/** One main-loop request: what the prompt cache did with it. */
export type Sample = {
  turnId: string
  index: number
  model: string
  /** When the request started, in `$.clock.now()` milliseconds. The cache lifetime counts from here. */
  startedAt: number
  /** Prompt tokens the cache served. */
  read: number
  /** Prompt tokens written to the cache. */
  write: number
  /** Prompt tokens not cached at all. */
  fresh: number
  output: number
}

/** The live context window, from `$.session.usage()`. */
export type Context = {
  tokens: number | null
  window: number | null
  percent: number | null
  /** Token count at which auto-compaction runs; null when off or not read yet. */
  compactAt: number | null
}

/** One worker the coordinator sent work to. */
export type Worker = {
  dispatchId: string
  /** The worker's role, taken from its worktree folder name. */
  role: string
  /** The task key the dispatch carried. */
  key: string
  phase: 'active' | 'done' | 'failed' | 'stopped'
  /** Orca's own detail for a failure (`process_exited`, `agent_readiness`, ...). */
  detail: string
  /** When the phase was first seen, in `$.clock.now()` milliseconds. */
  since: number
  /** Orca's activity for the agent (`working`, `idle`, `done`, ...); empty when it does not say. */
  activity: string
  /** False when Orca's liveness check says the agent is gone. */
  isLive: boolean
  /** True when Orca flags the dispatch as waiting on someone (a question, a gate). */
  needsAction: boolean
  /** The furthest main step reached: an index into STAGES (explore, build, verify, report), or STAGES.length when done. */
  stage: number
  /** When `stage` last moved, in `$.clock.now()` milliseconds; the dispatch's `since` until it does. */
  stageAt: number
  /** What it is doing, read from its transcript for active workers only; null until read. */
  progress: Progress | null
}

/** What a running worker is doing, from its transcript. */
export type Progress = {
  /** The worker's latest words, first line. */
  said: string
  /** Its latest tool calls (up to six), newest last: `Bash: npm test`, `Edit report.md`. */
  steps: string[]
  /** When it last did anything, in milliseconds; 0 when unknown. */
  at: number
}

/** What the mod last read. */
export type Meter = {
  at: number
  context: Context
  /** The latest main-loop requests, oldest first. */
  samples: Sample[]
  ttl: Ttl
  /** Why the lifetime is what it is, for the `/meter` text. */
  ttlSource: string
  /** The model the session runs, as the engine names it (e.g. `claude-opus-5-5`). */
  model: string | null
  /** How hard the last request asked the model to think; null before the first request. */
  effort: string | null
  costUsd: number | null
  fiveHour: number | null
  /** The coordinator's workers; null when this session is bound to no Orca run. */
  workers: Worker[] | null
}

/** What was seen of each dispatch, so a finished one can leave the list after a while. */
export type Seen = Record<string, { phase: Worker['phase']; since: number; isBaseline: boolean; needsAction: boolean }>

/** One `<key>-review` folder under `.fullops-squad/docs/evaluations/qa-reports/`. */
export type Review = {
  key: string
  /** recorded: `result.json` is written; waived, abandoned, superseded: that receipt stands; open: none yet. */
  state: 'recorded' | 'waived' | 'abandoned' | 'superseded' | 'open'
  /** The first line of the reviewer's conclusion. */
  conclusion: string
  findings: number
  unresolved: number
  /** The worst severity among the unresolved findings. */
  worst: string | null
  /** The folder's last change, in milliseconds. */
  at: number
}

/** One open decision the coordinator asked the person for, from `decision.py` in the git common folder. */
export type Decision = {
  id: string
  /** The task key it belongs to; empty when none was given. */
  key: string
  question: string
  options: string[]
  /** What waits on it (a role, a task, a worker question's message id); empty when none was given. */
  blocks: string
  /** When it was asked, in milliseconds; 0 when the record has no readable time. */
  askedAt: number
}

/** What the FullOps pane and labels read from the repository. */
export type FullOps = {
  /** The role this checkout plays (`coor`, `dev`, ...). */
  role: string
  reviews: Review[]
  /** Orca task id to task key, so a dispatch card can name the task. */
  keys: Record<string, string>
  /** The keys of tasks still waiting for a worker, in listing order. */
  queued: string[]
  /** Open decisions, oldest first; state from an older load carries none. */
  decisions?: Decision[]
}

/** One run of a settings hook event FullOps Squad hooks, from the `classic.*` chain. */
export type HookRun = {
  id: string
  /** The classic event name: `Stop`, `PreToolUse`, ... */
  event: string
  /** In `$.clock.now()` milliseconds. */
  startedAt: number
  endedAt: number | null
  status: 'running' | 'ok' | 'blocked'
  /** The block or deny reason's first line; empty when the run passed. */
  detail: string
}

export type Tab = 'workers' | 'reviews'

declare module 'claude-code' {
  interface PluginState {
    'fullops-meter': { meter: Meter | null; now: number; isHidden: boolean; seen: Seen; fullops: FullOps | null; tab: Tab; hooks: HookRun[] }
  }
}
