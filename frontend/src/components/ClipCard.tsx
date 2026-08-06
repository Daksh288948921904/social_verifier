import { memo, useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { api } from '../api/client'
import { apiUrl } from '../api/base'
import type { Clip } from '../api/types'
import { useClipMutations } from '../hooks/useClips'

function formatDuration(seconds: number): string {
  const m = Math.floor(seconds / 60)
  const s = Math.round(seconds % 60)
  return `${m}:${String(s).padStart(2, '0')}`
}

export const ClipCard = memo(function ClipCard({ clip }: { clip: Clip }) {
  const { rename, retrim, remove } = useClipMutations(clip.session_id)
  const [expanded, setExpanded] = useState(false)
  const [title, setTitle] = useState(clip.title)
  const [start, setStart] = useState(clip.start_seconds.toFixed(1))
  const [end, setEnd] = useState(clip.end_seconds.toFixed(1))

  const duration = clip.end_seconds - clip.start_seconds

  const createReel = useMutation({
    mutationFn: () => api.createClipReel(clip.id),
  })
  const { data: reel } = useQuery({
    queryKey: ['clip-reel', clip.id, createReel.data?.id],
    queryFn: () => api.getClipReel(clip.id, createReel.data!.id),
    enabled: !!createReel.data,
    refetchInterval: (query) => (query.state.data?.status === 'generating' ? 1500 : false),
  })

  return (
    <div className="group animate-slide-up overflow-hidden border-2 border-neutral-800 bg-neutral-950/90 shadow-[4px_4px_0_0_#000] transition-all duration-150 hover:-translate-x-[2px] hover:-translate-y-[2px] hover:border-brand-600 hover:shadow-[6px_6px_0_0_#000]">
      <button className="relative block w-full" onClick={() => setExpanded((v) => !v)}>
        {expanded ? (
          <video controls autoPlay className="aspect-video w-full bg-black" src={apiUrl(`/api/clips/${clip.id}/video`)} />
        ) : (
          <>
            <img
              src={apiUrl(`/api/clips/${clip.id}/thumbnail`)}
              alt={clip.title}
              className="aspect-video w-full object-cover grayscale transition-all duration-300 group-hover:grayscale-0"
            />
            <span className="absolute inset-0 flex items-center justify-center bg-black/0 transition group-hover:bg-black/40">
              <span className="flex h-11 w-11 items-center justify-center border-2 border-black bg-brand-500 text-lg text-black opacity-0 shadow-[3px_3px_0_0_#000] transition group-hover:opacity-100">
                ▶
              </span>
            </span>
          </>
        )}
      </button>

      <div className="space-y-2 p-3">
        <input
          className="w-full border-2 border-transparent bg-black px-2 py-1 font-mono text-sm font-medium text-neutral-100 outline-none transition focus:border-brand-600"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          onBlur={() => title !== clip.title && rename.mutate({ id: clip.id, title })}
        />
        {clip.summary && <p className="text-xs text-neutral-500">{clip.summary}</p>}
        <p className="font-mono text-xs text-brand-500">{formatDuration(duration)}</p>

        <div className="flex items-center gap-2 pt-1">
          <input
            className="w-16 border-2 border-neutral-800 bg-black px-1.5 py-0.5 font-mono text-xs outline-none focus:border-brand-600"
            value={start}
            onChange={(e) => setStart(e.target.value)}
          />
          <span className="text-neutral-600">–</span>
          <input
            className="w-16 border-2 border-neutral-800 bg-black px-1.5 py-0.5 font-mono text-xs outline-none focus:border-brand-600"
            value={end}
            onChange={(e) => setEnd(e.target.value)}
          />
          <button
            className="border-2 border-neutral-700 bg-neutral-900 px-2 py-0.5 font-mono text-xs uppercase text-neutral-200 transition hover:border-brand-500 disabled:opacity-50"
            disabled={retrim.isPending}
            onClick={() => retrim.mutate({ id: clip.id, start: Number(start), end: Number(end) })}
          >
            {retrim.isPending ? 'Trimming…' : 'Re-trim'}
          </button>
          <button
            className="ml-auto border-2 border-transparent px-2 py-0.5 font-mono text-xs uppercase text-brand-400 transition hover:border-brand-600"
            onClick={() => confirm(`Discard "${clip.title}"?`) && remove.mutate(clip.id)}
          >
            Discard
          </button>
        </div>

        <div className="border-t-2 border-neutral-800 pt-2">
          <button
            className="w-full border-2 border-neutral-700 bg-neutral-900 px-2 py-1 font-mono text-xs uppercase text-neutral-200 transition hover:border-brand-500 disabled:opacity-50"
            disabled={createReel.isPending || reel?.status === 'generating'}
            onClick={() => createReel.mutate()}
          >
            {reel?.status === 'generating'
              ? '🎬 Making reel…'
              : reel?.status === 'done'
                ? '🎬 Regenerate reel'
                : '🎬 Make reel'}
          </button>

          {createReel.isError && (
            <p className="mt-1.5 font-mono text-xs text-brand-400">
              {(createReel.error as Error).message}
            </p>
          )}
          {reel?.status === 'error' && (
            <p className="mt-1.5 font-mono text-xs text-brand-400">{reel.error_message}</p>
          )}
          {reel?.status === 'done' && (
            <div className="mt-2 animate-slide-up space-y-1.5 border-2 border-neutral-800 bg-black p-2">
              {reel.hook_text && (
                <p className="font-mono text-xs italic text-neutral-300">"{reel.hook_text}"</p>
              )}
              {reel.audio_style && (
                <p className="font-mono text-[11px] text-neutral-500">{reel.audio_style}</p>
              )}
              <a
                href={apiUrl(`/api/clips/${clip.id}/reel/${reel.id}/video`)}
                download="reel.mp4"
                className="inline-block w-full border-2 border-emerald-600 bg-black py-1 text-center font-mono text-xs uppercase text-emerald-400 transition hover:bg-emerald-950"
              >
                ⬇ Download reel
              </a>
            </div>
          )}
        </div>
      </div>
    </div>
  )
})
