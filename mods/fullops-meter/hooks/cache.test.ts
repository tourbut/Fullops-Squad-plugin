import { describe, expect, test } from 'claude-code/testing'

import type { Sample } from '../types'
import { accountOf, adviseCache, decideTtl, hitRatio, keepSamples, missOf, observeTtl, remainingMs, ttlMs } from './cache'

const MIN = 60_000

const sample = (startedAt: number, read: number, write: number, fresh: number, model = 'opus'): Sample => ({
  turnId: 't',
  index: 0,
  model,
  startedAt,
  read,
  write,
  fresh,
  output: 10,
})

describe('lifetime rules', () => {
  const base = { option: 'auto', account: 'other' as const }

  test('the option, then the environment, then the setting, then the account', () => {
    expect(decideTtl({ ...base, option: '1h', force5m: '1' })).toEqual({ ttl: '1h', source: 'mod option' })
    expect(decideTtl({ ...base, force5m: '1', ttlVariable: '1h' }).ttl).toBe('5m')
    expect(decideTtl({ ...base, ttlVariable: '1h', setting: '5m' }).ttl).toBe('1h')
    expect(decideTtl({ ...base, setting: '5m', enable1h: '1' }).ttl).toBe('5m')
    expect(decideTtl({ ...base, enable1h: 'true', account: 'credits' }).ttl).toBe('1h')
  })

  test('a subscription gets an hour, credits and everything else five minutes', () => {
    expect(decideTtl({ ...base, account: 'subscription' }).ttl).toBe('1h')
    expect(decideTtl({ ...base, account: 'credits' }).ttl).toBe('5m')
    expect(decideTtl(base)).toEqual({ ttl: '5m', source: 'default' })
  })

  test('the account comes from the rate-limit windows', () => {
    expect(accountOf([])).toBe('other')
    expect(accountOf([{ kind: 'spend_limit', percentUsed: 10 }])).toBe('other')
    expect(accountOf([{ kind: 'five_hour', percentUsed: 20 }])).toBe('subscription')
    expect(accountOf([{ kind: 'five_hour', percentUsed: 100 }, { kind: 'seven_day', percentUsed: 30 }])).toBe('credits')
  })

  test('minutes', () => {
    expect(ttlMs('5m')).toBe(5 * MIN)
    expect(ttlMs('1h')).toBe(60 * MIN)
  })
})

describe('what the request timing proves', () => {
  const prev = sample(0, 90, 10, 0)

  test('a hit after five minutes can only be the one-hour lifetime', () => {
    expect(observeTtl(prev, sample(6 * MIN, 95, 5, 0), undefined)).toBe('1h')
    expect(observeTtl(prev, sample(20 * MIN, 95, 5, 0), '5m')).toBe('1h')
  })

  test('a miss after five minutes on a prompt that grew says it lapsed', () => {
    expect(observeTtl(prev, sample(10 * MIN, 0, 120, 0), undefined)).toBe('5m')
  })

  test('a few cached tokens from a shared prefix are a miss, not a proven hour', () => {
    expect(observeTtl(prev, sample(6 * MIN, 5, 95, 0), undefined)).toBe('5m')
  })

  test('a miss does not undo a proven hour, and a model change proves nothing', () => {
    expect(observeTtl(prev, sample(10 * MIN, 0, 120, 0), '1h')).toBe('1h')
    expect(observeTtl(prev, sample(10 * MIN, 0, 120, 0, 'sonnet'), undefined)).toBeUndefined()
  })

  test('requests close together, a shrunk prompt and the first request prove nothing', () => {
    expect(observeTtl(prev, sample(2 * MIN, 95, 5, 0), undefined)).toBeUndefined()
    expect(observeTtl(prev, sample(10 * MIN, 0, 50, 0), undefined)).toBeUndefined()
    expect(observeTtl(undefined, sample(10 * MIN, 0, 50, 0), '5m')).toBe('5m')
  })
})

