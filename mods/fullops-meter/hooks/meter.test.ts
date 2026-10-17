import { describe, expect, test } from 'claude-code/testing'

import type { Meter, Sample, Worker } from '../types'
import { adviceText, bandLine, clock, contextText, missText, modelName, sessionHit, statusLine, tokens, workerBlock, workerLine } from './meter'

const MIN = 60_000
const policy = { warnMs: 60_000, compactAtTokens: 100_000 }

const sample = (startedAt: number, read: number, write: number, fresh: number): Sample => ({
  turnId: 't',
  index: 0,
  model: 'claude-opus-5-5',
  startedAt,
  read,
  write,
  fresh,
  output: 10,
})

const meter: Meter = {
  at: 0,
  context: { tokens: 124_000, window: 200_000, percent: 62, compactAt: 160_000 },
  samples: [sample(0, 900, 60, 40), sample(MIN, 940, 40, 20)],
  ttl: '1h',
  ttlSource: 'subscription default',
  model: 'claude-opus-5-5',
  effort: 'high',
  costUsd: 1.844,
  fiveHour: 23.5,
  workers: null,
}

describe('numbers', () => {
  test('tokens are short', () => {
    expect(tokens(950)).toBe('950')
    expect(tokens(12_345)).toBe('12.3k')
    expect(tokens(124_000)).toBe('124k')
    expect(tokens(1_250_000)).toBe('1.3M')
    expect(tokens(99_960)).toBe('100k')
    expect(tokens(999_960)).toBe('1.0M')
  })

  test('clock counts minutes and seconds, then hours, never below zero', () => {
    expect(clock(192_000)).toBe('3:12')
    expect(clock(59_001)).toBe('1:00')
    expect(clock(-5)).toBe('0:00')
    expect(clock(54 * MIN + 12_000)).toBe('54:12')
    expect(clock(3600_000 + 5 * MIN + 7_000)).toBe('1:05:07')
  })

  test('the model without its vendor prefix', () => {
    expect(modelName('claude-opus-5-5')).toBe('opus-5-5')
    expect(modelName(null)).toBe('-')
  })

  test('the context shows what is left', () => {
    expect(contextText(meter.context)).toBe('ctx 62% · 76.0k left')
    expect(contextText({ tokens: null, window: null, percent: null, compactAt: null })).toBe('ctx -')
  })
})

describe('status line', () => {
  test('model and effort, context left, last request hit rate and time until the cache lapses', () => {
    expect(statusLine(meter, 2 * MIN)).toBe('opus-5-5 high · ctx 62% · 76.0k left · cache 94% 59:00')
  })

  test('says when the cache lapsed', () => {
    expect(statusLine({ ...meter, ttl: '5m' }, 10 * MIN)).toBe('opus-5-5 high · ctx 62% · 76.0k left · cache 94% expired')
  })

  test('copes with no reading yet', () => {
    const empty: Meter = {
      ...meter,
      model: null,
      effort: null,
      context: { tokens: null, window: null, percent: null, compactAt: null },
      samples: [],
    }
    expect(statusLine(empty, 0)).toBe('- - · ctx - · cache - -')
  })
})

describe('band', () => {
  test('adds the margins, the session hit rate, cost and rate limit', () => {
    const line = bandLine(meter, 2 * MIN, policy)
    expect(line).toContain('opus-5-5 high (1h)')
    expect(line).toContain('context 62% (124k/200k) · 76.0k left')
    expect(line).toContain('36.0k to auto-compact')
    expect(line).toContain('cache 94% 59:00 (session 92%)')
    expect(line).toContain('$1.84')
    expect(line).toContain('5h 23.5%')
  })

  test('names a miss and, once lapsed, says the next message rereads it', () => {
    const missed: Meter = {
      ...meter,
      ttl: '5m',
      samples: [sample(0, 140_000, 0, 500), sample(10 * MIN, 0, 141_000, 500)],
    }
    const line = bandLine(missed, 20 * MIN, policy)
    expect(line).toContain('cache rewritten after expiry (10:00 gap)')
    expect(line).toContain('next message rereads 142k tokens at full price. /clear if done')
    expect(line).not.toContain('/compact now')
  })

  test('session hit rate counts every kept request', () => {
    expect(sessionHit(meter)).toBe(92)
    expect(sessionHit({ ...meter, samples: [] })).toBeNull()
  })

  test('advice and miss wording', () => {
    expect(adviceText({ state: 'warm', tokens: 10, shouldCompact: false })).toBe('')
    expect(adviceText({ state: 'soon', tokens: 10, shouldCompact: false })).toContain('keep working')
    expect(adviceText({ state: 'soon', tokens: 150_000, shouldCompact: true })).toBe(
      'expires soon: stepping away? /compact now, while 150k tokens are still cached',
    )
    expect(adviceText({ state: 'expired', tokens: 10, shouldCompact: false })).toContain('full price')
    expect(missText({ reason: 'model', gapMs: 0 })).toContain('model')
    expect(missText({ reason: 'prefix', gapMs: 0 })).toContain('CLAUDE.md')
  })
})

describe('worker line', () => {
  const worker = (phase: Worker['phase'], role: string, key: string, since = 0, detail = ''): Worker => ({
    dispatchId: `${role}${key}`,
    role,
    key,
    phase,
    detail,
    since,
    activity: '',
    isLive: true,
    needsAction: false,
    stage: 0,
    progress: null,
  })

  test('shows nothing without workers', () => {
    expect(workerLine(null, 0)).toBe('')
    expect(workerLine([], 0)).toBe('')
  })

  test('a running worker shows its age, a failed one its reason', () => {
    const line = workerLine(
      [worker('active', 'dev', 'K1', 0), worker('done', 'tester', 'K2'), worker('failed', 'ops', 'K3', 0, 'process_exited')],
      12 * MIN,
    )
    expect(line).toBe('worker ▶ dev K1 12m · ✔ tester K2 · ✖ ops K3 process_exited')
  })

  test('long lists are cut with a count', () => {
    const many = ['a', 'b', 'c', 'd', 'e', 'f'].map(role => worker('active', role, ''))
    expect(workerLine(many, MIN)).toContain('· +2')
  })
})

describe('worker block', () => {
  test('a running worker shows its activity, last words, steps and how long ago', () => {
    const block = workerBlock(
      {
        dispatchId: 'd',
        role: 'designer',
        key: 'K1',
        phase: 'active',
        detail: '',
        since: 0,
        activity: 'working',
        isLive: true,
        needsAction: true,
        stage: 1,
        progress: { said: 'Docs updated.', steps: ['Edit report.md', 'Bash: Run lint'], at: 2 * MIN - 40_000 },
      },
      2 * MIN,
    )
    expect(block.head).toBe('▶ designer K1 2m · working · ⚠ waiting on you')
    expect(block.lines).toEqual(['“Docs updated.”', '› Edit report.md', '› Bash: Run lint', 'last activity 40s ago'])
  })
})
