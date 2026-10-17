import type { Sample, Ttl } from '../types'

// The prompt cache's rules, from Anthropic's prompt-caching documentation:
//  - an entry lives 5 minutes, or 1 hour where that was asked for or the account gets it;
//  - the lifetime counts from the START of the request that wrote or read the entry, and every
//    read starts it over;
//  - a prompt is `input` (uncached) + `cache_read` + `cache_creation`.

const MINUTE = 60_000
/** Request starts are not exact to the second, so a hit or a miss near a boundary proves nothing. */
const SLACK = 10_000

export const ttlMs = (ttl: Ttl): number => (ttl === '1h' ? 60 * MINUTE : 5 * MINUTE)

export const promptTokens = (s: Sample): number => s.read + s.write + s.fresh

/** The share of the prompt the cache served, 0 to 1; null for an empty prompt. */
export const hitRatio = (s: Sample): number | null => {
  const all = promptTokens(s)
  return all === 0 ? null : s.read / all
}

export type Account = 'subscription' | 'credits' | 'other'

/**
 * The account kind from the rate-limit windows the last response reported: a five-hour or
 * seven-day window means a Claude subscription, and a full one means requests now draw on
 * usage credits. No window (an API key, a cloud provider, or no response yet) says nothing.
 */
export const accountOf = (windows: readonly { kind: string; percentUsed: number }[]): Account => {
  const plan = windows.filter(w => w.kind === 'five_hour' || w.kind === 'seven_day')
  if (plan.length === 0) return 'other'
  return plan.some(w => w.percentUsed >= 100) ? 'credits' : 'subscription'
}

export type TtlInputs = {
  /** The mod's own option: `auto`, `5m` or `1h`. */
  option: unknown
  force5m?: string
  ttlVariable?: string
  enable1h?: string
  /** `promptCacheTtl` from a settings file. */
  setting?: unknown
  account: Account
}

const asTtl = (value: unknown): Ttl | undefined => (value === '5m' || value === '1h' ? value : undefined)
const isOn = (value: string | undefined): boolean => value === '1' || value?.toLowerCase() === 'true'

/** Which lifetime to expect and why: the first rule that applies, from the most explicit. */
export const decideTtl = (input: TtlInputs): { ttl: Ttl; source: string } => {
  const pinned = asTtl(input.option)
  if (pinned !== undefined) return { ttl: pinned, source: 'mod option' }
  if (isOn(input.force5m)) return { ttl: '5m', source: 'FORCE_PROMPT_CACHING_5M' }
  const fromVariable = asTtl(input.ttlVariable)
  if (fromVariable !== undefined) return { ttl: fromVariable, source: 'CLAUDE_CODE_PROMPT_CACHE_TTL' }
  const fromSetting = asTtl(input.setting)
  if (fromSetting !== undefined) return { ttl: fromSetting, source: 'promptCacheTtl setting' }
  if (isOn(input.enable1h)) return { ttl: '1h', source: 'ENABLE_PROMPT_CACHING_1H' }
  if (input.account === 'subscription') return { ttl: '1h', source: 'subscription default' }
  if (input.account === 'credits') return { ttl: '5m', source: 'usage credits default' }
  return { ttl: '5m', source: 'default' }
}

/**
 * What the request timing proves about the lifetime, which beats every rule above.
 * A hit more than 5 minutes after the previous request can only be a 1-hour entry. A miss
 * 5 to 60 minutes after it, on the same model and a prompt that did not shrink, says the
 * entry lapsed, so 5 minutes (unless 1 hour was already proven: a changed prefix looks the same).
 */
export const observeTtl = (prev: Sample | undefined, cur: Sample, known: Ttl | undefined): Ttl | undefined => {
  if (prev === undefined || prev.model !== cur.model) return known
  const gap = cur.startedAt - prev.startedAt
  const isHit = cur.read > 0
  if (isHit && gap > 5 * MINUTE + SLACK) return '1h'
  const isLapse = !isHit && gap > 5 * MINUTE + SLACK && gap < 60 * MINUTE - SLACK
  if (isLapse && known !== '1h' && promptTokens(cur) >= promptTokens(prev)) return '5m'
  return known
}

export type Miss = { reason: 'model' | 'lapsed' | 'prefix'; gapMs: number }

/** Why a request did not read what the previous one left in the cache; undefined when it did. */
export const missOf = (prev: Sample | undefined, cur: Sample, ttl: Ttl): Miss | undefined => {
  if (prev === undefined) return undefined
  const isServed = cur.read >= 0.1 * promptTokens(prev)
  if (isServed) return undefined
  const gapMs = cur.startedAt - prev.startedAt
  if (prev.model !== cur.model) return { reason: 'model', gapMs }
  return { reason: gapMs > ttlMs(ttl) ? 'lapsed' : 'prefix', gapMs }
}

/** Milliseconds until the entry lapses; null before any request. */
export const remainingMs = (last: Sample | undefined, ttl: Ttl, now: number): number | null =>
  last === undefined ? null : Math.max(0, last.startedAt + ttlMs(ttl) - now)

export type Policy = { warnMs: number; compactAtTokens: number }

export type Advice = { state: 'none' | 'warm' | 'soon' | 'expired'; tokens: number; shouldCompact: boolean }

/**
 * Where the cache stands and whether a /compact is worth it now. Compacting pays only while the cache
 * is warm: after it lapses, /compact rereads the whole conversation at full price too.
 */
export const adviseCache = (last: Sample | undefined, ttl: Ttl, now: number, policy: Policy): Advice => {
  const left = remainingMs(last, ttl, now)
  if (last === undefined || left === null) return { state: 'none', tokens: 0, shouldCompact: false }
  const tokens = promptTokens(last)
  if (left === 0) return { state: 'expired', tokens, shouldCompact: false }
  // Half the lifetime at most, so a 5-minute cache is not "about to lapse" from its first second.
  const isSoon = left <= Math.min(policy.warnMs, ttlMs(ttl) / 2)
  return { state: isSoon ? 'soon' : 'warm', tokens, shouldCompact: isSoon && tokens >= policy.compactAtTokens }
}

/** The samples to keep: the newest `keep`, oldest first. */
export const keepSamples = (samples: readonly Sample[], next: Sample, keep: number): Sample[] =>
  [...samples, next].slice(-keep)
