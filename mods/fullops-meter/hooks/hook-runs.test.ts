import { describe, expect, test } from 'claude-code/testing'

import type { HookRun } from '../types'
import { KEEP_HOOKS, hookLines, hookOutcome, recordHookRun } from './hook-runs'

const run = (id: string, event = 'Stop'): HookRun => ({ id, event, startedAt: 1_000, endedAt: null, status: 'running', detail: '' })

describe('hook runs', () => {
  test('the newest run comes first, a repeated id is replaced, and the list is capped', () => {
    let list: HookRun[] = []
    for (let n = 0; n < KEEP_HOOKS + 2; n++) list = recordHookRun(list, run(`r${n}`))
    expect(list.length).toBe(KEEP_HOOKS)
    expect(list[0]?.id).toBe(`r${KEEP_HOOKS + 1}`)
    expect(recordHookRun(list, { ...run(`r${KEEP_HOOKS + 1}`), status: 'ok' })[0]?.status).toBe('ok')
  })

  test('the outcome reads a block, a deny or a pass', () => {
    expect(hookOutcome(run('a'), { block: 'FullOps: lint first\nmore' }, 3_000)).toMatchObject({ status: 'blocked', detail: 'FullOps: lint first', endedAt: 3_000 })
    expect(hookOutcome(run('a', 'PreToolUse'), { deny: 'FullOps: no' }, 3_000)).toMatchObject({ status: 'blocked', detail: 'FullOps: no' })
    expect(hookOutcome(run('a'), {}, 3_000)).toMatchObject({ status: 'ok', detail: '' })
    expect(hookOutcome(run('a'), undefined, 3_000).status).toBe('ok')
  })

  test('the block lists running and blocked runs and counts the passed ones', () => {
    const list: HookRun[] = [
      run('x'),
      { ...run('b'), endedAt: 2_000, status: 'blocked', detail: 'FullOps: lint first' },
      { ...run('p1', 'PreToolUse'), endedAt: 1_500, status: 'ok' },
      { ...run('p2', 'PreToolUse'), endedAt: 1_500, status: 'ok' },
      { ...run('s'), endedAt: 1_500, status: 'ok' },
    ]
    const lines = hookLines(list, 5_000)
    expect(lines.map(l => l.text)).toEqual(['Stop running 0:04', 'Stop blocked · 0:01 · 3s ago', 'passed: PreToolUse ×2 · Stop ×1'])
    expect(lines[1]?.detail).toBe('FullOps: lint first')
    expect(hookLines([], 5_000)).toEqual([])
  })
})
