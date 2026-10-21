import type { HookRun } from '../types'
import { ago, clock } from './meter'

/** The settings hook events FullOps Squad's hooks.json hooks. */
export const HOOK_EVENTS: ReadonlySet<string> = new Set(['SessionStart', 'UserPromptSubmit', 'PreToolUse', 'PostToolUse', 'Stop', 'SessionEnd'])
/** Runs the pane keeps, newest first. */
export const KEEP_HOOKS = 30
/** Blocked runs the pane lists before it only counts. */
const SHOW_BLOCKED = 5
const DETAIL_WIDTH = 70

const cut = (line: string, width: number): string => (line.length > width ? `${line.slice(0, width - 1)}…` : line)

/** The list with `run` at its head; an earlier record of the same run is replaced. */
export const recordHookRun = (list: HookRun[], run: HookRun): HookRun[] => [run, ...list.filter(r => r.id !== run.id)].slice(0, KEEP_HOOKS)

/** The run once its chain has answered: `block` (Stop and the rest) or `deny` (PreToolUse) carries the reason. */
export const hookOutcome = (run: HookRun, result: unknown, endedAt: number): HookRun => {
  const answer = typeof result === 'object' && result !== null ? (result as { block?: unknown; deny?: unknown }) : {}
  const reason = [answer.block, answer.deny].find((r): r is string => typeof r === 'string') ?? ''
  return { ...run, endedAt, status: reason === '' ? 'ok' : 'blocked', detail: cut(reason.trim().split('\n')[0] ?? '', DETAIL_WIDTH) }
}

export type HookLine = { icon: string; tone: 'claude' | 'success' | 'error'; text: string; detail: string }

/** The Hooks block: running hooks, the latest blocked runs, then one count of the passed ones. */
export const hookLines = (list: HookRun[], now: number): HookLine[] => {
  const lines: HookLine[] = list
    .filter(r => r.status === 'running')
    .map(r => ({ icon: '…', tone: 'claude', text: `${r.event} running ${clock(now - r.startedAt)}`, detail: '' }))
  for (const r of list.filter(r => r.status === 'blocked').slice(0, SHOW_BLOCKED)) {
    lines.push({ icon: '✖', tone: 'error', text: `${r.event} blocked · ${clock((r.endedAt ?? now) - r.startedAt)} · ${ago(now - (r.endedAt ?? now))} ago`, detail: r.detail })
  }
  const passed = new Map<string, number>()
  for (const r of list) if (r.status === 'ok') passed.set(r.event, (passed.get(r.event) ?? 0) + 1)
  if (passed.size > 0) lines.push({ icon: '✔', tone: 'success', text: `passed: ${[...passed].map(([event, n]) => `${event} ×${n}`).join(' · ')}`, detail: '' })
  return lines
}
