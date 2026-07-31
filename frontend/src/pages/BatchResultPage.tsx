import { useQuery } from '@tanstack/react-query'
import { useNavigate, useParams } from 'react-router-dom'
import { api } from '../api/client'
import { PageHeader } from '../components/ui/PageHeader'
import { Badge } from '../components/ui/Badge'
import { Card } from '../components/ui/Card'
import { Skeleton } from '../components/ui/Skeleton'

const STATUS_LABEL: Record<string, string> = {
  queued: 'Queued…',
  downloading: 'Downloading…',
  transcribing: 'Transcribing…',
  extracting_claims: 'Extracting claims…',
  verifying_claims: 'Verifying claims…',
  concluding: 'Concluding…',
  done: 'Done',
  error: 'Failed',
}

export function BatchResultPage() {
  const { batchId } = useParams<{ batchId: string }>()
  const navigate = useNavigate()
  if (!batchId) return null

  const { data: batch } = useQuery({
    queryKey: ['batch', batchId],
    queryFn: () => api.getBatch(batchId),
    refetchInterval: (query) => (query.state.data?.status === 'done' ? false : 1500),
  })

  const finished = batch?.checks.filter((c) => c.status === 'done' || c.status === 'error').length ?? 0

  return (
    <div className="mx-auto max-w-2xl px-4 py-8">
      <PageHeader
        backTo="/verify/batch"
        backLabel="All batches"
        title={batch ? `${batch.checks.length}-link batch` : <Skeleton className="h-6 w-48" />}
        subtitle={batch && `Started ${batch.created_at}`}
        actions={
          batch && (
            <Badge tone={batch.status === 'done' ? 'success' : 'neutral'} dot pulse={batch.status !== 'done'}>
              {batch.status === 'done' ? 'Done' : `${finished}/${batch.checks.length} done`}
            </Badge>
          )
        }
      />

      {!batch && (
        <div className="space-y-2">
          <Skeleton className="h-16 w-full" />
          <Skeleton className="h-16 w-full" />
        </div>
      )}

      <div className="space-y-2">
        {batch?.checks.map((c, i) => {
          const isTerminal = c.status === 'done' || c.status === 'error'
          return (
            <button
              key={c.id}
              onClick={() => navigate(`/verify/${c.id}`)}
              style={{ animationDelay: `${i * 40}ms` }}
              className="group flex w-full animate-slide-up items-center justify-between gap-3 border-2 border-neutral-800 bg-neutral-950/90 px-4 py-3.5 text-left shadow-[4px_4px_0_0_#000] transition-all duration-150 hover:-translate-x-[2px] hover:-translate-y-[2px] hover:border-brand-600 hover:shadow-[6px_6px_0_0_#000]"
            >
              <div className="min-w-0 flex-1">
                <span className="block truncate font-mono text-sm text-neutral-300 transition group-hover:text-neutral-100">
                  {c.url}
                </span>
                {c.status === 'done' && (
                  <span className="mt-0.5 block font-mono text-xs text-neutral-600">
                    {c.claims.length} claim{c.claims.length === 1 ? '' : 's'} checked
                  </span>
                )}
                {c.status === 'error' && c.error_message && (
                  <span className="mt-0.5 block truncate font-mono text-xs text-brand-400">
                    {c.error_message}
                  </span>
                )}
              </div>
              <Badge
                className="shrink-0"
                tone={c.status === 'done' ? 'success' : c.status === 'error' ? 'danger' : 'neutral'}
                dot
                pulse={!isTerminal}
              >
                {STATUS_LABEL[c.status] ?? c.status}
                {c.status === 'verifying_claims' && c.progress ? ` ${c.progress}` : ''}
              </Badge>
            </button>
          )
        })}
      </div>

      {batch?.checks.length === 0 && (
        <Card className="p-6 text-center font-mono text-sm text-neutral-600">
          This batch has no links.
        </Card>
      )}
    </div>
  )
}
