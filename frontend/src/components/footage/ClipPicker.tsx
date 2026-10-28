import { useEffect } from 'react'
import type { FootagePlanClip } from '../../api/types'
import { fmtTime, planClipKey } from './format'

// Choose what plays over one beat of the edit plan: any clip you pushed for
// the segment, any AI moment from its scraped videos, or the anchor.
export function ClipPicker({
  title,
  lines,
  candidates,
  current,
  inserting = false,
  usedKeys,
  colorOf,
  onChoose,
  onPreview,
  onClose,
}: {
  title: string
  lines: string
  candidates: FootagePlanClip[]
  current: FootagePlanClip | null
  /** Choosing a clip to drop in between beats, rather than for script lines. */
  inserting?: boolean
  usedKeys: Set<string>
  colorOf: (keywordId: string) => string
  onChoose: (clip: FootagePlanClip | null) => void
  onPreview: (clip: FootagePlanClip) => void
  onClose: () => void
}) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  // Clips not used anywhere in the plan yet come first in each group.
  const unusedFirst = (list: FootagePlanClip[]) =>
    [...list].sort((a, b) => Number(usedKeys.has(planClipKey(a))) - Number(usedKeys.has(planClipKey(b))))
  const picks = unusedFirst(candidates.filter((c) => c.source !== 'ai'))
  const ai = candidates.filter((c) => c.source === 'ai')
  // AI moments grouped by the keyword that found them, best first.
  const byKeyword = new Map<string, FootagePlanClip[]>()
  for (const c of [...ai].sort((a, b) => (b.score ?? 0) - (a.score ?? 0))) {
    const k = c.keyword_text || 'Other'
    byKeyword.set(k, [...(byKeyword.get(k) ?? []), c])
  }
  for (const [k, list] of byKeyword) byKeyword.set(k, unusedFirst(list))
  const currentKey = current ? planClipKey(current) : null

  function Row({ c }: { c: FootagePlanClip }) {
    const key = planClipKey(c)
    const isCurrent = key === currentKey
    const color = colorOf(c.keyword_id ?? '')
    return (
      <li className={`flex gap-3 border p-2 ${isCurrent ? 'border-brand-500 bg-brand-950/30' : 'border-neutral-800 bg-black/40'}`}>
        <button onClick={() => onPreview(c)} className="relative w-36 shrink-0" title="Preview">
          <img
            src={c.thumbnail_url ?? `https://i.ytimg.com/vi/${c.video_id}/mqdefault.jpg`}
            alt=""
            loading="lazy"
            className="aspect-video w-full object-cover"
          />
          <span className="absolute bottom-0.5 left-0.5 px-1 font-mono text-[10px] font-bold text-black" style={{ backgroundColor: color }}>
            ▶ {fmtTime(c.start)}–{fmtTime(c.end)}
          </span>
        </button>
        <div className="min-w-0 flex-1">
          <p className="text-xs font-bold uppercase text-neutral-100">{c.label || 'Untitled clip'}</p>
          {c.description && <p className="line-clamp-2 text-xs text-neutral-400">{c.description}</p>}
          <p className="truncate font-mono text-[10px] text-neutral-500">
            {c.video_title}
            {c.score != null && <span className="text-violet-400"> · score {c.score}</span>}
            {c.source === 'custom' && <span className="text-cyan-400"> · your timestamps</span>}
          </p>
        </div>
        <div className="flex shrink-0 flex-col items-end justify-center gap-1">
          {isCurrent ? (
            <span className="font-mono text-[10px] uppercase tracking-widest text-brand-400">Current</span>
          ) : (
            <button
              onClick={() => onChoose(c)}
              className="border-2 border-brand-600 px-2.5 py-1 font-mono text-[11px] font-bold uppercase text-brand-300 hover:bg-brand-950"
            >
              Use this
            </button>
          )}
          {!isCurrent && usedKeys.has(key) && (
            <span className="font-mono text-[9px] uppercase text-orange-400">Used elsewhere</span>
          )}
        </div>
      </li>
    )
  }

  return (
    <div className="fixed inset-0 z-40 flex animate-fade-in items-start justify-center overflow-y-auto bg-black/85 p-4" onClick={onClose}>
      <div
        className="my-auto w-full max-w-3xl border-2 border-neutral-700 bg-neutral-950 shadow-[8px_8px_0_0_#000]"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-label="Choose a clip"
      >
        <div className="flex items-center justify-between border-b-2 border-neutral-800 px-4 py-2">
          <p className="font-mono text-[11px] uppercase tracking-widest text-neutral-400">
            {inserting ? '＋ Insert clip' : current ? '⇄ Replace clip' : '＋ Add footage'} · {title}
          </p>
          <button onClick={onClose} className="font-mono text-xs uppercase tracking-widest text-neutral-500 hover:text-brand-400">
            Close ✕
          </button>
        </div>
        <div className="space-y-4 p-4">
          {lines && (
            <blockquote className="whitespace-pre-line border-l-2 border-neutral-700 pl-3 text-sm text-neutral-300">{lines}</blockquote>
          )}

          {current && !inserting && (
            <button
              onClick={() => onChoose(null)}
              className="w-full border-2 border-dashed border-neutral-600 p-2 font-mono text-xs uppercase tracking-widest text-neutral-300 hover:border-neutral-300"
            >
              🎙 Use anchor on camera instead
            </button>
          )}

          {picks.length > 0 && (
            <section>
              <p className="mb-2 font-mono text-[11px] uppercase tracking-widest text-brand-400">📌 Clips you pushed</p>
              <ul className="space-y-2">{picks.map((c) => <Row key={planClipKey(c)} c={c} />)}</ul>
            </section>
          )}
          {[...byKeyword.entries()].map(([kw, clips]) => (
            <section key={kw}>
              <p className="mb-2 font-mono text-[11px] uppercase tracking-widest" style={{ color: colorOf(clips[0].keyword_id ?? '') }}>
                ✦ AI moments · “{kw}”
              </p>
              <ul className="space-y-2">{clips.map((c) => <Row key={planClipKey(c)} c={c} />)}</ul>
            </section>
          ))}
          {candidates.length === 0 && (
            <p className="border-2 border-dashed border-neutral-800 p-5 text-center text-sm text-neutral-500">
              No footage for this segment yet. Fetch its keywords (or press ⟳ New videos on one) above, then come back.
            </p>
          )}
          <p className="font-mono text-[10px] text-neutral-600">
            Want a different part of a video? Open it above, set your own timestamps and push it — it will show up here.
          </p>
        </div>
      </div>
    </div>
  )
}
