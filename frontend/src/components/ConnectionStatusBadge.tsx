import type { ConnectionStatus } from '../hooks/useSessionSocket'
import { Badge } from './ui/Badge'

const STYLES: Record<ConnectionStatus, { label: string; tone: 'warning' | 'success' | 'danger'; pulse?: boolean }> = {
  connecting: { label: 'Connecting…', tone: 'warning', pulse: true },
  open: { label: 'Live', tone: 'success', pulse: true },
  closed: { label: 'Disconnected', tone: 'danger' },
}

// The websocket can stay open after a session has stopped/errored (the
// backend doesn't close it), so "connected" alone would keep showing green
// "Live" forever. Once we know the session's own status, it wins over raw
// connectivity.
const SESSION_STYLES: Record<string, { label: string; tone: 'neutral' | 'danger' | 'warning' }> = {
  stopped: { label: 'Stopped', tone: 'neutral' },
  error: { label: 'Error', tone: 'danger' },
  starting: { label: 'Starting…', tone: 'warning' },
}

export function ConnectionStatusBadge({
  status,
  sessionStatus,
}: {
  status: ConnectionStatus
  sessionStatus?: string
}) {
  const s =
    sessionStatus && sessionStatus !== 'capturing'
      ? (SESSION_STYLES[sessionStatus] ?? { label: sessionStatus, tone: 'neutral' as const })
      : STYLES[status]
  return (
    <Badge tone={s.tone} dot pulse={'pulse' in s ? s.pulse : false} className="py-1.5 text-sm">
      {s.label}
    </Badge>
  )
}
