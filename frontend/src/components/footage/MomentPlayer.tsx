import { useEffect, useState } from 'react'
import type { FootageClip, FootageMoment, FootagePick, FootageVideo } from '../../api/types'
import { Button } from '../ui/Button'
import { ClipButton } from './ClipButton'
import { MomentTimeline } from './MomentTimeline'
import { PickButton } from './PickButton'
import { fmtTime, parseTime, youtubeAt } from './format'
import { useYouTubePlayer } from './useYouTubePlayer'

const MAX_CLIP_SECONDS = 600

export interface PlayerTarget {
  video: FootageVideo
  moment: FootageMoment | null
  keywordId: string
  keywordText: string
  keywordColor: string
  segmentId: string
  segmentTitle: string
  segmentPosition: number
}

export interface RangeActions {
  clipFor: (start: number, end: number) => FootageClip | undefined
  onDownload: (start: number, end: number, label: string) => void
  pickFor: (start: number, end: number) => FootagePick | undefined
  onPush: (
    start: number, end: number, label: string, description: string,
    source: 'suggested' | 'custom', clipAudio: boolean,
  ) => void
  onUnpick: (pick: FootagePick) => void
}

function TimeField({
  label,
  value,
  onChange,
  onNow,
  nowDisabled,
}: {
  label: string
  value: string
  onChange: (v: string) => void
  onNow: () => void
  nowDisabled: boolean
}) {
  return (
    <label className="flex items-center gap-1.5">
      <span className="w-10 font-mono text-[11px] uppercase tracking-widest text-neutral-500">{label}</span>
      <input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder="m:ss"
        inputMode="decimal"
        className="w-20 border-2 border-neutral-700 bg-black px-2 py-1 font-mono text-sm text-neutral-100 outline-none focus:border-cyan-500"
      />
      <button
        type="button"
        onClick={onNow}
        disabled={nowDisabled}
        title="Use the player's current position"
        className="border-2 border-neutral-700 px-2 py-1 font-mono text-[11px] uppercase text-neutral-300 transition hover:border-cyan-500 hover:text-cyan-300 disabled:opacity-40"
      >
        ⏱ Now
      </button>
    </label>
  )
}

