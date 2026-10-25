import type { FootageClip, FootageProject, FootagePlanBeat, FootagePlanClip, FootagePlanSegment } from '../../api/types'
import { Badge } from '../ui/Badge'
import { Button } from '../ui/Button'
import { Card } from '../ui/Card'
import { ClipButton } from './ClipButton'
import { fmtTime, youtubeAt } from './format'

const ANCHOR_COLOR = '#e5e5e5'

function totals(segments: FootagePlanSegment[]) {
  const beats = segments.flatMap((s) => s.beats)
  const anchor = beats.filter((b) => b.type === 'anchor').reduce((n, b) => n + b.est_seconds, 0)
  const footage = beats.filter((b) => b.type === 'clip').reduce((n, b) => n + b.est_seconds, 0)
  return { anchor, footage, total: anchor + footage, clips: beats.filter((b) => b.clip).map((b) => b.clip!) }
}

// Plain-text rundown an editor can keep open next to their timeline.
function rundownText(project: FootageProject, segments: FootagePlanSegment[]): string {
  const t = totals(segments)
  const out = [
    `EDIT PLAN — ${project.title}`,
    `Est. runtime ${fmtTime(t.total)} · anchor ${fmtTime(t.anchor)} · footage ${fmtTime(t.footage)}`,
    '',
  ]
  let clock = 0
  for (const s of segments) {
    out.push('='.repeat(60), `SEGMENT ${String(s.position + 1).padStart(2, '0')} — ${s.title.toUpperCase()}`, '='.repeat(60))
    for (const b of s.beats) {
      const head = `[${fmtTime(clock)}] ${b.type === 'anchor' ? 'ANCHOR ON CAMERA' : 'CLIP + VOICE-OVER'} (~${Math.round(b.est_seconds)}s)`
      out.push('', head)
      if (b.clip) {
        out.push(
          `  Footage: "${b.clip.label}" — ${b.clip.video_title}`,
          `  Use ${fmtTime(b.clip.start)}–${fmtTime(b.clip.end)} · ${youtubeAt(b.clip.video_id, b.clip.start)}`,
        )
      }
      if (b.note) out.push(`  Direction: ${b.note}`)
      out.push(...b.text.split('\n').map((l) => `    ${l}`))
      clock += b.est_seconds
    }
    out.push('')
  }
  return out.join('\n')
}

