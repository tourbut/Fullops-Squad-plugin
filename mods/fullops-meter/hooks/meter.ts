import type { Context, Meter, Worker } from '../types'
import { adviseCache, hitRatio, missOf, promptTokens, remainingMs } from './cache'
import type { Advice, Miss, Policy } from './cache'

/** Tokens in short form: 950, 12.3k, 124k, 1.2M. The steps sit where rounding would print 100.0k or 1000k. */
export const tokens = (n: number): string =>
  n >= 999_950
    ? `${(n / 1_000_000).toFixed(1)}M`
    : n >= 99_950
      ? `${Math.round(n / 1_000)}k`
      : n >= 1_000
        ? `${(n / 1_000).toFixed(1)}k`
        : String(n)

/** Milliseconds as m:ss, or h:mm:ss from an hour up. */
export const clock = (ms: number): string => {
  const total = Math.max(0, Math.ceil(ms / 1000))
  const seconds = String(total % 60).padStart(2, '0')
  if (total < 3600) return `${Math.floor(total / 60)}:${seconds}`
  return `${Math.floor(total / 3600)}:${String(Math.floor((total % 3600) / 60)).padStart(2, '0')}:${seconds}`
}

/** `claude-opus-5-5` as `opus-5-5`; a dash for a model not known yet. */
export const modelName = (model: string | null): string => (model === null ? '-' : model.replace(/^claude-/, ''))

export const contextText = (c: Context): string =>
  c.percent === null || c.tokens === null || c.window === null
    ? 'ctx -'
    : `ctx ${c.percent}% · ${tokens(Math.max(0, c.window - c.tokens))} left`

const last = (meter: Meter) => meter.samples[meter.samples.length - 1]

const cacheState = (meter: Meter, now: number): string => {
  const sample = last(meter)
  const left = remainingMs(sample, meter.ttl, now)
  const ratio = sample === undefined ? null : hitRatio(sample)
  const hit = ratio === null ? '-' : `${Math.round(ratio * 100)}%`
  return `cache ${hit} ${left === null ? '-' : left === 0 ? 'expired' : clock(left)}`
}

const modelText = (meter: Meter): string => `${modelName(meter.model)} ${meter.effort ?? '-'}`

/** The status line: model and effort, context left, cache hit rate and time until it lapses. */
export const statusLine = (meter: Meter, now: number): string =>
  `${modelText(meter)} · ${contextText(meter.context)} · ${cacheState(meter, now)}`

export const missText = (miss: Miss): string =>
  miss.reason === 'model'
    ? 'cache missed: model changed'
    : miss.reason === 'lapsed'
      ? `cache rewritten after expiry (${clock(miss.gapMs)} gap)`
      : 'cache missed: prefix changed (system prompt, tools, CLAUDE.md, settings)'

export const adviceText = (advice: Advice): string => {
  if (advice.state === 'expired') return `expired: next message rereads ${tokens(advice.tokens)} tokens at full price. /clear if done`
  if (advice.state !== 'soon') return ''
  return advice.shouldCompact
    ? `expires soon: stepping away? /compact now, while ${tokens(advice.tokens)} tokens are still cached`
    : 'expires soon: keep working to keep the cache warm'
}

/** Share of all prompt tokens the cache served across the kept requests, as a whole percent. */
export const sessionHit = (meter: Meter): number | null => {
  const all = meter.samples.reduce((sum, s) => sum + promptTokens(s), 0)
  return all === 0 ? null : Math.round((meter.samples.reduce((sum, s) => sum + s.read, 0) / all) * 100)
}

/** The band's first line: what the status line holds, with the margins and the cache's advice. */
export const bandLine = (meter: Meter, now: number, policy: Policy): string => {
  const c = meter.context
  const parts: string[] = [`${modelText(meter)} (${meter.ttl})`]
  if (c.percent !== null && c.tokens !== null && c.window !== null) {
    parts.push(`context ${c.percent}% (${tokens(c.tokens)}/${tokens(c.window)}) · ${tokens(Math.max(0, c.window - c.tokens))} left`)
    if (c.compactAt !== null) parts.push(`${tokens(Math.max(0, c.compactAt - c.tokens))} to auto-compact`)
  } else {
    parts.push('context -')
  }
  const latest = last(meter)
  const previous = meter.samples[meter.samples.length - 2]
  const miss = latest === undefined ? undefined : missOf(previous, latest, meter.ttl)
  const session = sessionHit(meter)
  parts.push(`${cacheState(meter, now)}${session === null ? '' : ` (session ${session}%)`}`)
  const advice = adviceText(adviseCache(latest, meter.ttl, now, policy))
  if (miss !== undefined) parts.push(missText(miss))
  if (advice !== '') parts.push(advice)
  if (meter.costUsd !== null) parts.push(`$${meter.costUsd.toFixed(2)}`)
  if (meter.fiveHour !== null) parts.push(`5h ${meter.fiveHour}%`)
  return parts.join(' · ')
}

const SYMBOL: Record<Worker['phase'], string> = { active: '▶', done: '✔', failed: '✖', stopped: '■' }

const SHOWN = 4

/** One worker: `▶ dev K1 12m`, or `✖ ops K3 process_exited`. */
export const workerText = (w: Worker, now: number): string => {
  const age = w.phase === 'active' ? ` ${Math.max(1, Math.round((now - w.since) / 60_000))}m` : ''
  const detail = w.phase === 'failed' || w.phase === 'stopped' ? ` ${w.detail}` : ''
  return `${SYMBOL[w.phase]} ${w.role}${w.key === '' ? '' : ` ${w.key}`}${age}${detail}`
}

const ago = (ms: number): string => (ms < 60_000 ? `${Math.max(0, Math.round(ms / 1000))}s` : `${Math.round(ms / 60_000)}m`)

/** One worker in the pane: its line, then what it last said and did. */
export const workerBlock = (w: Worker, now: number): { head: string; lines: string[] } => {
  const flags = [
    w.phase === 'active' && w.activity !== '' ? w.activity : '',
    w.needsAction ? '⚠ waiting on you' : '',
    w.isLive === false ? '✖ agent gone' : '',
  ].filter(Boolean)
  const head = [workerText(w, now), ...flags].join(' · ')
  // Workers kept in state from an older load carry no progress field.
  const p = w.progress
  if (p === null || p === undefined) return { head, lines: [] }
  const lines = [...(p.said === '' ? [] : [`“${p.said}”`]), ...p.steps.map(step => `› ${step}`)]
  if (w.phase === 'active' && p.at > 0) lines.push(`last activity ${ago(now - p.at)} ago`)
  return { head, lines }
}

/** `queued: K8, K9 · +3` for the tasks still waiting for a worker; empty for none. */
export const queuedText = (queued: readonly string[]): string => {
  if (queued.length === 0) return ''
  const more = queued.length > SHOWN ? ` · +${queued.length - SHOWN}` : ''
  return `queued: ${queued.slice(0, SHOWN).join(', ')}${more}`
}

/** The band's second line:the workers the coordinator sent work to. Empty when there is nothing to show. */
export const workerLine = (workers: readonly Worker[] | null, now: number): string => {
  if (workers === null || workers.length === 0) return ''
  const shown = workers.slice(0, SHOWN).map(w => workerText(w, now))
  const more = workers.length > SHOWN ? ` · +${workers.length - SHOWN}` : ''
  return `worker ${shown.join(' · ')}${more}`
}
