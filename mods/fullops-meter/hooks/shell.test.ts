import { describe, expect, test } from 'claude-code/testing'

import type { Shell } from '../types'
import { KEEP_SHELL, commandLine, isHookMessage, recordShell, shellLine, shellOutcome, tailOf } from './shell'

const entry = (id: string): Shell => ({ id, command: `cmd ${id}`, startedAt: 1_000, endedAt: null, status: 'running', tail: '' })

describe('shell records', () => {
  test('the newest call comes first, a repeated id is replaced, and the list is capped', () => {
    let list: Shell[] = []
    for (let n = 0; n < KEEP_SHELL + 3; n++) list = recordShell(list, entry(`c${n}`))
    expect(list.length).toBe(KEEP_SHELL)
    expect(list[0]?.id).toBe(`c${KEEP_SHELL + 2}`)
    const replaced = recordShell(list, { ...entry(`c${KEEP_SHELL + 2}`), status: 'ok' })
    expect(replaced.length).toBe(KEEP_SHELL)
    expect(replaced[0]?.status).toBe('ok')
  })

  test('the outcome reads deny, error, interruption and the output tail', () => {
    expect(shellOutcome(entry('a'), { deny: 'protected' }, 2_000)).toMatchObject({ status: 'denied', tail: 'protected', endedAt: 2_000 })
    expect(shellOutcome(entry('a'), { isError: true, text: 'exit 1\nmore' }, 2_000)).toMatchObject({ status: 'failed', tail: 'exit 1' })
    expect(shellOutcome(entry('a'), { result: { stdout: 'x\n', stderr: '', interrupted: true } }, 2_000)).toMatchObject({ status: 'interrupted', tail: 'x' })
    expect(shellOutcome(entry('a'), { result: { stdout: 'PASS\nexit=0\n', stderr: '' } }, 2_000)).toMatchObject({ status: 'ok', tail: 'exit=0' })
  })

  test('long commands and tails are cut, and only the first command line is kept', () => {
    expect(commandLine('\n  git status\n&& ls')).toBe('git status')
    expect(commandLine('x'.repeat(60))).toBe(`${'x'.repeat(47)}…`)
    expect(tailOf('', `${'y'.repeat(70)}\n`)).toBe(`${'y'.repeat(59)}…`)
    expect(tailOf('', '')).toBe('')
  })

  test('a hook message is one that names a hook', () => {
    expect(isHookMessage('Running Stop hook…')).toBe(true)
    expect(isHookMessage('Running PreToolUse hooks')).toBe(true)
    expect(isHookMessage('Compacting conversation')).toBe(false)
    expect(isHookMessage(null)).toBe(false)
  })

  test('a row shows the state, the elapsed time and the tail', () => {
    expect(shellLine(entry('a'), 61_000)).toMatchObject({ icon: '…', tone: 'claude', head: 'cmd a', when: '1:00 running', detail: '' })
    expect(shellLine({ ...entry('a'), endedAt: 4_000, status: 'failed', tail: 'boom' }, 9_000)).toMatchObject({ icon: '✖', tone: 'error', when: '0:03', detail: 'boom' })
  })
})
