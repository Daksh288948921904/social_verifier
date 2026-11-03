import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../api/client'
import { apiUrl } from '../api/base'
import { Card } from './ui/Card'
import { Button } from './ui/Button'
import { fmtTime, youtubeAt } from './footage/format'
import { searchResultKey } from './searchResultKey'
import type { SearchResult } from '../api/types'

const SOURCE_LABEL: Record<string, string> = {
  youtube: 'YouTube',
  web: 'Web',
  instagram: 'Instagram',
}

export function SearchResultCard({ result, seconds }: { result: SearchResult; seconds: number }) {
  const queryClient = useQueryClient()
  const save = (r: SearchResult) => queryClient.setQueryData(searchResultKey(r.id), r)
  const fetchClip = useMutation({ mutationFn: () => api.fetchSearchResult(result.id), onSuccess: save })
  const smartClip = useMutation({ mutationFn: () => api.smartSearchClip(result.id, seconds), onSuccess: save })

  // One query per card holds the latest row; the buttons here (and the
  // page's "Smart-pick all") write into it, and it polls while a fetch or
  // smart clip is running.
  const { data } = useQuery({
    queryKey: searchResultKey(result.id),
    queryFn: () => api.getSearchResult(result.id),
    initialData: result,
    staleTime: Infinity,
    refetchInterval: (query) => {
      const r = query.state.data
      return r && (r.status === 'fetching' || r.smart_status === 'analyzing') ? 1500 : false
    },
  })

  const current = data ?? result
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
      <div className="flex flex-1 flex-col gap-2 p-3">
        <span className="font-mono text-[11px] uppercase tracking-widest text-brand-500">
          {SOURCE_LABEL[result.source] ?? result.source}
        </span>
        <h3 className="font-display text-lg uppercase leading-tight text-neutral-100">{result.title}</h3>
        {result.description && (
          <p className="line-clamp-3 text-xs text-neutral-500">{result.description}</p>
        )}

        {result.source === 'youtube' && (
          <SmartClipPanel
            result={current}
            seconds={seconds}
            starting={smartClip.isPending}
            onRun={() => smartClip.mutate()}
          />
        )}

        <div className="mt-auto space-y-2 pt-1">
          {isDone ? (
            <video
              controls
              className="aspect-video w-full bg-black"
              src={apiUrl(`/api/search-results/${result.id}/video`)}
            />
          ) : (
            <Button
              size="sm"
              className="w-full"
              disabled={fetchClip.isPending || isFetching}
              onClick={() => fetchClip.mutate()}
            >
              {isFetching ? 'Fetching…' : 'Fetch whole video'}
            </Button>
          )}

          {(fetchClip.isError || current.status === 'error') && (
            <p className="font-mono text-xs text-brand-400">
              {current.error_message ?? (fetchClip.error as Error | undefined)?.message}
            </p>
          )}
        </div>
      </div>
    </Card>
  )
}

function SmartClipPanel({
  result: r,
  seconds,
  starting,
  onRun,
}: {
  result: SearchResult
  seconds: number
  starting: boolean
  onRun: () => void
}) {
  const running = starting || r.smart_status === 'analyzing'
  const range =
    r.smart_start != null && r.smart_end != null
      ? `${fmtTime(r.smart_start)}–${fmtTime(r.smart_end)} · ${Math.round(r.smart_end - r.smart_start)}s`
      : null

  return (
    <div className="space-y-2 border-2 border-dashed border-cyan-900 bg-cyan-950/10 p-2">
      <p className="font-mono text-[10px] uppercase tracking-widest text-cyan-400">
        ✦ Smart clip · clean, {seconds}s, no ticker / logo / text
      </p>

      {r.smart_status === 'done' && (
        <>
          <video
            controls
            className="aspect-video w-full bg-black"
            src={apiUrl(`/api/search-results/${r.id}/smart-video`)}
          />
          <p className="font-mono text-xs font-bold text-cyan-300">
            {range}
            {r.smart_start != null && (
              <a
                href={youtubeAt(r.url.split('v=')[1]?.slice(0, 11) ?? '', Math.floor(r.smart_start))}
                target="_blank"
                rel="noreferrer"
                className="ml-2 font-normal text-neutral-500 hover:text-neutral-300"
              >
                on YouTube ↗
              </a>
            )}
          </p>
          {r.smart_note && <p className="text-xs text-neutral-400">{r.smart_note}</p>}
          <div className="flex gap-2">
            <a href={apiUrl(`/api/search-results/${r.id}/smart-video?download=true`)} className="flex-1">
              <Button size="sm" variant="primary" className="w-full">⬇ Download clip</Button>
            </a>
            <a
              href={apiUrl(`/api/search-results/${r.id}/smart-video?download=true&audio=false`)}
              title="Same clip with the sound track removed"
            >
              <Button size="sm">⬇ No audio</Button>
            </a>
            <Button size="sm" variant="ghost" disabled={running} onClick={onRun} title="Look again">
              ↻
            </Button>
          </div>
        </>
      )}

      {running && (
        <p className="animate-pulse font-mono text-xs text-cyan-300">
          {r.smart_note || 'Starting…'}
          {range && <span className="text-neutral-500"> · {range}</span>}
        </p>
      )}

      {!running && (r.smart_status === 'none' || r.smart_status === 'error') && (
        <p className={`text-xs ${r.smart_status === 'none' ? 'text-orange-400' : 'text-brand-400'}`}>
          {r.smart_note}
        </p>
      )}

      {r.smart_status !== 'done' && (
        <Button size="sm" variant="primary" className="w-full" disabled={running} onClick={onRun}>
          {running ? 'Finding a clean clip…' : r.smart_status ? '↻ Try again' : `✦ Find a clean ${seconds}s clip`}
        </Button>
      )}
    </div>
  )
}
