import type { ClientModule, Color } from 'claude-code'

/** One worker as the cards draw it: plain data, handed in from the hooks module. */
export type Card = {
  id: string
  role: string
  key: string
  phase: 'active' | 'done' | 'failed' | 'stopped'
  /** Index into `stages`, or `stages.length` when done. */
  stage: number
  since: number
  /** When the worker last did anything; 0 when unknown. */
  lastAt: number
  needsAction: boolean
  isLive: boolean
}

export type CardsProps = { now: number; stages: string[]; workers: Card[] }

type State = { frame: number; now: number; nowFrame: number }

const FRAME_MS = 120
const SPINNER = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏']
const FLOW = ['▸┄┄', '┄▸┄', '┄┄▸']
/** A worker silent this long is flagged as idle. */
const IDLE_MS = 5 * 60_000
/** The width the pane asks for, used before the first layout reports one. */
const PANE_COLUMNS = 56

const ROLE_COLORS: Record<string, Color> = {
  coor: 'claude',
  dev: 'suggestion',
  designer: 'merged',
  tester: 'autoAccept',
  ops: 'warning',
  reviewer: 'permission',
}

const roleColor = (role: string): Color => ROLE_COLORS[role] ?? 'ide'

const clock = (ms: number): string => {
  const minutes = Math.floor(Math.max(0, ms) / 60_000)
  const seconds = Math.floor((Math.max(0, ms) % 60_000) / 1000)
  return minutes >= 60 ? `${Math.floor(minutes / 60)}h${String(minutes % 60).padStart(2, '0')}m` : `${minutes}:${String(seconds).padStart(2, '0')}`
}

/** `text` cut to `width` cells with an ellipsis: a wrapped key breaks the card in a narrow pane. */
export const fit = (text: string, width: number): string => {
  if (width <= 0) return ''
  if (text.length <= width) return text
  return width === 1 ? '…' : `${text.slice(0, width - 1)}…`
}

/** Cells the full rail takes: each stage as `✔ label`, joined by three-cell links. */
export const railWidth = (stages: readonly string[]): number =>
  [...stages, 'done'].reduce((sum, label) => sum + label.length + 2, 0) + stages.length * 3

/** Draws the coordinator's workers as cards with a stage rail that animates while they run. */
const WorkerCards: ClientModule<CardsProps, State> = (props, surface) => {
  const { Box, Text } = surface.elements
  const state = surface.state ?? { frame: 0, now: props.now, nowFrame: 0 }
  if (surface.state === undefined) {
    surface.setState(state)
    surface.every(FRAME_MS, () => {
      const last = surface.state ?? state
      surface.setState({ ...last, frame: last.frame + 1 })
    })
  }
  // The hooks module hands a new `now` every poll; the frames count the time since.
  const isNewNow = state.now !== props.now
  const now = props.now + (isNewNow ? 0 : (state.frame - state.nowFrame) * FRAME_MS)
  if (isNewNow) surface.setState({ ...state, now: props.now, nowFrame: state.frame })
  const frame = state.frame
  const pulse: Color = Math.floor(frame / 4) % 2 === 0 ? 'claude' : 'text'
  const spinner = SPINNER[frame % SPINNER.length] ?? '•'

  const columns = surface.columns > 0 ? surface.columns : PANE_COLUMNS
  // A card's border and padding take four cells.
  const inner = columns - 4
  // Too narrow for the full rail: icons only, then the current stage's name.
  const isCompact = railWidth(props.stages) > inner

  const running = props.workers.filter(w => w.phase === 'active')
  const finished = props.workers.filter(w => w.phase !== 'active')
  const failed = finished.filter(w => w.phase === 'failed').length

  const rail = (w: Card) => {
    const steps = [...props.stages, 'done']
    const parts = []
    for (let i = 0; i < steps.length; i++) {
      const label = isCompact ? '' : ` ${steps[i] ?? ''}`
      if (i > 0) {
        const link = i <= w.stage ? '━━━' : i === w.stage + 1 ? (FLOW[Math.floor(frame / 3) % FLOW.length] ?? '┄┄┄') : '┄┄┄'
        parts.push(
          <Text key={`l${i}`} color={i <= w.stage ? 'success' : i === w.stage + 1 ? 'claude' : 'inactive'}>
            {isCompact ? link.slice(0, 1) : link}
          </Text>,
        )
      }
      if (i < w.stage) {
        parts.push(
          <Text key={`s${i}`} color="success">
            ✔{label}
          </Text>,
        )
      } else if (i === w.stage) {
        parts.push(
          <Text key={`s${i}`} color={pulse} bold>
            {spinner}
            {label}
          </Text>,
        )
      } else {
        parts.push(
          <Text key={`s${i}`} color="inactive">
            ○{label}
          </Text>,
        )
      }
    }
    if (isCompact) {
      parts.push(
        <Text key="now" color={pulse} bold>
          {'  '}
          {steps[Math.min(w.stage, steps.length - 1)] ?? ''}
        </Text>,
      )
    }
    return parts
  }

  return (
    <Box flexDirection="column">
      <Box gap={2}>
        <Text color="claude" bold>
          {running.length > 0 ? spinner : '•'} {running.length} running
        </Text>
        <Text color="success">✔ {finished.length - failed} done</Text>
        <Text color={failed > 0 ? 'error' : 'inactive'}>✖ {failed} failed</Text>
      </Box>
      {props.workers.length === 0 && <Text color="inactive">No workers out.</Text>}
      {running.map(w => {
        const idle = w.lastAt > 0 ? now - w.lastAt : 0
        const flag = !w.isLive ? '✖ gone' : w.needsAction ? '⚠ needs you' : idle >= IDLE_MS ? `⏸ idle ${clock(idle)}` : ''
        const time = clock(now - w.since)
        const badge = ` ${w.role} `
        // Badge, a space, the key, a gap, the flag and its gap, the clock: the key takes what is left.
        const keyWidth = inner - badge.length - 2 - time.length - (flag === '' ? 0 : flag.length + 1)
        return (
          <Box key={w.id} flexDirection="column" borderStyle="round" borderColor={roleColor(w.role)} paddingX={1}>
            <Box justifyContent="space-between">
              <Box flexShrink={1}>
                <Text backgroundColor={roleColor(w.role)} color="inverseText" bold>
                  {badge}
                </Text>
                <Text bold wrap="truncate-end">
                  {' '}
                  {fit(w.key || '-', keyWidth)}
                </Text>
              </Box>
              <Box gap={1} flexShrink={0}>
                {flag !== '' && <Text color={w.isLive ? 'warning' : 'error'}>{flag}</Text>}
                <Text color="subtle">{time}</Text>
              </Box>
            </Box>
            <Box>{rail(w)}</Box>
          </Box>
        )
      })}
      {finished.map(w => {
        const tail = ` · ${w.phase} ${clock(now - w.since)} ago`
        return (
          <Box key={w.id}>
            <Text color={w.phase === 'done' ? 'success' : w.phase === 'failed' ? 'error' : 'inactive'}>
              {w.phase === 'done' ? '✔ ' : w.phase === 'failed' ? '✖ ' : '■ '}
            </Text>
            <Text color={roleColor(w.role)} bold>
              {w.role}
            </Text>
            <Text wrap="truncate-end">
              {' '}
              {fit(w.key, columns - w.role.length - tail.length - 3)}
            </Text>
            <Text color="subtle">{tail}</Text>
          </Box>
        )
      })}
    </Box>
  )
}

export default WorkerCards
