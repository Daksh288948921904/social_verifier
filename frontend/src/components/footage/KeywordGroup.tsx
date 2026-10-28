import { useState } from 'react'
import type { FootageClip, FootageKeyword, FootageMoment, FootagePick, FootageVideo } from '../../api/types'
import { Button } from '../ui/Button'
import { VideoCard } from './VideoCard'
import { isRunning } from './format'

export function KeywordGroup({
  keyword,
  color,
  onPlay,
  onRerun,
  onFresh,
  clipFor,
  onDownload,
  pickFor,
  onPush,
  onUnpick,
}: {
  keyword: FootageKeyword
  color: string
  onPlay: (video: FootageVideo, moment: FootageMoment | null) => void
  onRerun: () => void
  onFresh: () => void
  clipFor: (video: FootageVideo, moment: FootageMoment) => FootageClip | undefined
  onDownload: (video: FootageVideo, moment: FootageMoment) => void
  pickFor: (video: FootageVideo, moment: FootageMoment) => FootagePick | undefined
  onPush: (video: FootageVideo, moment: FootageMoment) => void
  onUnpick: (pick: FootagePick) => void
}) {
  const [open, setOpen] = useState(true)
  const running = isRunning(keyword.status)
  // Best fits first; videos still being analysed go last.
  const videos = [...keyword.videos].sort((a, b) => (b.relevance ?? -1) - (a.relevance ?? -1))
  const analyzed = keyword.videos.filter((v) => v.analyzed)
  const strong = analyzed.filter((v) => (v.relevance ?? 0) >= 70).length
  const momentCount = analyzed.reduce((n, v) => n + v.moments.length, 0)

  return (
    <div className="border-l-4 bg-neutral-950/60" style={{ borderColor: color }}>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 px-3 py-2">
        <button
          onClick={() => setOpen((o) => !o)}
          className="flex min-w-0 items-center gap-2 text-left"
          aria-expanded={open}
        >
          <span className="font-mono text-xs text-neutral-500">{open ? '▾' : '▸'}</span>
          <span className="font-display text-xl uppercase leading-none" style={{ color }}>
            “{keyword.text}”
          </span>
        </button>
        <span className="font-mono text-[11px] text-neutral-500">
          {running ? (
            <span className="inline-flex items-center gap-1.5 text-neutral-300">
              <span
                className="h-2.5 w-2.5 animate-spin rounded-full border-2 border-t-transparent"
                style={{ borderColor: color, borderTopColor: 'transparent' }}
              />
              {keyword.progress || 'Working…'}
            </span>
          ) : keyword.status === 'error' ? (
            <span className="text-brand-400">Failed: {keyword.error_message}</span>
          ) : (
            `${keyword.videos.length} videos · ${strong} strong fits · ${momentCount} moments`
          )}
        </span>
        {!running && (
          <div className="ml-auto flex gap-2">
            <Button size="sm" onClick={onRerun} title="Run the same search again and re-analyse its videos">
              ↻ Same search
            </Button>
            <Button
              size="sm"
              variant="primary"
              onClick={onFresh}
              title={`Search YouTube for "${keyword.text}" again, skipping every video already found`}
            >
              ⟳ New videos
            </Button>
          </div>
        )}
      </div>
      {keyword.rationale && open && (
        <p className="px-3 pb-2 text-xs text-neutral-500">
          <span className="font-mono uppercase tracking-widest text-neutral-600">For: </span>
          {keyword.rationale}
        </p>
      )}
      {open && videos.length > 0 && (
        <div className="grid grid-cols-1 gap-3 px-3 pb-3 sm:grid-cols-2 xl:grid-cols-3">
          {videos.map((v) => (
            <VideoCard
              key={v.id}
              video={v}
              color={color}
              onPlay={onPlay}
              clipFor={clipFor}
              onDownload={onDownload}
              pickFor={pickFor}
              onPush={onPush}
              onUnpick={onUnpick}
            />
          ))}
        </div>
      )}
      {open && running && videos.length === 0 && (
        <div className="grid grid-cols-1 gap-3 px-3 pb-3 sm:grid-cols-2 xl:grid-cols-3">
          {[0, 1, 2].map((i) => (
            <div key={i} className="aspect-[4/3] animate-shimmer bg-[linear-gradient(90deg,#171717_25%,#262626_50%,#171717_75%)] bg-[length:200%_100%]" />
          ))}
        </div>
      )}
      {open && !running && keyword.status === 'done' && videos.length === 0 && (
        <p className="px-3 pb-3 font-mono text-xs text-neutral-600">YouTube returned no videos for this keyword.</p>
      )}
    </div>
  )
}
