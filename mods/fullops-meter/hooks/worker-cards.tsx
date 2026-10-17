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

  const running = props.workers.filter(w => w.phase === 'active')
  const finished = props.workers.filter(w => w.phase !== 'active')
  const failed = finished.filter(w => w.phase === 'failed').length

  const rail = (w: Card) => {
    const parts = []
    const steps = [...props.stages, 'done']
    for (let i = 0; i < steps.length; i++) {
      const label = steps[i] ?? ''
      if (i > 0) {
        const link = i <= w.stage ? '━━━' : i === w.stage + 1 ? FLOW[Math.floor(frame / 3) % FLOW.length] : '┄┄┄'
        parts.push(
          <Text key={`l${i}`} color={i <= w.stage ? 'success' : i === w.stage + 1 ? 'claude' : 'inactive'}>
            {link}
          </Text>,
        )
      }
      if (i < w.stage) {
        parts.push(<Text key={`s${i}`} color="success">✔ {label}</Text>)
      } else if (i === w.stage) {
        parts.push(
          <Text key={`s${i}`} color={pulse} bold>
            {SPINNER[frame % SPINNER.length]} {label}
          </Text>,
        )
      } else {
        parts.push(<Text key={`s${i}`} color="inactive">○ {label}</Text>)
      }
    }
    return parts
  }

  return (
    <Box flexDirection="column">
      <Box gap={2}>
        <Text color="claude" bold>
          {running.length > 0 ? SPINNER[frame % SPINNER.length] : '•'} {running.length} running
        </Text>
        <Text color="success">✔ {finished.length - failed} done</Text>
        <Text color={failed > 0 ? 'error' : 'inactive'}>✖ {failed} failed</Text>
      </Box>
      {props.workers.length === 0 && <Text color="inactive">No workers out.</Text>}
      {running.map(w => {
        const idle = w.lastAt > 0 ? now - w.lastAt : 0
        const flag = !w.isLive ? '✖ agent gone' : w.needsAction ? '⚠ needs you' : idle >= IDLE_MS ? `⏸ idle ${clock(idle)}` : ''
        return (
          <Box key={w.id} flexDirection="column" borderStyle="round" borderColor={roleColor(w.role)} paddingX={1}>
            <Box justifyContent="space-between">
              <Box>
                <Text backgroundColor={roleColor(w.role)} color="inverseText" bold>
                  {` ${w.role} `}
                </Text>
                <Text bold> {w.key || '-'}</Text>
              </Box>
              <Box gap={1}>
                {flag !== '' && <Text color={w.isLive ? 'warning' : 'error'}>{flag}</Text>}
                <Text color="subtle">{clock(now - w.since)}</Text>
              </Box>
            </Box>
            <Box flexWrap="wrap">{rail(w)}</Box>
          </Box>
        )
      })}
      {finished.map(w => (
        <Box key={w.id}>
          <Text color={w.phase === 'done' ? 'success' : w.phase === 'failed' ? 'error' : 'inactive'}>
            {w.phase === 'done' ? '✔' : w.phase === 'failed' ? '✖' : '■'}{' '}
          </Text>
          <Text color={roleColor(w.role)} bold>
            {w.role}
          </Text>
          <Text> {w.key}</Text>
          <Text color="subtle"> · {w.phase} {clock(now - w.since)} ago</Text>
        </Box>
      ))}
    </Box>
  )
}

export default WorkerCards
