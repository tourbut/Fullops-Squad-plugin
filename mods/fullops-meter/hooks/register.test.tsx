import { expect, mock, test } from 'claude-code/testing'

const DECISION = 'wt/shared/fullops-decisions/D1.json'

const decision = (status: string) => JSON.stringify({ id: 'D1', status, question: 'Ship it?', asked_at: '2026-10-17T09:00:00+00:00' })

const PANE = {
  plugin: 'fullops-meter',
  surface: 'terminal',
  component: 'Pane',
  requestId: 'fullops',
  props: { title: 'FullOps', isFocused: false, bodyColumns: 56, placement: 'dock', scroll: { offset: 0, bodyRows: 40 }, view: {} },
} as const

test('a refresh looks up the git folders once a minute and rereads a record only when it changed', async ($, on) => {
  const clock = mock.clock(on, { now: 1_000_000 })
  const files: Record<string, string> = {
    '.fullops-squad/fullops.json': JSON.stringify({ roles: { dev: 'fullops/dev' } }),
    '.git': 'gitdir: wt\n',
    'wt/commondir': 'shared\n',
    'wt/HEAD': 'ref: refs/heads/fullops/dev\n',
    [DECISION]: decision('open'),
  }
  let mtimeMs = 1
  const reads: string[] = []
  const count = (name: string) => reads.filter(one => one === name).length
  // The engine hands a hook the path made absolute.
  const nameOf = (path: string) => Object.keys(files).find(name => path.replace(/\\/g, '/').endsWith(`/${name}`))

  on('session.start', (_, e) => ({ cwd: e.cwd }))
  on('command.register', () => ({ value: { command: 'x' } }))
  on('ui.status', () => ({ value: undefined }))
  on('env.get', () => ({ value: undefined }))
  on('process.run', () => ({ value: { exitCode: 1, stdout: '', stderr: '', isStdoutTruncated: false, isStderrTruncated: false } }))
  on('fs.exists', (_, e) => ({ value: nameOf(e.path) !== undefined }))
  on('fs.read', (_, e) => {
    const name = nameOf(e.path)
    if (name === undefined) throw new Error('no such file')
    reads.push(name)
    return { value: files[name] ?? '' }
  })
  on('fs.list', (_, e) => ({
    value: e.path.replace(/\\/g, '/').endsWith('wt/shared/fullops-decisions') ? [{ name: 'D1.json', kind: 'file', size: 100, mtimeMs, isLink: false }] : [],
  }))

  await $.session.start({ cwd: '.', surface: 'terminal', isInteractive: true })
  await clock.advance(30_000)
  // The first poll and two more: the locations once, HEAD each time, the unchanged record once.
  expect(count('.git')).toBe(1)
  expect(count('wt/commondir')).toBe(1)
  expect(count('wt/HEAD')).toBe(3)
  expect(count(DECISION)).toBe(1)

  const ui = await $.ui.mount(PANE)
  expect((await ui.find({ type: 'Text', text: /Ship it\?/ }))?.text).toContain('Ship it?')

  // An answered decision leaves on the next refresh, not when any cache lapses.
  files[DECISION] = decision('answered')
  mtimeMs = 2
  await clock.advance(15_000)
  expect(count(DECISION)).toBe(2)
  expect(await ui.find({ type: 'Text', text: /Ship it\?/ })).toBeUndefined()
  await ui.unmount()

  await clock.advance(30_000)
  expect(count('.git')).toBe(2)
})