describe('misses', () => {
  const prev = sample(0, 90, 10, 0)

  test('names the cause', () => {
    expect(missOf(prev, sample(MIN, 95, 5, 0), '5m')).toBeUndefined()
    expect(missOf(prev, sample(MIN, 0, 100, 0, 'sonnet'), '5m')?.reason).toBe('model')
    expect(missOf(prev, sample(10 * MIN, 0, 100, 0), '5m')?.reason).toBe('lapsed')
    expect(missOf(prev, sample(2 * MIN, 0, 100, 0), '5m')?.reason).toBe('prefix')
    expect(missOf(prev, sample(10 * MIN, 0, 100, 0), '1h')?.reason).toBe('prefix')
    expect(missOf(undefined, sample(0, 0, 100, 0), '5m')).toBeUndefined()
    // After /compact: a 300k prompt becomes 25k, 20k of it served from the cache.
    expect(missOf(sample(0, 290_000, 10_000, 0), sample(MIN, 20_000, 0, 5_000), '5m')).toBeUndefined()
    expect(missOf(sample(0, 290_000, 10_000, 0), sample(MIN, 0, 20_000, 5_000), '5m')?.reason).toBe('prefix')
  })
})

describe('time left and advice', () => {
  const last = sample(100_000, 90, 10, 0)
  const policy = { warnMs: 60_000, compactAtTokens: 100_000 }

  test('the lifetime counts from the start of the last request', () => {
    expect(remainingMs(last, '5m', 100_000 + 2 * MIN)).toBe(3 * MIN)
    expect(remainingMs(last, '1h', 100_000 + 2 * MIN)).toBe(58 * MIN)
    expect(remainingMs(last, '5m', 100_000 + 9 * MIN)).toBe(0)
    expect(remainingMs(undefined, '5m', 0)).toBeNull()
  })

  test('warm, about to lapse, lapsed', () => {
    expect(adviseCache(last, '5m', 100_000 + MIN, policy).state).toBe('warm')
    expect(adviseCache(last, '5m', 100_000 + 4.5 * MIN, policy).state).toBe('soon')
    expect(adviseCache(last, '5m', 100_000 + 6 * MIN, policy).state).toBe('expired')
    expect(adviseCache(undefined, '5m', 0, policy).state).toBe('none')
  })

  test('a large prompt about to lapse suggests compacting; a lapsed one no longer does', () => {
    const large = sample(0, 150_000, 0, 500)
    expect(adviseCache(large, '5m', 4.5 * MIN, policy)).toEqual({ state: 'soon', tokens: 150_500, shouldCompact: true })
    expect(adviseCache(large, '5m', 6 * MIN, policy)).toEqual({ state: 'expired', tokens: 150_500, shouldCompact: false })
    expect(adviseCache(last, '5m', 100_000 + 4.5 * MIN, policy).shouldCompact).toBe(false)
  })

  test('the warning starts at most half a lifetime before the lapse', () => {
    const early = { warnMs: 5 * MIN, compactAtTokens: 100_000 }
    expect(adviseCache(last, '5m', 100_000 + 2 * MIN, early).state).toBe('warm')
    expect(adviseCache(last, '5m', 100_000 + 3 * MIN, early).state).toBe('soon')
    expect(adviseCache(last, '1h', 100_000 + 56 * MIN, early).state).toBe('soon')
    expect(adviseCache(last, '1h', 100_000 + 54 * MIN, early).state).toBe('warm')
  })
})

describe('numbers', () => {
  test('hit ratio is the cache share of the prompt', () => {
    expect(hitRatio(sample(0, 94, 4, 2))).toBe(0.94)
    expect(hitRatio(sample(0, 0, 0, 0))).toBeNull()
  })

  test('only the newest samples are kept', () => {
    const kept = [1, 2, 3].map(i => sample(i, 1, 0, 0))
    expect(keepSamples(kept, sample(4, 1, 0, 0), 3).map(s => s.startedAt)).toEqual([2, 3, 4])
  })
})