function downloadText(filename: string, text: string) {
  const url = URL.createObjectURL(new Blob([text], { type: 'text/plain' }))
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

function ProgramBar({ segments, colorOf }: { segments: FootagePlanSegment[]; colorOf: (keywordId: string) => string }) {
  const total = totals(segments).total || 1
  return (
    <div className="flex h-6 w-full overflow-hidden border border-neutral-800 bg-neutral-900">
      {segments.flatMap((s, si) =>
        s.beats.map((b, bi) => (
          <button
            key={`${s.segment_id}-${bi}`}
            onClick={() => document.getElementById(`plan-${s.segment_id}-${bi}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' })}
            title={`S${si + 1} · ${b.type === 'anchor' ? 'Anchor' : `Clip: ${b.clip?.label}`} · ~${Math.round(b.est_seconds)}s`}
            className="h-full transition hover:brightness-125"
            style={{
              width: `${(b.est_seconds / total) * 100}%`,
              backgroundColor: b.clip ? colorOf(b.clip.keyword_id) : ANCHOR_COLOR,
              opacity: b.clip ? 0.9 : 0.25,
              borderLeft: bi === 0 && si > 0 ? '2px solid #000' : undefined,
            }}
          />
        )),
      )}
    </div>
  )
}

function BeatRow({
  id,
  beat,
  clock,
  color,
  clip,
  onPlay,
  onDownload,
}: {
  id: string
  beat: FootagePlanBeat
  clock: number
  color: string
  clip: FootageClip | undefined
  onPlay: () => void
  onDownload: () => void
}) {
  const isClip = beat.type === 'clip' && beat.clip
  return (
    <li id={id} className="grid scroll-mt-32 gap-3 border-l-4 bg-black/30 p-3 md:grid-cols-[88px_1fr_280px]" style={{ borderColor: isClip ? color : '#525252' }}>
      <div className="flex items-center gap-2 md:block">
        <p className="font-mono text-xs font-bold text-neutral-300">{fmtTime(clock)}</p>
        <p className="font-mono text-[10px] text-neutral-500">~{Math.round(beat.est_seconds)}s</p>
        <span
          className="mt-1 inline-block px-1.5 py-0.5 font-mono text-[10px] font-bold uppercase tracking-wider"
          style={isClip ? { backgroundColor: color, color: '#000' } : { border: '1px solid #737373', color: '#d4d4d4' }}
        >
          {isClip ? '🎞 Clip' : '🎙 Anchor'}
        </span>
      </div>

      <div className="min-w-0">
        <p className="mb-1 font-mono text-[10px] uppercase tracking-widest text-neutral-500">
          {isClip ? 'Voice-over over footage' : 'Anchor on camera'}
        </p>
        <p className="whitespace-pre-line text-sm leading-relaxed text-neutral-200">{beat.text}</p>
        {beat.note && <p className="mt-2 text-xs italic text-neutral-500">Direction: {beat.note}</p>}
      </div>

      {isClip && beat.clip ? (
        <ClipPanel planClip={beat.clip} color={color} shortBy={beat.clip_short_by ?? 0} clip={clip} onPlay={onPlay} onDownload={onDownload} />
      ) : (
        <div className="flex items-center justify-center border border-dashed border-neutral-800 p-3 text-center font-mono text-[11px] uppercase tracking-widest text-neutral-600">
          🎙 Record anchor<br />on camera
        </div>
      )}
    </li>
  )
}

function ClipPanel({
  planClip: c,
  color,
  shortBy,
  clip,
  onPlay,
  onDownload,
}: {
  planClip: FootagePlanClip
  color: string
  shortBy: number
  clip: FootageClip | undefined
  onPlay: () => void
  onDownload: () => void
}) {
  return (
    <div className="space-y-1.5">
      <button onClick={onPlay} className="group relative block w-full">
        <img
          src={c.thumbnail_url ?? `https://i.ytimg.com/vi/${c.video_id}/mqdefault.jpg`}
          alt=""
          loading="lazy"
          className="aspect-video w-full object-cover opacity-90 group-hover:opacity-100"
        />
        <span className="absolute bottom-1 left-1 px-1.5 font-mono text-[11px] font-bold text-black" style={{ backgroundColor: color }}>
          ▶ {fmtTime(c.start)}–{fmtTime(c.end)}
        </span>
      </button>
      <p className="text-xs font-bold uppercase leading-tight text-neutral-100">{c.label}</p>
      <p className="line-clamp-2 font-mono text-[10px] text-neutral-500">
        {c.video_title} · via <span style={{ color }}>“{c.keyword_text}”</span>
      </p>
      {c.estimated && (
        <p className="font-mono text-[10px] uppercase text-orange-400">≈ Estimated time — no captions</p>
      )}
      {shortBy > 0 && (
        <p className="font-mono text-[10px] uppercase text-orange-400">
          Clip is ~{Math.round(shortBy)}s shorter than the narration — extend or add a cutaway
        </p>
      )}
      <ClipButton clip={clip} onDownload={onDownload} compact />
    </div>
  )
}

export function EditPlanSection({
  project,
  colorOf,
  clipFor,
  onBuild,
  building,
  onPlay,
  onDownload,
}: {
  project: FootageProject
  colorOf: (keywordId: string) => string
  clipFor: (c: FootagePlanClip) => FootageClip | undefined
  onBuild: () => void
  building: boolean
  onPlay: (segmentId: string, c: FootagePlanClip) => void
  onDownload: (segmentPosition: number, clips: FootagePlanClip[]) => void
}) {
  const ep = project.edit_plan
  const segments = ep?.plan?.segments ?? []
  const isBuilding = building || ep?.status === 'building'
  const stale = ep?.status === 'done' && ep.moment_count !== project.moment_count
  const t = totals(segments)
  const notDownloaded = segments.flatMap((s) =>
    s.beats.filter((b) => b.clip && (!clipFor(b.clip) || clipFor(b.clip)?.status === 'error')).map((b) => ({ s, c: b.clip! })),
  )
  const downloaded = t.clips.filter((c) => clipFor(c)?.status === 'done').length

  let clock = 0
  return (
    <Card id="edit-plan" className="scroll-mt-28 space-y-5 p-4 sm:p-5">
      <div className="flex flex-wrap items-start gap-3">
        <div className="min-w-0 flex-1">
          <p className="font-mono text-[11px] uppercase tracking-widest text-brand-500">Final step</p>
          <h2 className="font-display text-3xl uppercase leading-none tracking-wide text-neutral-50">🎬 Edit plan — full script</h2>
          <p className="mt-2 max-w-2xl text-sm text-neutral-400">
            Your whole script, beat by beat: where the anchor speaks to camera, and where a fetched clip runs
            under the anchor's voice-over — with the exact part of the video to use.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button variant="primary" onClick={onBuild} disabled={isBuilding}>
            {isBuilding ? 'Building…' : segments.length ? '↻ Rebuild plan' : 'Build edit plan'}
          </Button>
          {segments.length > 0 && (
            <Button onClick={() => downloadText(`${project.title || 'edit-plan'} rundown.txt`, rundownText(project, segments))}>
              Export rundown (.txt)
            </Button>
          )}
        </div>
      </div>

      {isBuilding && (
        <Badge tone="info" dot pulse>Writing the plan, one segment at a time…</Badge>
      )}
      {ep?.status === 'error' && <p className="font-mono text-sm text-brand-400">{ep.error_message}</p>}
      {stale && !isBuilding && (
        <p className="border-l-2 border-orange-500 pl-3 font-mono text-xs text-orange-400">
          New footage has been found since this plan was built — rebuild it to use the new clips.
        </p>
      )}
      {!segments.length && !isBuilding && ep?.status !== 'error' && (
        <p className="border-2 border-dashed border-neutral-800 p-5 text-center font-mono text-sm text-neutral-500">
          Fetch footage for the segments above, then build the plan. Segments with no footage yet are planned as
          anchor on camera.
        </p>
      )}

      {segments.length > 0 && (
        <>
          <div className="space-y-2">
            <div className="flex flex-wrap gap-x-5 gap-y-1 font-mono text-xs text-neutral-400">
              <span>Est. runtime <b className="text-neutral-100">{fmtTime(t.total)}</b></span>
              <span>🎙 Anchor <b className="text-neutral-100">{fmtTime(t.anchor)}</b> ({Math.round((t.anchor / (t.total || 1)) * 100)}%)</span>
              <span>🎞 Footage <b className="text-neutral-100">{fmtTime(t.footage)}</b> ({Math.round((t.footage / (t.total || 1)) * 100)}%)</span>
              <span>{t.clips.length} clips · {downloaded} downloaded</span>
              {notDownloaded.length > 0 && (
                <button
                  onClick={() => {
                    const bySegment = new Map<number, FootagePlanClip[]>()
                    notDownloaded.forEach(({ s, c }) => bySegment.set(s.position, [...(bySegment.get(s.position) ?? []), c]))
                    bySegment.forEach((clips, pos) => onDownload(pos, clips))
                  }}
                  className="uppercase tracking-widest text-brand-400 hover:text-brand-300"
                >
                  ⬇ Download {notDownloaded.length === t.clips.length ? 'all' : 'remaining'} {notDownloaded.length} plan clips
                </button>
              )}
            </div>
            <ProgramBar segments={segments} colorOf={colorOf} />
            <p className="font-mono text-[10px] text-neutral-600">
              Program timeline — grey: anchor on camera · colour: footage (by keyword). Click to jump.
              Durations are estimated from word count (~150 words/min).
            </p>
          </div>

          <div className="space-y-6">
            {segments.map((s) => {
              const segStart = clock
              const segLen = s.beats.reduce((n, b) => n + b.est_seconds, 0)
              return (
                <div key={s.segment_id}>
                  <div className="mb-2 flex items-baseline gap-3 border-b-2 border-neutral-800 pb-1">
                    <span className="font-mono text-[11px] uppercase tracking-widest text-brand-500">
                      Segment {String(s.position + 1).padStart(2, '0')}
                    </span>
                    <span className="font-display text-xl uppercase tracking-wide text-neutral-100">{s.title}</span>
                    <span className="ml-auto font-mono text-[11px] text-neutral-500">
                      {fmtTime(segStart)} · ~{fmtTime(segLen)}
                    </span>
                  </div>
                  <ol className="space-y-2">
                    {s.beats.map((b, i) => {
                      const at = clock
                      clock += b.est_seconds
                      const color = b.clip ? colorOf(b.clip.keyword_id) : ANCHOR_COLOR
                      return (
                        <BeatRow
                          key={i}
                          id={`plan-${s.segment_id}-${i}`}
                          beat={b}
                          clock={at}
                          color={color}
                          clip={b.clip ? clipFor(b.clip) : undefined}
                          onPlay={() => b.clip && onPlay(s.segment_id, b.clip)}
                          onDownload={() => b.clip && onDownload(s.position, [b.clip])}
                        />
                      )
                    })}
                  </ol>
                </div>
              )
            })}
          </div>
        </>
      )}
    </Card>
  )
}
