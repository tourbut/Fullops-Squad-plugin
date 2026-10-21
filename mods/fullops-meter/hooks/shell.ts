import type { Shell } from '../types'
import { clock } from './meter'

/** Calls the Shell tab keeps, newest first. */
export const KEEP_SHELL = 20
/** How much of a command the tab shows. */
const COMMAND_WIDTH = 48
/** How much of the output's last line the tab shows. */
const TAIL_WIDTH = 60

const cut = (line: string, width: number): string => (line.length > width ? `${line.slice(0, width - 1)}…` : line)

/** The command's first non-empty line, cut to fit the tab. */
export const commandLine = (command: string): string =>
  cut(command.split('\n').map(l => l.trim()).find(l => l !== '') ?? '', COMMAND_WIDTH)

/** A spinner message that tells of a settings hook running (`Running Stop hook…`, `Running PreToolUse hooks`). */
export const isHookMessage = (message: string | null): message is string => message !== null && /\bhooks?\b/i.test(message)

/** The list with `entry` at its head; an earlier record of the same call is replaced. */
export const recordShell = (list: Shell[], entry: Shell): Shell[] => [entry, ...list.filter(s => s.id !== entry.id)].slice(0, KEEP_SHELL)

/** The output's last non-empty line, stderr after stdout. */
export const tailOf = (stdout: string, stderr: string): string => {
  const lines = `${stdout}\n${stderr}`.split('\n').map(l => l.trim()).filter(l => l !== '')
  return cut(lines[lines.length - 1] ?? '', TAIL_WIDTH)
}

/** What `tool.call` answered, reduced to what the tab shows. */
export type Outcome = {
  deny?: string
  isError?: boolean
  text?: string
  result?: { stdout?: string; stderr?: string; interrupted?: boolean } | unknown
}

/** The record once the call has answered. */
export const shellOutcome = (entry: Shell, ran: Outcome, endedAt: number): Shell => {
  if (ran.deny !== undefined) return { ...entry, endedAt, status: 'denied', tail: cut(ran.deny, TAIL_WIDTH) }
  const result = typeof ran.result === 'object' && ran.result !== null ? (ran.result as { stdout?: string; stderr?: string; interrupted?: boolean }) : {}
  const tail = tailOf(result.stdout ?? '', result.stderr ?? '') || cut((ran.text ?? '').trim().split('\n')[0] ?? '', TAIL_WIDTH)
  const status = result.interrupted === true ? 'interrupted' : ran.isError === true ? 'failed' : 'ok'
  return { ...entry, endedAt, status, tail }
}

const MARK: Record<Shell['status'], { icon: string; tone: 'claude' | 'success' | 'error' | 'warning' }> = {
  running: { icon: '…', tone: 'claude' },
  ok: { icon: '✔', tone: 'success' },
  failed: { icon: '✖', tone: 'error' },
  interrupted: { icon: '!', tone: 'warning' },
  denied: { icon: '✖', tone: 'error' },
}

/** One row of the Shell tab. */
export const shellLine = (shell: Shell, now: number): { icon: string; tone: 'claude' | 'success' | 'error' | 'warning'; head: string; when: string; detail: string } => ({
  ...MARK[shell.status],
  head: shell.command,
  when: shell.endedAt === null ? `${clock(now - shell.startedAt)} running` : clock(shell.endedAt - shell.startedAt),
  detail: shell.tail,
})
