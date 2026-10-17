import type { Review, Worker } from '../types'
import { asRecord, declaredKey, text } from './workers'

export type Config = { mode: string; primaryRole: string | null; roles: Record<string, string> }

/** `.fullops-squad/fullops.json`, or null when it is not one. */
export const parseConfig = (source: string): Config | null => {
  let parsed: unknown
  try {
    parsed = JSON.parse(source)
  } catch {
    return null
  }
  const config = asRecord(parsed)
  const roles: Record<string, string> = {}
  for (const [role, branch] of Object.entries(asRecord(config.roles))) {
    if (typeof branch === 'string') roles[role] = branch
  }
  return { mode: text(config.mode) || 'coor', primaryRole: text(config.primary_role) || null, roles }
}

/** `ref: refs/heads/fullops/dev` to `fullops/dev`; null for a detached HEAD. */
export const branchOf = (head: string): string | null => /^ref:\s*refs\/heads\/(\S+)/.exec(head.trim())?.[1] ?? null

/** The role this checkout plays: the role whose branch it is on, else the repo's primary role. */
export const checkoutRole = (config: Config, branch: string | null): string => {
  const own = Object.entries(config.roles).find(([, roleBranch]) => roleBranch === branch)?.[0]
  return own ?? config.primaryRole ?? config.mode
}

const SEVERITIES = ['critical', 'high', 'medium', 'low'] as const

/** The receipt files `review.py` leaves in a review folder, strongest first. */
export const MARKERS = [
  ['superseded.json', 'superseded'],
  ['abandoned.json', 'abandoned'],
  ['waiver.json', 'waived'],
] as const

export type Marker = (typeof MARKERS)[number][1]

/** One `<key>-review` folder: its `result.json` text when written, and the strongest receipt beside it. */
export const summarizeReview = (key: string, result: string | null, marker: Marker | null, at: number): Review => {
  if (marker === 'superseded' || marker === 'abandoned' || result === null) {
    return { key, state: marker ?? 'open', conclusion: '', unresolved: 0, findings: 0, worst: null, at }
  }
  let parsed: unknown
  try {
    parsed = JSON.parse(result)
  } catch {
    parsed = {}
  }
  const record = asRecord(parsed)
  const findings = Array.isArray(record.findings) ? record.findings.map(asRecord) : []
  const open = findings.filter(finding => finding.resolved !== true)
  const worst = SEVERITIES.find(severity => open.some(finding => finding.severity === severity)) ?? null
  return {
    key,
    state: 'recorded',
    conclusion: text(record.conclusion).split(/\r?\n/)[0]?.trim() ?? '',
    unresolved: open.length,
    findings: findings.length,
    worst,
    at,
  }
}

/** Splits a shell command into words; null when it chains, pipes or redirects, so only a single command gets a card. */
export const words = (command: string): string[] | null => {
  const out: string[] = []
  let word = ''
  let isWord = false
  let quote: '"' | "'" | null = null
  for (let i = 0; i < command.length; i++) {
    const char = command[i] ?? ''
    if (quote !== null) {
      if (char === quote) quote = null
      else if (char === '\\' && quote === '"' && i + 1 < command.length) word += command[++i]
      else word += char
      continue
    }
    if (char === '"' || char === "'") {
      quote = char
      isWord = true
    } else if (/[;&|<>`\r\n]/.test(char) || (char === '$' && command[i + 1] === '(')) {
      // A newline runs a second command, so it counts as a chain too; checked before plain whitespace.
      return null
    } else if (/\s/.test(char)) {
      if (isWord) out.push(word)
      word = ''
      isWord = false
    } else {
      word += char
      isWord = true
    }
  }
  if (quote !== null) return null
  if (isWord) out.push(word)
  return out
}

const flag = (args: readonly string[], name: string): string => {
  const at = args.indexOf(name)
  return at === -1 ? '' : (args[at + 1] ?? '')
}

const lastPart = (path: string): string => path.replace(/[\\/]+$/, '').split(/[\\/]/).pop() ?? ''

/**
 * The one-line card for a FullOps step a Bash call runs, or null for any other command.
 * Only the command that runs counts (`echo orca ...` or `ssh host orca ...` is no Orca step).
 * `keys` maps an Orca task id to its task key, from the coordinator's last listing.
 */
export const cardOf = (command: string, keys: Readonly<Record<string, string>>): string | null => {
  const args = words(command)
  if (args === null || args.length === 0) return null

  if (lastPart(args[0] ?? '').replace(/\.(exe|cmd)$/i, '') === 'orca' && args[1] === 'orchestration') {
    const verb = args[2] ?? ''
    const rest = args.slice(3)
    if (verb === 'worker-start') {
      const role = lastPart(flag(rest, '--worktree'))
      const key = declaredKey(flag(rest, '--spec'))
      const agent = flag(rest, '--agent')
      return `start worker → ${[role || flag(rest, '--terminal'), key].filter(Boolean).join(' ')}${agent === '' ? '' : ` (${agent})`}`
    }
    if (verb === 'dispatch') {
      const task = flag(rest, '--task')
      return `dispatch ${keys[task] || task} → ${flag(rest, '--to')}`
    }
    return null
  }

  // The script is the interpreter's first non-flag word (`python3 -I .../scripts/review.py`).
  const script = args.findIndex((arg, at) => at > 0 && !arg.startsWith('-'))
  if (!/^(python3?|py)(\.exe)?$/i.test(lastPart(args[0] ?? '')) || !/[\\/]scripts[\\/][a-z_]+\.py$/.test(args[script] ?? '')) return null
  const name = lastPart(args[script] ?? '').replace(/\.py$/, '')
  if (name === 'orca_wait') return args.includes('--settings') ? 'read worker settings' : 'wait for worker reports'
  const rest = args.slice(script + 1)
  const mode = rest[0] !== undefined && !rest[0].startsWith('-') ? rest[0] : ''
  const key = flag(rest, '--key') || flag(rest, '--id')
  return [name.replace(/_/g, ' '), mode, key].filter(Boolean).join(' ')
}

/** What the spinner adds while the coordinator has workers out or reviews open; empty for nothing. */
export const spinnerText = (workers: readonly Worker[] | null, reviews: readonly Review[]): string => {
  const running = (workers ?? []).filter(worker => worker.phase === 'active').length
  const open = reviews.filter(review => review.state === 'open').length
  const parts = [
    running > 0 ? `${running} worker${running === 1 ? '' : 's'} running` : '',
    open > 0 ? `${open} review${open === 1 ? '' : 's'} open` : '',
  ].filter(Boolean)
  return parts.join(' · ')
}

/** Reviewers write paragraph-long conclusions; the pane shows the start. */
const CONCLUSION_CHARS = 80

/** One review in the pane:`K1 recorded · 1 open (high) · <conclusion>`. */
export const reviewText = (review: Review): string => {
  if (review.state !== 'recorded') return `${review.key} ${review.state}`
  const findings = review.findings === 0 ? 'no findings' : review.unresolved === 0 ? `${review.findings} resolved` : `${review.unresolved} open (${review.worst})`
  const conclusion = review.conclusion.length > CONCLUSION_CHARS ? `${review.conclusion.slice(0, CONCLUSION_CHARS - 1)}…` : review.conclusion
  return [`${review.key} recorded`, findings, conclusion].filter(Boolean).join(' · ')
}
