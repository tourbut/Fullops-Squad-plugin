import { describe, expect, test } from 'claude-code/testing'

import type { FlowTask, Review, Worker } from '../types'
import { KEEP_FINISHED_MS, NODES, baseKey, flowRow, parseFlow, taskOf, visibleFlow } from './flow'

const MIN = 60_000

const task = (key: string, node: string, updated: number, rounds = 0): FlowTask => ({
  key,
  node: NODES.indexOf(node as (typeof NODES)[number]),
  rounds,
  budget: 2,
  updated,
})

const worker = (key: string, stage: number, extra: Partial<Worker> = {}): Worker => ({
  dispatchId: `d-${key}`,
  role: 'dev',
  key,
  phase: 'active',
  detail: '',
  since: 0,
  activity: 'working',
  isLive: true,
  needsAction: false,
  stage,
  stageAt: 0,
  progress: null,
  ...extra,
})

const review = (key: string, unresolved: number, worst: Review['worst']): Review => ({
  key,
  state: 'recorded',
  conclusion: '',
  unresolved,
  findings: unresolved,
  worst,
  at: 0,
})

describe('flow records', () => {
  test('reads what flow_state.py writes and turns down anything else', () => {
    const record = parseFlow(
      JSON.stringify({ key: 'K1', node: 'review', rounds: 1, budget: 2, sha: 'abc', gates: ['route'], updated: '2026-10-23T06:00:00+00:00' }),
    )
    expect(record).toEqual({ key: 'K1', node: NODES.indexOf('review'), rounds: 1, budget: 2, updated: Date.parse('2026-10-23T06:00:00Z') })
    expect(parseFlow(JSON.stringify({ key: 'K1', node: 'unknown' }))).toBe(null)
    expect(parseFlow('{')).toBe(null)
  })

  test('round and role-split keys belong to the task before them', () => {
    expect(baseKey('K1-FIX-DEV')).toBe('K1')
    expect(baseKey('K1-R2')).toBe('K1')
    expect(baseKey('K1-DEV')).toBe('K1-DEV')
  })

  test('a review key folds into its task as flow_state.task_of does: the role goes only when it is one', () => {
    const roles = ['coor', 'dev']
    expect(taskOf('K1-DEV-REVIEW-R2', roles)).toBe('K1')
    expect(taskOf('K1-review', roles)).toBe('K1')
    expect(taskOf('K1-FIX-DEV-REVIEW', roles)).toBe('K1')
    expect(taskOf('K1-API-REVIEW', roles)).toBe('K1-API')
    expect(taskOf('K1-FIX-DEV', roles)).toBe('K1')
    expect(taskOf('K1-DEV', roles)).toBe('K1-DEV')
    expect(taskOf('-REVIEW', roles)).toBe('-REVIEW')
  })

  test('tasks under way come first, newest first; merged ones leave after a while', () => {
    const now = 100 * MIN
    const tasks = [task('OLD', 'merge', now - KEEP_FINISHED_MS - 1), task('MERGED', 'merge', now - MIN), task('A', 'build', now - 9 * MIN), task('B', 'review', now - 2 * MIN)]
    expect(visibleFlow(tasks, now).map(one => one.key)).toEqual(['B', 'A', 'MERGED'])
  })
})

describe('flow rows', () => {
  test('draws the outer rail to the current node and the worker inner stages under it', () => {
    const row = flowRow(task('K1', 'build', MIN), [], [worker('K1-FIX', 1)], [], 6 * MIN)
    expect(row.rail).toEqual(['passed', 'passed', 'passed', 'current', 'ahead', 'ahead', 'ahead', 'ahead', 'ahead'])
    expect(row.label).toBe('build')
    expect(row.when).toBe('5m ago')
    expect(row.inner).toBe('dev ✔ explore ◉ build ○ verify ○ report')
    expect(row.flags).toEqual([])
  })

  test('says what holds a task in words and colour', () => {
    const row = flowRow(task('K1', 'review', 0, 3), [review('K1-FIX', 1, 'high'), review('K2', 2, 'critical')], [worker('K1', 2, { needsAction: true, isLive: false })], [], 0)
    expect(row.flags).toEqual([
      { text: '⚠ rounds 3/2', tone: 'warning' },
      { text: '✖ review blocked · high', tone: 'error' },
      { text: '⚠ needs you', tone: 'warning' },
      { text: '✖ agent gone', tone: 'error' },
    ])
    expect(flowRow(task('K3', 'review', 0), [review('K3', 1, 'low')], [], [], 0).flags).toEqual([])
  })

  test('a review key holds its task, whichever of the task\'s reviews and workers comes first', () => {
    const reviews = [review('K1', 1, 'low'), review('K1-DEV-REVIEW-R2', 1, 'high')]
    const workers = [worker('K1-FIX', 1), worker('K1-DEV-REVIEW', 0, { needsAction: true })]
    const row = flowRow(task('K1', 'review', 0), reviews, workers, ['dev'], 0)
    expect(row.flags).toEqual([
      { text: '✖ review blocked · high', tone: 'error' },
      { text: '⚠ needs you', tone: 'warning' },
    ])
    // A review key whose role part is no role is another task's.
    expect(flowRow(task('K1', 'review', 0), [review('K1-API-REVIEW', 1, 'high')], [], ['dev'], 0).flags).toEqual([])
  })

  test('the head and inner lines fit the 56-column pane', () => {
    const long = 'SAR-PUBLIC-MESSAGES-001-DEV-EXTRA'
    const row = flowRow(task(long, 'report', 0), [], [worker(long, 0, { role: 'designer' })], [], 59 * MIN)
    expect(row.key).toBe('SAR-PUBLIC-MESSAGES-001…')
    expect(`${row.key} ${'◉'.repeat(row.rail.length)} ${row.label} · ${row.when}`.length <= 56).toBe(true)
    expect(`  ${row.inner}`.length <= 56).toBe(true)
  })
})
