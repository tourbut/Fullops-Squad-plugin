import { describe, expect, test } from 'claude-code/testing'

import type { Worker } from '../types'
import { branchOf, cardOf, checkoutRole, parseConfig, reviewLine, sortReviews, spinnerText, summarizeReview, words } from './fullops'

const config = parseConfig(JSON.stringify({ mode: 'coor', primary_role: 'coor', roles: { coor: 'fullops/coor', dev: 'fullops/dev' } }))

describe('which role a checkout plays', () => {
  test('a worker worktree on its role branch is that role', () => {
    expect(config).not.toBeNull()
    expect(checkoutRole(config!, branchOf('ref: refs/heads/fullops/dev\n'))).toBe('dev')
  })

  test('the main checkout on main is the primary role', () => {
    expect(checkoutRole(config!, branchOf('ref: refs/heads/main'))).toBe('coor')
    expect(checkoutRole(config!, branchOf('0123abcd'))).toBe('coor')
  })

  test('a repo without a primary role falls back to its mode', () => {
    expect(checkoutRole(parseConfig('{"mode":"dev","roles":{}}')!, 'main')).toBe('dev')
    expect(parseConfig('not json')).toBeNull()
    expect(parseConfig('42')).toBeNull()
    expect(parseConfig('[]')).toBeNull()
  })
})

describe('reviews', () => {
  const result = JSON.stringify({
    conclusion: 'Merge after the fix.\nDetails follow.',
    findings: [
      { severity: 'high', resolved: false },
      { severity: 'low', resolved: false },
      { severity: 'medium', resolved: true },
    ],
  })

  test('a recorded review names its worst open finding', () => {
    const review = summarizeReview('K1', result, null, 0)
    expect(review).toMatchObject({ state: 'recorded', findings: 3, unresolved: 2, worst: 'high' })
    expect(reviewLine(review, 5 * 60_000)).toEqual({ icon: '✖', tone: 'error', state: '2 open · high', when: '5m ago', detail: 'Merge after the fix.' })
  })

  test('a receipt outranks the record, and a folder with neither is open', () => {
    expect(summarizeReview('K2', result, 'superseded', 0).state).toBe('superseded')
    expect(summarizeReview('K3', null, 'waived', 0).state).toBe('waived')
    expect(reviewLine(summarizeReview('K3', null, 'waived', 0), 0)).toMatchObject({ icon: '–', tone: 'inactive', state: 'waived' })
    expect(reviewLine(summarizeReview('K4', null, null, 0), 0)).toMatchObject({ icon: '…', tone: 'claude', state: 'reviewing' })
  })

  test('a clean record is a tick, and open findings sort first', () => {
    const clean = summarizeReview('K5', JSON.stringify({ conclusion: 'Fine.', findings: [{ severity: 'low', resolved: true }] }), null, 9)
    expect(reviewLine(clean, 9)).toMatchObject({ icon: '✔', tone: 'success', state: '1 resolved', detail: 'Fine.' })
    const open = summarizeReview('K4', null, null, 1)
    const dirty = summarizeReview('K1', result, null, 0)
    expect(sortReviews([clean, open, dirty]).map(review => review.key)).toEqual(['K1', 'K4', 'K5'])
  })
})

describe('tool cards', () => {
  test('worker-start names the role, task key and agent', () => {
    const command = `orca orchestration worker-start --run R1 --spec "Task key: K7; Purpose: implementation" --worktree "D:/w/repo/dev" --agent claude`
    expect(cardOf(command, {})).toBe('start worker → dev K7 (claude)')
  })

  test('dispatch names the task by its key when the listing has it', () => {
    expect(cardOf('orca orchestration dispatch --task t-9 --to term-2', { 't-9': 'K9' })).toBe('dispatch K9 → term-2')
    expect(cardOf('orca orchestration dispatch --task t-9 --to term-2', {})).toBe('dispatch t-9 → term-2')
  })

  test('a FullOps script names its step', () => {
    expect(cardOf('python3 C:/p/fullops-squad/scripts/review.py prepare --repo . --key K1', {})).toBe('review prepare K1')
    expect(cardOf('python3 /p/scripts/orca_wait.py --orca orca --repo . --run R1', {})).toBe('wait for worker reports')
    expect(cardOf('python3 /p/scripts/orca_wait.py --repo . --settings', {})).toBe('read worker settings')
  })

  test('a second line, or orca not being the command run, keeps the row', () => {
    expect(cardOf('python3 /p/scripts/review.py prepare --key K1\nrm -rf build', {})).toBeNull()
    expect(cardOf('echo orca orchestration dispatch --task T --to dev', {})).toBeNull()
    expect(cardOf('ssh host orca orchestration worker-start --spec "Task key: K1"', {})).toBeNull()
    expect(cardOf('python3 -I /p/scripts/review.py need --repo .', {})).toBe('review need')
    expect(cardOf('python3 build.py /p/scripts/review.py', {})).toBeNull()
  })

  test('chains and other commands keep their own row', () => {
    expect(cardOf('cd x && python3 /p/scripts/review.py need --repo .', {})).toBeNull()
    expect(cardOf('orca orchestration worker-list --json', {})).toBeNull()
    expect(cardOf('git status', {})).toBeNull()
    expect(words('echo "a | b"')).toEqual(['echo', 'a | b'])
    expect(words('echo $(id)')).toBeNull()
  })
})

describe('spinner', () => {
  const worker = (phase: Worker['phase']): Worker => ({ dispatchId: phase, role: 'dev', key: 'K1', phase, detail: '', since: 0, activity: '', isLive: true, needsAction: false, stage: 0, progress: null })

  test('counts running workers and open reviews', () => {
    expect(spinnerText([worker('active'), worker('active'), worker('done')], [summarizeReview('K1', null, null, 0)])).toBe(
      '2 workers running · 1 review open',
    )
    expect(spinnerText(null, [])).toBe('')
  })
})
