import { describe, expect, test } from 'claude-code/testing'

import type { Seen, Worker } from '../types'
import { KEEP_FINISHED_MS, STAGES, STALL_MS, declaredKey, keyOf, noticesOf, parseProgress, parseRows, parseRunId, parseTasks, phaseOf, reconcile, roleOf, stageOf, stageOfRecords, stageOfStep } from './workers'
import type { Row } from './workers'

const row = (dispatchId: string, phase: Row['phase'], workspace = 'repo::C:/orca/repo/dev'): Row => ({
  dispatchId,
  taskId: `task_${dispatchId}`,
  phase,
  detail: '',
  workspace,
  activity: '',
  isLive: true,
  needsAction: false,
})

describe('reading Orca', () => {
  test('worker and dispatch state become a phase, and an unknown state reads as running', () => {
    expect(phaseOf('succeeded', 'completed')).toBe('done')
    expect(phaseOf('failed', 'failed')).toBe('failed')
    expect(phaseOf('stopped', 'failed')).toBe('stopped')
    expect(phaseOf('running', 'active')).toBe('active')
    expect(phaseOf('something-new', 'also-new')).toBe('active')
  })

  test('the task key is the declared one, else the first word', () => {
    expect(keyOf('Task key: SAR-UX-1; Purpose: review')).toBe('SAR-UX-1')
    expect(keyOf('Task key=K1.')).toBe('K1')
    expect(keyOf('K2 implement the thing')).toBe('K2')
    expect(keyOf('')).toBe('')
    expect(declaredKey('the task keys below are K1 and K2')).toBe('')
  })

  test('the role is the worktree folder', () => {
    expect(roleOf('repo-1::C:/Users/me/orca/workspaces/KnowsLink/dev')).toBe('dev')
    expect(roleOf('C:\\orca\\KnowsLink\\tester\\')).toBe('tester')
    expect(roleOf('')).toBe('')
    expect(roleOf('repo-1::C:/orca/KnowsLink/.fullops-review-c64b790767fa4dcd')).toBe('reviewer')
  })

  test('worker-list, task-list and run-current output', () => {
    const list = JSON.stringify({
      ok: true,
      result: {
        workers: [
          {
            dispatchId: 'ctx_1',
            taskId: 'task_1',
            workerState: 'failed',
            dispatchStatus: 'failed',
            projection: {
              stage: { detail: 'process_exited', activity: 'done' },
              workspace: { id: 'r::C:/o/KnowsLink/ops' },
              liveness: { verdict: 'dead' },
              attention: { requiresAction: true },
            },
          },
        ],
      },
    })
    expect(parseRows(list)).toEqual([
      {
        dispatchId: 'ctx_1',
        taskId: 'task_1',
        phase: 'failed',
        detail: 'process_exited',
        workspace: 'r::C:/o/KnowsLink/ops',
        activity: 'done',
        isLive: false,
        needsAction: true,
      },
    ])
    expect(parseRows('not json')).toEqual([])
    expect(
      parseTasks(
        JSON.stringify({
          result: {
            tasks: [
              { id: 'task_1', spec: 'Task key: K9', status: 'completed', dispatch_id: 'ctx_1' },
              { id: 'task_2', spec: 'Task key: K10', status: 'pending', dispatch_id: null },
              { id: 'task_3', spec: 'Task key: K11', status: 'cancelled', dispatch_id: null },
            ],
          },
        }),
      ),
    ).toEqual({ keys: { task_1: 'K9', task_2: 'K10', task_3: 'K11' }, queued: ['K10'] })
    expect(parseTasks('nope')).toEqual({ keys: {}, queued: [] })
    expect(parseRunId(JSON.stringify({ result: { run: { id: 'run_a' } } }))).toBe('run_a')
    expect(parseRunId(JSON.stringify({ result: { run: null } }))).toBeNull()
    expect(parseRunId('')).toBeNull()
  })
})

describe('which workers show', () => {
  const MIN = 60_000

  test('work that was already finished when the mod first looked never shows', () => {
    const first = reconcile({}, [row('old', 'done'), row('now', 'active')], { task_now: 'K1' }, 1000, true)
    expect(first.workers.map(w => w.dispatchId)).toEqual(['now'])
    expect(first.workers[0]?.key).toBe('K1')
    expect(first.workers[0]?.role).toBe('dev')
    expect(first.seen.old?.isBaseline).toBe(true)
  })

  test('a worker that finishes after that shows for a while, then leaves', () => {
    const first = reconcile({}, [row('w', 'active')], {}, 0, true)
    const done = reconcile(first.seen, [row('w', 'done')], {}, 5 * MIN, false)
    expect(done.workers.map(w => w.phase)).toEqual(['done'])
    expect(done.workers[0]?.since).toBe(5 * MIN)
    const later = reconcile(done.seen, [row('w', 'done')], {}, 5 * MIN + KEEP_FINISHED_MS + 1, false)
    expect(later.workers).toEqual([])
  })

  test('a new dispatch that is already done after the first look still shows', () => {
    const first = reconcile({}, [], {}, 0, true)
    const next = reconcile(first.seen, [row('quick', 'done')], {}, MIN, false)
    expect(next.workers.map(w => w.dispatchId)).toEqual(['quick'])
  })

  test('active work comes first, then the most recent change', () => {
    const seen: Seen = {}
    const result = reconcile(
      seen,
      [row('a', 'failed'), row('b', 'active'), row('c', 'done')],
      {},
      10,
      false,
    )
    expect(result.workers.map(w => w.dispatchId)).toEqual(['b', 'a', 'c'])
  })
})

