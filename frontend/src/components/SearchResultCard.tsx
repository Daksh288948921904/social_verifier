import { useMutation, useQuery } from '@tanstack/react-query'
import { api } from '../api/client'
import { apiUrl } from '../api/base'
import { Card } from './ui/Card'
import { Button } from './ui/Button'
import type { SearchResult } from '../api/types'

const SOURCE_LABEL: Record<string, string> = {
  youtube: 'YouTube',
  web: 'Web',
  instagram: 'Instagram',
}

export function SearchResultCard({ result }: { result: SearchResult }) {
  const fetchClip = useMutation({ mutationFn: () => api.fetchSearchResult(result.id) })

  // Mirrors ClipCard's mutate-then-poll pattern: a mutation kicks off the
  // background job, then a polling query tracks it until it leaves
  // 'fetching'.
  const { data: polled } = useQuery({
    queryKey: ['search-result', result.id],
    queryFn: () => api.getSearchResult(result.id),
    enabled: !!fetchClip.data,
    refetchInterval: (query) => (query.state.data?.status === 'fetching' ? 1500 : false),
  })

  const current = polled ?? fetchClip.data ?? result
  const isFetching = current.status === 'fetching'
  const isDone = current.status === 'done'

  return (
    <Card hover className="flex animate-slide-up flex-col overflow-hidden">
      <a href={result.url} target="_blank" rel="noreferrer" className="block">
        {result.thumbnail_url ? (
          <img
            src={result.thumbnail_url}
            alt={result.title}
            className="aspect-video w-full object-cover"
          />
        ) : (
          <div className="flex aspect-video w-full items-center justify-center bg-neutral-900 font-mono text-xs text-neutral-600">
            no preview
          </div>
        )}
      </a>
      <div className="space-y-2 p-3">
        <span className="font-mono text-[11px] uppercase tracking-widest text-brand-500">
          {SOURCE_LABEL[result.source] ?? result.source}
        </span>
        <h3 className="font-display text-lg uppercase leading-tight text-neutral-100">{result.title}</h3>
        {result.description && (
          <p className="line-clamp-3 text-xs text-neutral-500">{result.description}</p>
        )}

        {isDone ? (
          <video
            controls
            className="aspect-video w-full bg-black"
            src={apiUrl(`/api/search-results/${result.id}/video`)}
          />
        ) : (
          <Button
            variant="primary"
            size="sm"
            className="w-full"
            disabled={fetchClip.isPending || isFetching}
            onClick={() => fetchClip.mutate()}
          >
            {isFetching ? 'Fetching…' : 'Fetch Clip'}
          </Button>
        )}

        {(fetchClip.isError || current.status === 'error') && (
          <p className="font-mono text-xs text-brand-400">
            {current.error_message ?? (fetchClip.error as Error | undefined)?.message}
          </p>
        )}
      </div>
    </Card>
  )
}