export function MomentPlayer({
  target,
  onClose,
  actions,
}: {
  target: PlayerTarget
  onClose: () => void
  actions: RangeActions
}) {
  const { video, keywordText, keywordColor, segmentTitle } = target
  const [moment, setMoment] = useState<FootageMoment | null>(target.moment)
  const [copied, setCopied] = useState(false)
  const player = useYouTubePlayer(video.video_id, target.moment?.start ?? 0, target.moment?.end ?? null)

  // The custom range starts as a copy of whichever moment is selected, so
  // nudging an AI suggestion by a few seconds is just an edit of these boxes.
  const [startText, setStartText] = useState(moment ? fmtTime(moment.start) : '0:00')
  const [endText, setEndText] = useState(moment ? fmtTime(moment.end) : '0:30')
  const [label, setLabel] = useState(moment?.label ?? '')

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  function selectMoment(m: FootageMoment) {
    setMoment(m)
    setStartText(fmtTime(m.start))
    setEndText(fmtTime(m.end))
    setLabel(m.label)
    player.playRange(m.start, m.end)
  }

  const start = parseTime(startText)
  const end = parseTime(endText)
  const duration = video.duration_seconds
  const rangeError =
    start == null || end == null ? 'Enter times like 1:23 or 83'
    : end <= start ? 'End must be after start'
    : duration != null && end > duration + 1 ? `Video is only ${fmtTime(duration)} long`
    : end - start > MAX_CLIP_SECONDS ? 'A clip can be at most 10 minutes'
    : null
  // The boxes show whole seconds, so an untouched AI moment (whose times can
  // have decimals) is matched by its displayed values and kept exact.
  const isSuggested =
    !!moment && startText === fmtTime(moment.start) && endText === fmtTime(moment.end)
  const rangeStart = isSuggested ? moment!.start : start ?? 0
  const rangeEnd = isSuggested ? moment!.end : end ?? 0
  const rangePick = !rangeError ? actions.pickFor(rangeStart, rangeEnd) : undefined

  function setFromPlayer(set: (v: string) => void) {
    const t = player.currentTime()
    if (t != null) set(fmtTime(t))
  }

  async function copyReference() {
    const at = Math.floor(moment?.start ?? 0)
    const range = moment ? ` (${fmtTime(moment.start)}–${fmtTime(moment.end)})` : ''
    const name = moment?.label ? ` — ${moment.label}` : ''
    await navigator.clipboard.writeText(`${video.title}${name}${range}\n${youtubeAt(video.video_id, at)}`)
    setCopied(true)
    setTimeout(() => setCopied(false), 1500)
  }

  return (
    <div
      className="fixed inset-0 z-50 flex animate-fade-in items-start justify-center overflow-y-auto bg-black/85 p-4"
      onClick={onClose}
    >
      <div
        className="my-auto w-full max-w-4xl border-2 border-neutral-700 bg-neutral-950 shadow-[8px_8px_0_0_#000]"
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

        <div ref={player.hostRef} className="aspect-video w-full bg-black" />

        <div className="space-y-4 p-4">
          <div>
            <h3 className="font-display text-2xl uppercase leading-tight text-neutral-50">{video.title}</h3>
            <p className="font-mono text-xs text-neutral-500">
              {video.channel || 'Unknown channel'} · {fmtTime(video.duration_seconds)} long
            </p>
          </div>

          <MomentTimeline video={video} active={moment} onSelect={selectMoment} color={keywordColor} tall />

          {video.moments.length > 0 && (
            <div>
              <p className="mb-1.5 font-mono text-[11px] uppercase tracking-widest text-neutral-500">
                {video.moments.length} moment{video.moments.length === 1 ? '' : 's'} found in this video — click to watch
              </p>
              <div className="flex flex-wrap gap-2">
                {[...video.moments]
                  .sort((a, b) => a.start - b.start)
                  .map((m) => {
                    const active = moment?.start === m.start && moment?.end === m.end
                    const picked = !!actions.pickFor(m.start, m.end)
                    return (
                      <button
                        key={`${m.start}-${m.end}`}
                        onClick={() => selectMoment(m)}
                        aria-pressed={active}
                        className={`flex max-w-full items-center gap-2 border-2 px-2 py-1 text-left transition ${
                          active ? 'bg-black' : 'border-neutral-800 hover:border-neutral-500'
                        }`}
                        style={active ? { borderColor: keywordColor } : undefined}
                      >
                        <span
                          className="shrink-0 px-1 font-mono text-[11px] font-bold text-black"
                          style={{ backgroundColor: keywordColor, opacity: active ? 1 : 0.7 }}
                        >
                          {fmtTime(m.start)}–{fmtTime(m.end)}
                        </span>
                        <span className={`truncate text-xs font-bold uppercase ${active ? 'text-white' : 'text-neutral-300'}`}>
                          {m.label}
                        </span>
                        {picked && <span className="shrink-0 font-mono text-[10px] text-brand-400">📌</span>}
                      </button>
                    )
                  })}
              </div>
            </div>
          )}

          {moment ? (
            <div className="border-l-4 bg-black/40 p-3" style={{ borderColor: keywordColor }}>
              <p className="font-mono text-xs font-bold" style={{ color: keywordColor }}>
                ✦ AI moment · {fmtTime(moment.start)} – {fmtTime(moment.end)} · {Math.round(moment.end - moment.start)}s
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
              <div className="mt-3 flex flex-wrap gap-2">
                <PickButton
                  pick={actions.pickFor(moment.start, moment.end)}
                  onPush={(clipAudio) => actions.onPush(moment.start, moment.end, moment.label, moment.description, 'suggested', clipAudio)}
                  onRemove={actions.onUnpick}
                  audioChoice
                />
                <ClipButton
                  clip={actions.clipFor(moment.start, moment.end)}
                  onDownload={() => actions.onDownload(moment.start, moment.end, moment.label)}
                />
              </div>
            </div>
          ) : (
            video.verdict && <p className="text-sm text-neutral-400">{video.verdict}</p>
          )}

          <div className="space-y-3 border-2 border-dashed border-cyan-900 bg-cyan-950/10 p-3">
            <div>
              <p className="font-mono text-[11px] uppercase tracking-widest text-cyan-400">✎ Your own timestamps</p>
              <p className="text-xs text-neutral-500">
                Pick any part of this video yourself — type the times, or play the video and press ⏱ Now at the
                start and at the end. Then push it to the plan or download it.
              </p>
            </div>
            <div className="flex flex-wrap items-center gap-x-5 gap-y-2">
              <TimeField
                label="Start"
                value={startText}
                onChange={setStartText}
                onNow={() => setFromPlayer(setStartText)}
                nowDisabled={!player.ready}
              />
              <TimeField
                label="End"
                value={endText}
                onChange={setEndText}
                onNow={() => setFromPlayer(setEndText)}
                nowDisabled={!player.ready}
              />
              <span className="font-mono text-xs text-neutral-400">
                {rangeError ? <span className="text-brand-400">{rangeError}</span> : `${Math.round(rangeEnd - rangeStart)}s clip`}
              </span>
            </div>
            <input
              value={label}
              onChange={(e) => setLabel(e.target.value)}
              placeholder="What's in this clip? e.g. Göring testifying (helps the plan place it)"
              className="w-full border-2 border-neutral-700 bg-black px-3 py-1.5 text-sm text-neutral-100 placeholder-neutral-600 outline-none focus:border-cyan-500"
            />
            <div className="flex flex-wrap gap-2">
              <Button
                size="sm"
                disabled={!!rangeError || !player.ready}
                onClick={() => player.playRange(rangeStart, rangeEnd)}
              >
                ▶ Preview range
              </Button>
              {!rangeError && (
                <>
                  <PickButton
                    pick={rangePick}
                    audioChoice
                    onPush={(clipAudio) =>
                      actions.onPush(
                        rangeStart,
                        rangeEnd,
                        label.trim(),
                        isSuggested ? moment!.description : '',
                        isSuggested ? 'suggested' : 'custom',
                        clipAudio,
                      )
                    }
                    onRemove={actions.onUnpick}
                  />
                  <ClipButton
                    clip={actions.clipFor(rangeStart, rangeEnd)}
                    onDownload={() => actions.onDownload(rangeStart, rangeEnd, label.trim() || 'Custom clip')}
                  />
                </>
              )}
            </div>
          </div>

          <div className="flex flex-wrap gap-2 border-t border-neutral-800 pt-3">
            <a href={youtubeAt(video.video_id, Math.floor(moment?.start ?? 0))} target="_blank" rel="noreferrer">
              <Button size="sm" variant="ghost">Open on YouTube ↗</Button>
            </a>
            <Button size="sm" variant="ghost" onClick={copyReference}>{copied ? 'Copied ✓' : 'Copy reference'}</Button>
          </div>
        </div>
      </div>
    </div>
  )
}
