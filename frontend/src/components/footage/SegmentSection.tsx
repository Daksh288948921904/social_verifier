import { useState } from 'react'
import type { FormEvent } from 'react'
import type { FootageClip, FootageKeyword, FootageMoment, FootagePick, FootageSegment, FootageVideo } from '../../api/types'
import { Card } from '../ui/Card'
import { ClipButton } from './ClipButton'
import { KeywordChip } from './KeywordChip'
import { KeywordGroup } from './KeywordGroup'
import { PickButton } from './PickButton'
import { fmtTime, isRunning } from './format'

const BEST_PICKS = 3

export interface SegmentHandlers {
  colorOf: (keywordId: string) => string
  isSelected: (keywordId: string) => boolean
  toggle: (keywordId: string) => void
  selectMany: (keywordIds: string[]) => void
  play: (segment: FootageSegment, keyword: FootageKeyword, video: FootageVideo, moment: FootageMoment | null) => void
  addKeyword: (segmentId: string, text: string) => void
  deleteKeyword: (keywordId: string) => void
  rerun: (keywordId: string) => void
  fresh: (keywordId: string) => void
  clipFor: (video: FootageVideo, moment: FootageMoment) => FootageClip | undefined
  download: (segment: FootageSegment, items: { video: FootageVideo; moment: FootageMoment }[]) => void
  picksOf: (segmentId: string) => FootagePick[]
  pickFor: (segmentId: string, videoId: string, start: number, end: number) => FootagePick | undefined
  push: (segment: FootageSegment, keyword: FootageKeyword, video: FootageVideo, moment: FootageMoment) => void
  unpick: (pick: FootagePick) => void
  playPick: (segment: FootageSegment, pick: FootagePick) => void
}

