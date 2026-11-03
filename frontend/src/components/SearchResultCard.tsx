import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../api/client'
import { apiUrl } from '../api/base'
import { Card } from './ui/Card'
import { Button } from './ui/Button'
import { fmtTime, parseTime, youtubeAt } from './footage/format'
import { searchResultKey } from './searchResultKey'
import type { SearchRangeClip, SearchResult } from '../api/types'

const MAX_RANGE_SECONDS = 600

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
      const busy = r && (r.status === 'fetching' || r.smart_status === 'analyzing' || r.ranges?.some((c) => c.status === 'cutting'))
      return busy ? 1500 : false
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

        <RangePanel result={current} onChange={save} />

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

const videoIdOf = (url: string) => url.match(/(?:v=|youtu\.be\/|shorts\/)([\w-]{11})/)?.[1] ?? null

// Your own timestamps: cut any part of the result, then download it with
// or without its sound.
function RangePanel({ result: r, onChange }: { result: SearchResult; onChange: (r: SearchResult) => void }) {
  const smart = r.smart_status === 'done' && r.smart_start != null && r.smart_end != null
  const [startText, setStartText] = useState(smart ? fmtTime(r.smart_start) : '0:00')
  const [endText, setEndText] = useState(smart ? fmtTime(r.smart_end) : '0:10')
  const cut = useMutation({
    mutationFn: ({ start, end }: { start: number; end: number }) => api.cutSearchRange(r.id, start, end),
    onSuccess: onChange,
  })
  const remove = useMutation({ mutationFn: (clipId: string) => api.deleteSearchRange(clipId), onSuccess: onChange })

  const start = parseTime(startText)
  const end = parseTime(endText)
  const error =
    start == null || end == null ? 'Enter times like 1:23 or 83'
    : end <= start ? 'End must be after start'
    : end - start > MAX_RANGE_SECONDS ? 'A clip can be at most 10 minutes'
    : null
  const videoId = r.source === 'youtube' ? videoIdOf(r.url) : null
  const field = 'w-16 border-2 border-neutral-700 bg-black px-2 py-1 font-mono text-xs text-neutral-100 outline-none focus:border-cyan-500'

  return (
    <div className="space-y-2 border-2 border-dashed border-neutral-800 p-2">
      <p className="font-mono text-[10px] uppercase tracking-widest text-neutral-400">✎ Your own timestamps</p>
      <div className="flex flex-wrap items-center gap-2">
        <label className="flex items-center gap-1 font-mono text-[10px] uppercase text-neutral-500">
          From <input className={field} value={startText} onChange={(e) => setStartText(e.target.value)} placeholder="m:ss" />
        </label>
        <label className="flex items-center gap-1 font-mono text-[10px] uppercase text-neutral-500">
          To <input className={field} value={endText} onChange={(e) => setEndText(e.target.value)} placeholder="m:ss" />
        </label>
        <span className="font-mono text-[10px] text-neutral-500">
          {error ? <span className="text-brand-400">{error}</span> : `${Math.round(end! - start!)}s`}
        </span>
        {videoId && start != null && (
          <a href={youtubeAt(videoId, Math.floor(start))} target="_blank" rel="noreferrer"
            className="font-mono text-[10px] text-neutral-500 hover:text-neutral-300">
            ▶ check on YouTube ↗
          </a>
        )}
      </div>
      <Button size="sm" className="w-full" disabled={!!error || cut.isPending}
        onClick={() => start != null && end != null && cut.mutate({ start, end })}>
        ✂ Cut {error ? 'clip' : `${fmtTime(start)}–${fmtTime(end)}`}
      </Button>
      {cut.isError && <p className="font-mono text-xs text-brand-400">{(cut.error as Error).message}</p>}
      {(r.ranges ?? []).length > 0 && (
        <ul className="space-y-1.5">
          {r.ranges!.map((c) => (
            <RangeRow key={c.id} clip={c} onRemove={() => remove.mutate(c.id)} removing={remove.isPending} />
          ))}
        </ul>
      )}
    </div>
  )
}

function RangeRow({ clip: c, onRemove, removing }: { clip: SearchRangeClip; onRemove: () => void; removing: boolean }) {
  const file = (audio: boolean) => apiUrl(`/api/search-results/ranges/${c.id}/file?audio=${audio}`)
  return (
    <li className="space-y-1 border border-neutral-800 bg-black/40 p-1.5">
      <div className="flex items-center gap-2 font-mono text-[11px]">
        <span className="font-bold text-neutral-200">{fmtTime(c.start)}–{fmtTime(c.end)}</span>
        <span className="text-neutral-500">{Math.round(c.end - c.start)}s</span>
        {c.status === 'cutting' && <span className="animate-pulse text-cyan-300">cutting…</span>}
        {c.status !== 'cutting' && (
          <button onClick={onRemove} disabled={removing} title="Remove this clip"
            className="ml-auto text-neutral-600 hover:text-brand-400">✕</button>
        )}
      </div>
      {c.status === 'done' && (
        <div className="flex gap-1.5">
          <a href={file(true)} className="flex-1"><Button size="sm" variant="primary" className="w-full">⬇ With audio</Button></a>
          <a href={file(false)} className="flex-1"><Button size="sm" className="w-full">⬇ No audio</Button></a>
        </div>
      )}
      {c.status === 'error' && <p className="text-[11px] text-brand-400">{c.error_message}</p>}
    </li>
  )
}
