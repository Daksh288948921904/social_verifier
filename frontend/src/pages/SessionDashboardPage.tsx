import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useParams } from 'react-router-dom'
import { api } from '../api/client'
import { useSessionSocket } from '../hooks/useSessionSocket'
import { ConnectionStatusBadge } from '../components/ConnectionStatusBadge'
import { TranscriptTicker } from '../components/TranscriptTicker'
import { SegmentInProgressBanner } from '../components/SegmentInProgressBanner'
import { ClipsGallery } from '../components/ClipsGallery'
import { NewspaperPanel } from '../components/NewspaperPanel'
import { PageHeader } from '../components/ui/PageHeader'
import { Button } from '../components/ui/Button'

export function SessionDashboardPage() {
  const { sessionId } = useParams<{ sessionId: string }>()
  const queryClient = useQueryClient()
  if (!sessionId) return null

  const { data: session } = useQuery({
    queryKey: ['session', sessionId],
    queryFn: () => api.getSession(sessionId),
    refetchInterval: 5000,
  })

  const { connectionStatus, transcriptTicks, inProgress, errors } = useSessionSocket(sessionId)

  const stopSession = useMutation({
    mutationFn: () => api.stopSession(sessionId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['session', sessionId] }),
  })

  return (
    <div className="mx-auto max-w-5xl px-4 py-8">
      <PageHeader
        backTo="/"
        backLabel="All sessions"
        title={session?.url}
        subtitle={session?.source_type}
        actions={
          <div className="flex shrink-0 items-center gap-3">
            <ConnectionStatusBadge status={connectionStatus} sessionStatus={session?.status} />
            {session?.status === 'capturing' && (
              <Button variant="danger" size="sm" disabled={stopSession.isPending} onClick={() => stopSession.mutate()}>
                {stopSession.isPending ? 'Stopping…' : 'Stop'}
              </Button>
            )}
          </div>
        }
      />

      <div className="mb-4 space-y-3">
        <TranscriptTicker ticks={transcriptTicks} />
        <SegmentInProgressBanner segment={inProgress} />
        {errors.length > 0 && (
          <div className="animate-slide-up border-2 border-brand-600 bg-black p-3 font-mono text-xs text-brand-400 shadow-[4px_4px_0_0_#000]">
            {errors.map((e, i) => (
              <p key={i}>{e}</p>
            ))}
          </div>
        )}
      </div>

      <NewspaperPanel sessionId={sessionId} />

      <h2 className="mb-3 font-display text-lg uppercase tracking-widest text-neutral-500">Clips</h2>
      <ClipsGallery sessionId={sessionId} />
    </div>
  )
}