function PushedToPlan({ segment, h }: { segment: FootageSegment; h: SegmentHandlers }) {
  const picks = h.picksOf(segment.id)
  return (
    <div className="border-2 border-dashed border-brand-900 bg-brand-950/20 p-3">
      <p className="mb-2 font-mono text-[11px] uppercase tracking-widest text-brand-400">
        📌 Pushed to plan · {picks.length} clip{picks.length === 1 ? '' : 's'}
      </p>
      {picks.length === 0 ? (
        <p className="text-xs text-neutral-500">
          Nothing yet. The edit plan only uses clips you choose — press <b>📌 Push to plan</b> on any moment below,
          or open a video and set your own timestamps.
        </p>
      ) : (
        <ul className="flex flex-wrap gap-2">
          {picks.map((p) => (
            <li key={p.id} className="flex w-64 items-stretch border border-neutral-800 bg-black/60">
              <button onClick={() => h.playPick(segment, p)} className="relative w-24 shrink-0" title="Play this clip">
                <img
                  src={p.thumbnail_url ?? `https://i.ytimg.com/vi/${p.video_id}/mqdefault.jpg`}
                  alt=""
                  className="h-full w-full object-cover"
                />
                <span className="absolute bottom-0 left-0 bg-black/85 px-1 font-mono text-[10px] text-neutral-100">
                  ▶ {fmtTime(p.start)}–{fmtTime(p.end)}
                </span>
              </button>
              <div className="min-w-0 flex-1 p-1.5">
                <p className="truncate text-[11px] font-bold uppercase text-neutral-100" title={p.label}>
                  {p.label || 'Untitled clip'}
                </p>
                <p className="truncate font-mono text-[10px] text-neutral-500" title={p.video_title}>{p.video_title}</p>
                <div className="mt-1 flex items-center justify-between">
                  <span className={`font-mono text-[9px] uppercase tracking-wider ${p.source === 'custom' ? 'text-cyan-400' : 'text-neutral-500'}`}>
                    {p.source === 'custom' ? '✎ Your timestamps' : '✦ AI moment'}
                  </span>
                  <button
                    onClick={() => h.unpick(p)}
                    aria-label={`Remove ${p.label || 'clip'} from the plan`}
                    className="font-mono text-[11px] text-neutral-500 hover:text-brand-400"
                  >
                    ✕
                  </button>
                </div>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

function BestPicks({ segment, h }: { segment: FootageSegment; h: SegmentHandlers }) {
  // The strongest moments across every keyword in this segment -- the
  // shortlist an editor would actually cut from. One per video, so a single
  // great source doesn't crowd out the alternatives.
  const seen = new Set<string>()
  const picks = segment.keywords
    .flatMap((k) => k.videos.flatMap((v) => v.moments.map((m) => ({ k, v, m }))))
    .sort((a, b) => b.m.score - a.m.score)
    .filter(({ v }) => !seen.has(v.video_id) && !!seen.add(v.video_id))
    .slice(0, BEST_PICKS)
  if (picks.length === 0) return null
  const notDownloaded = picks.filter(({ v, m }) => {
    const clip = h.clipFor(v, m)
    return !clip || clip.status === 'error'
  })

  return (
    <div>
      <div className="mb-2 flex flex-wrap items-center gap-x-3 gap-y-1">
        <p className="font-mono text-[11px] uppercase tracking-widest text-neutral-500">
          ★ Best footage for this segment
        </p>
        {notDownloaded.length > 0 && (
          <button
            onClick={() => h.download(segment, notDownloaded.map(({ v, m }) => ({ video: v, moment: m })))}
            className="font-mono text-[11px] uppercase tracking-widest text-brand-400 hover:text-brand-300"
          >
            ⬇ Download {notDownloaded.length === picks.length ? 'all' : `the other ${notDownloaded.length}`} best pick
            {notDownloaded.length === 1 ? '' : 's'}
          </button>
        )}
      </div>
      <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
        {picks.map(({ k, v, m }, i) => {
          const color = h.colorOf(k.id)
          return (
            <div
              key={`${v.id}-${m.start}`}
              className="flex flex-col border-2 border-neutral-800 bg-black/50 transition hover:-translate-y-0.5 hover:border-neutral-500"
            >
              <button onClick={() => h.play(segment, k, v, m)} className="group flex flex-1 flex-col text-left">
                <div className="relative">
                  <img
                    src={v.thumbnail_url ?? `https://i.ytimg.com/vi/${v.video_id}/mqdefault.jpg`}
                    alt=""
                    loading="lazy"
                    className="aspect-video w-full object-cover"
                  />
                  <span className="absolute left-0 top-0 bg-brand-500 px-2 font-display text-lg text-black">
                    #{i + 1}
                  </span>
                  <span
                    className="absolute bottom-1.5 left-1.5 px-1.5 font-mono text-xs font-bold text-black"
                    style={{ backgroundColor: color }}
                  >
                    ▶ {fmtTime(m.start)}–{fmtTime(m.end)}
                  </span>
                </div>
                <div className="space-y-1 p-2.5">
                  <p className="font-display text-lg uppercase leading-tight text-neutral-100">{m.label}</p>
                  <p className="text-xs text-neutral-400">{m.description}</p>
                  {m.fit && <p className="text-[11px] italic text-neutral-500">↳ {m.fit}</p>}
                  <p className="pt-1 font-mono text-[10px] text-neutral-600">
                    from <span className="text-neutral-400">{v.title}</span> · via{' '}
                    <span style={{ color }}>“{k.text}”</span>
                  </p>
                </div>
              </button>
              <div className="flex flex-wrap gap-2 px-2.5 pb-2.5">
                <PickButton
                  pick={h.pickFor(segment.id, v.video_id, m.start, m.end)}
                  onPush={() => h.push(segment, k, v, m)}
                  onRemove={h.unpick}
                />
                <ClipButton clip={h.clipFor(v, m)} onDownload={() => h.download(segment, [{ video: v, moment: m }])} />
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

export function SegmentSection({
  segment,
  index,
  showHeader,
  h,
}: {
  segment: FootageSegment
  index: number
  showHeader: boolean
  h: SegmentHandlers
}) {
  const [showScript, setShowScript] = useState(false)
  const [newKeyword, setNewKeyword] = useState('')

  const selectable = segment.keywords.filter((k) => !isRunning(k.status))
  const notYetRun = selectable.filter((k) => k.status === 'idle' || k.status === 'error')
  const withResults = segment.keywords.filter((k) => k.status !== 'idle')

  function submitKeyword(e: FormEvent) {
    e.preventDefault()
    if (!newKeyword.trim()) return
    h.addKeyword(segment.id, newKeyword.trim())
    setNewKeyword('')
  }

  return (
    <Card id={`segment-${segment.id}`} className="scroll-mt-24 space-y-5 p-4 sm:p-5">
      {showHeader && (
        <div>
          <p className="font-mono text-[11px] uppercase tracking-widest text-brand-500">
            Segment {String(index + 1).padStart(2, '0')}
          </p>
          <h2 className="font-display text-3xl uppercase leading-none tracking-wide text-neutral-50">
            {segment.title}
          </h2>
          {segment.summary && <p className="mt-2 text-sm text-neutral-300">{segment.summary}</p>}
          {segment.visual_needs && (
            <p className="mt-2 text-sm text-neutral-400">
              <span className="font-mono text-[11px] uppercase tracking-widest text-neutral-500">
                🎬 Footage wanted:{' '}
              </span>
              {segment.visual_needs}
            </p>
          )}
          {segment.script_excerpt && (
            <div className="mt-2">
              <button
                onClick={() => setShowScript((s) => !s)}
                className="font-mono text-[11px] uppercase tracking-widest text-neutral-500 hover:text-brand-400"
              >
                {showScript ? '▾ Hide script' : '▸ Show script for this segment'}
              </button>
              {showScript && (
                <pre className="mt-2 max-h-72 overflow-y-auto whitespace-pre-wrap border-l-2 border-neutral-700 bg-black/50 p-3 font-mono text-xs leading-relaxed text-neutral-400">
                  {segment.script_excerpt}
                </pre>
              )}
            </div>
          )}
        </div>
      )}

      {showHeader && <PushedToPlan segment={segment} h={h} />}

      <BestPicks segment={segment} h={h} />

      <div>
        <div className="mb-2 flex flex-wrap items-center gap-x-3 gap-y-1">
          <p className="font-mono text-[11px] uppercase tracking-widest text-neutral-500">
            Keywords — pick the ones to fetch
          </p>
          {notYetRun.length > 0 && (
            <button
              onClick={() => h.selectMany(notYetRun.map((k) => k.id))}
              className="font-mono text-[11px] uppercase tracking-widest text-brand-400 hover:text-brand-300"
            >
              + Select {notYetRun.length} not yet run
            </button>
          )}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {segment.keywords.map((k) => (
            <KeywordChip
              key={k.id}
              keyword={k}
              color={h.colorOf(k.id)}
              selected={h.isSelected(k.id)}
              onToggle={() => h.toggle(k.id)}
              onDelete={() => h.deleteKeyword(k.id)}
            />
          ))}
          <form onSubmit={submitKeyword} className="inline-flex">
            <input
              value={newKeyword}
              onChange={(e) => setNewKeyword(e.target.value)}
              placeholder="+ add your own keyword"
              className="w-52 border-2 border-dashed border-neutral-700 bg-transparent px-2.5 py-1 font-mono text-xs text-neutral-200 placeholder-neutral-600 outline-none focus:border-brand-600"
            />
          </form>
        </div>
      </div>

      {withResults.length > 0 && (
        <div className="space-y-3">
          {withResults.map((k) => (
            <KeywordGroup
              key={k.id}
              keyword={k}
              color={h.colorOf(k.id)}
              onPlay={(v, m) => h.play(segment, k, v, m)}
              onRerun={() => h.rerun(k.id)}
              onFresh={() => h.fresh(k.id)}
              clipFor={h.clipFor}
              onDownload={(v, m) => h.download(segment, [{ video: v, moment: m }])}
              pickFor={(v, m) => h.pickFor(segment.id, v.video_id, m.start, m.end)}
              onPush={(v, m) => h.push(segment, k, v, m)}
              onUnpick={h.unpick}
            />
          ))}
        </div>
      )}
    </Card>
  )
}
