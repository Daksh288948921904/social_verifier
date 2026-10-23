import { useEffect, useState } from 'react'
import type { FootageClip, FootageMoment, FootageVideo } from '../../api/types'
import { Button } from '../ui/Button'
import { ClipButton } from './ClipButton'
import { MomentTimeline } from './MomentTimeline'
import { fmtTime, youtubeAt } from './format'

export interface PlayerTarget {
  video: FootageVideo
  moment: FootageMoment | null
  keywordText: string
  keywordColor: string
  segmentTitle: string
  segmentPosition: number
}

export function MomentPlayer({
  target,
  onClose,
  clipFor,
  onDownload,
}: {
  target: PlayerTarget
  onClose: () => void
  clipFor: (video: FootageVideo, moment: FootageMoment) => FootageClip | undefined
  onDownload: (video: FootageVideo, moment: FootageMoment) => void
}) {
  const { video, keywordText, keywordColor, segmentTitle } = target
  const [moment, setMoment] = useState<FootageMoment | null>(target.moment)
  const [copied, setCopied] = useState(false)

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  const start = Math.floor(moment?.start ?? 0)
  const params = new URLSearchParams({ start: String(start), autoplay: '1', rel: '0' })
  if (moment) params.set('end', String(Math.ceil(moment.end)))
  const embedSrc = `https://www.youtube-nocookie.com/embed/${video.video_id}?${params}`

  async function copyReference() {
    const range = moment ? ` (${fmtTime(moment.start)}–${fmtTime(moment.end)})` : ''
    const label = moment?.label ? ` — ${moment.label}` : ''
    await navigator.clipboard.writeText(`${video.title}${label}${range}\n${youtubeAt(video.video_id, start)}`)
    setCopied(true)
    setTimeout(() => setCopied(false), 1500)
  }

  return (
    <div
      className="fixed inset-0 z-50 flex animate-fade-in items-start justify-center overflow-y-auto bg-black/85 p-4 sm:items-center"
      onClick={onClose}
    >
      <div
        className="w-full max-w-4xl border-2 border-neutral-700 bg-neutral-950 shadow-[8px_8px_0_0_#000]"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-label={video.title}
      >
        <div className="flex items-center justify-between gap-3 border-b-2 border-neutral-800 px-4 py-2">
          <div className="min-w-0 font-mono text-[11px] uppercase tracking-widest text-neutral-500">
            <span className="text-neutral-300">{segmentTitle}</span>
            <span className="mx-2">/</span>
            <span style={{ color: keywordColor }}>“{keywordText}”</span>
          </div>
          <button
            onClick={onClose}
            className="font-mono text-xs uppercase tracking-widest text-neutral-500 hover:text-brand-400"
          >
            Close ✕
          </button>
        </div>

        {/* key forces a fresh iframe per moment so start/end actually apply */}
        <div className="aspect-video w-full bg-black">
          <iframe
            key={embedSrc}
            src={embedSrc}
            title={video.title}
            className="h-full w-full"
            allow="autoplay; encrypted-media; picture-in-picture; fullscreen"
            allowFullScreen
          />
        </div>

        <div className="space-y-4 p-4">
          <div>
            <h3 className="font-display text-2xl uppercase leading-tight text-neutral-50">{video.title}</h3>
            <p className="font-mono text-xs text-neutral-500">
              {video.channel || 'Unknown channel'} · {fmtTime(video.duration_seconds)} long
            </p>
          </div>

          <MomentTimeline
            video={video}
            active={moment}
            onSelect={setMoment}
            color={keywordColor}
            tall
          />

          {moment ? (
            <div className="border-l-4 bg-black/40 p-3" style={{ borderColor: keywordColor }}>
              <p className="font-mono text-xs font-bold" style={{ color: keywordColor }}>
                {fmtTime(moment.start)} – {fmtTime(moment.end)} · {Math.round(moment.end - moment.start)}s
                {moment.estimated && <span className="ml-2 text-orange-400">≈ estimated — no captions</span>}
              </p>
              <p className="mt-1 font-display text-xl uppercase text-neutral-100">{moment.label}</p>
              <p className="mt-1 text-sm text-neutral-300">{moment.description}</p>
              {moment.fit && (
                <p className="mt-2 text-sm text-neutral-400">
                  <span className="font-mono text-[11px] uppercase tracking-widest text-neutral-500">
                    Covers in your script →{' '}
                  </span>
                  {moment.fit}
                </p>
              )}
            </div>
          ) : (
            video.verdict && <p className="text-sm text-neutral-400">{video.verdict}</p>
          )}

          <div className="flex flex-wrap gap-2">
            <a href={youtubeAt(video.video_id, start)} target="_blank" rel="noreferrer">
              <Button size="sm" variant="primary">Open on YouTube at {fmtTime(start)}</Button>
            </a>
            <Button size="sm" onClick={copyReference}>{copied ? 'Copied ✓' : 'Copy reference'}</Button>
            {moment && <ClipButton clip={clipFor(video, moment)} onDownload={() => onDownload(video, moment)} />}
          </div>
        </div>
      </div>
    </div>
  )
}