describe('what to tell', () => {
  const worker = (dispatchId: string, phase: Row['phase'], needsAction = false, said = ''): Worker => ({
    dispatchId,
    role: 'dev',
    key: 'K1',
    phase,
    detail: phase === 'failed' ? 'process_exited' : '',
    since: 0,
    activity: '',
    isLive: true,
    needsAction,
    stage: 1,
    stageAt: 0,
    progress: said === '' ? null : { said, steps: [], at: 1 },
  })
  const seen = (phase: Row['phase'], needsAction = false): Seen => ({ a: { phase, since: 0, isBaseline: false, needsAction } })

  test('a worker that finished, or now waits on someone, is told once', () => {
    expect(noticesOf(seen('active'), [worker('a', 'done')], 0, 0)).toEqual(['dev K1 done'])
    expect(noticesOf(seen('active'), [worker('a', 'failed')], 0, 0)).toEqual(['dev K1 failed: process_exited'])
    expect(noticesOf({}, [worker('a', 'done')], 0, 0)).toEqual(['dev K1 done'])
    expect(noticesOf(seen('done'), [worker('a', 'done')], 0, 0)).toEqual([])
    expect(noticesOf(seen('active'), [worker('a', 'active', true, 'Merge now?')], 0, 0)).toEqual(['dev K1 waiting on you: Merge now?'])
    expect(noticesOf(seen('active', true), [worker('a', 'active', true, 'Merge now?')], 0, 0)).toEqual([])
    expect(noticesOf(seen('active'), [worker('a', 'active')], 0, 0)).toEqual([])
  })

  test('a worker stuck in a stage is told of when it crosses the limit, and a finished one never', () => {
    expect(noticesOf(seen('active'), [worker('a', 'active')], STALL_MS - 1, STALL_MS)).toEqual(['dev K1 in build for 30m'])
    expect(noticesOf(seen('active'), [worker('a', 'active')], STALL_MS, STALL_MS + 15_000)).toEqual([])
    expect(noticesOf(seen('active'), [worker('a', 'active')], 0, STALL_MS - 1)).toEqual([])
    expect(noticesOf(seen('done'), [worker('a', 'done')], 0, 2 * STALL_MS)).toEqual([])
  })
})

describe('worker progress', () => {
  const transcript = (messages: unknown[]) => JSON.stringify({ result: { transcript: { messages } } })

  test('keeps the last words, the latest tool calls and the newest time', () => {
    const progress = parseProgress(
      transcript([
        { role: 'assistant', timestamp: 10, blocks: [{ type: 'tool-call', name: 'Read', input: { file_path: 'C:\\repo\\a.md' } }] },
        { role: 'tool', timestamp: 20, blocks: [{ type: 'tool-result', output: 'x' }] },
        { role: 'assistant', timestamp: 30, blocks: [{ type: 'text', text: 'Docs updated; now running checks.\nmore' }] },
        { role: 'assistant', timestamp: 40, blocks: [{ type: 'tool-call', name: 'Bash', input: { command: 'npm test\necho', description: '' } }] },
        { role: 'assistant', timestamp: 50, blocks: [{ type: 'tool-call', name: 'Edit', input: { file_path: '/repo/report.md' } }] },
        { role: 'assistant', timestamp: 60, blocks: [{ type: 'tool-call', name: 'Bash', input: { command: 'x', description: 'Run lint' } }] },
      ]),
    )
    expect(progress).toEqual({
      said: 'Docs updated; now running checks.',
      steps: ['Read a.md', 'Bash: npm test', 'Edit report.md', 'Bash: Run lint'],
      at: 60,
    })
  })

  test('anything else reads as no progress', () => {
    expect(parseProgress('nope')).toBeNull()
    expect(parseProgress('{"result":{}}')).toBeNull()
  })
})

describe('worker stages', () => {
  test('each tool call maps to the main step it serves', () => {
    expect(stageOfStep('Read a.md')).toBe(0)
    expect(stageOfStep('Bash: git status')).toBe(0)
    expect(stageOfStep('Edit report.md')).toBe(1)
    expect(stageOfStep('Write register.test.ts')).toBe(1)
    expect(stageOfStep('Bash: Run FullOps lint at current SHA')).toBe(2)
    expect(stageOfStep('Bash: Validate the plugin manifest and hooks module')).toBe(2)
    expect(stageOfStep('Bash: Archive the instruction and completion report with work.py')).toBe(3)
    expect(stageOfStep('Bash: python3 /p/scripts/orca_wait.py --run R1')).toBe(3)
  })

  test('the checkout records prove verify and report, but only files newer than the dispatch count', () => {
    const gate = [{ name: 'lint-result.json', mtimeMs: 50 }]
    const logs = [{ name: '2026-10-17_to_dev.md', mtimeMs: 70 }]
    expect(stageOfRecords(gate, [], 'dev', 10)).toBe(2)
    expect(stageOfRecords([{ name: 'pass.json', mtimeMs: 50 }], [], 'dev', 10)).toBe(2)
    expect(stageOfRecords(gate, logs, 'dev', 10)).toBe(3)
    expect(stageOfRecords(gate, logs, 'tester', 10)).toBe(2)
    expect(stageOfRecords(gate, logs, 'dev', 60)).toBe(3)
    expect(stageOfRecords(gate, logs, 'dev', 80)).toBe(0)
    expect(stageOfRecords([{ name: 'other.json', mtimeMs: 50 }], [], 'dev', 10)).toBe(0)
  })

  test('the stage never goes back while a worker re-reads files', () => {
    expect(stageOf(['Edit a.ts', 'Bash: npm test'], 0)).toBe(2)
    expect(stageOf(['Read a.ts', 'Grep x'], 2)).toBe(2)
    expect(stageOf([], 1)).toBe(1)
    expect(STAGES).toEqual(['explore', 'build', 'verify', 'report'])
  })
})
