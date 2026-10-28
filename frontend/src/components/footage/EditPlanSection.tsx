import { useState } from 'react'
import type {
  FootageClip,
  FootageProject,
  FootagePlanBeat,
  FootagePlanClip,
  FootagePlanMode,
  FootagePlanSegment,
} from '../../api/types'
import { Badge } from '../ui/Badge'
import { Button } from '../ui/Button'
import { Card } from '../ui/Card'
import { ClipButton } from './ClipButton'
import { ClipPicker } from './ClipPicker'
import { fmtTime, planClipKey, youtubeAt } from './format'

const ANCHOR_COLOR = '#e5e5e5'

const MODES: { id: FootagePlanMode; icon: string; title: string; desc: string }[] = [
  { id: 'picks', icon: '📌', title: 'My picks only', desc: 'Only the clips you pushed to the plan.' },
  { id: 'auto', icon: '✦', title: 'AI picks', desc: 'The AI chooses from all the footage found.' },
  { id: 'mixed', icon: '📌+✦', title: 'Mine + AI', desc: 'Your picks are always used; the AI fills the gaps.' },
]

const STALE_REASON: Record<FootagePlanMode, string> = {
  picks: "You've pushed or removed clips since this plan was built",
  auto: 'New footage has been found since this plan was built',
  mixed: 'Your picks or the footage found have changed since this plan was built',
}

function sourceTag(c: FootagePlanClip): { text: string; cls: string } {
  if (c.source === 'ai') return { text: `✦ AI chose this${c.score != null ? ` · score ${c.score}` : ''}`, cls: 'text-violet-400' }
  if (c.source === 'custom') return { text: '✎ Your timestamps', cls: 'text-cyan-400' }
  return { text: '📌 AI moment you picked', cls: 'text-neutral-400' }
}

function beatHeading(b: FootagePlanBeat): string {
  if (b.type === 'anchor') return b.added ? 'Anchor on camera — added wording' : 'Anchor on camera'
  if (!b.text) return b.clip_audio ? 'Clip plays on its own, with its sound' : 'Clip plays on its own, muted'
  return b.clip_audio ? 'Voice-over over footage, clip sound kept underneath' : 'Voice-over over muted footage'
}

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
      const head = `[${fmtTime(clock)}] ${beatHeading(b).toUpperCase()}${b.added ? ' [ADDED]' : ''} (~${Math.round(b.est_seconds)}s)`
      out.push('', head)
      if (b.clip) {
        out.push(
          `  Footage: "${b.clip.label}" — ${b.clip.video_title} (${b.clip.source === 'ai' ? 'AI pick' : 'your pick'})`,
          `  Use ${fmtTime(b.clip.start)}–${fmtTime(b.clip.end)} · ${youtubeAt(b.clip.video_id, b.clip.start)}`,
          `  Clip sound: ${b.clip_audio ? 'KEEP original audio' : 'MUTE'}`,
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
              backgroundColor: b.clip ? colorOf(b.clip.keyword_id ?? '') : ANCHOR_COLOR,
              opacity: b.clip ? 0.9 : 0.25,
              borderLeft: bi === 0 && si > 0 ? '2px solid #000' : undefined,
            }}
          />
        )),
      )}
    </div>
  )
}

const TOOL =
  'border border-neutral-700 px-2 py-0.5 font-mono text-[10px] font-bold uppercase tracking-wider text-neutral-300 transition hover:border-neutral-400 hover:text-white disabled:cursor-not-allowed disabled:opacity-30'

interface BeatEdits {
  busy: boolean
  canMoveUp: boolean
  canMoveDown: boolean
  canCutEarlier: boolean
  canCutLater: boolean
  isFirst: boolean
  freshRunning: boolean
  onRemove: () => void
  onMove: (dir: -1 | 1) => void
  onCut: (dir: -1 | 1) => void
  onReplace: () => void
  onFresh: () => void
  onAudio: (on: boolean) => void
  onEditWording: () => void
  onDelete: () => void
}

// Keep the scraped clip's own sound, or mute it.
function AudioToggle({ on, disabled, onChange }: { on: boolean; disabled: boolean; onChange: (on: boolean) => void }) {
  const opt = (value: boolean, text: string, title: string) => (
    <button
      role="radio"
      aria-checked={on === value}
      disabled={disabled}
      onClick={() => on !== value && onChange(value)}
      title={title}
      className={`px-2 py-0.5 font-mono text-[10px] font-bold uppercase tracking-wider transition disabled:opacity-40 ${
        on === value ? 'bg-neutral-200 text-black' : 'text-neutral-400 hover:text-white'
      }`}
    >
      {text}
    </button>
  )
  return (
    <span role="radiogroup" aria-label="Clip sound" className="inline-flex border border-neutral-600">
      {opt(true, '🔊 Clip sound', "Keep the scraped clip's original audio")}
      {opt(false, '🔇 Mute clip', "Drop the clip's audio — only the anchor is heard")}
    </span>
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
  edits: e,
}: {
  id: string
  beat: FootagePlanBeat
  clock: number
  color: string
  clip: FootageClip | undefined
  onPlay: () => void
  onDownload: () => void
  edits: BeatEdits
}) {
  const isClip = beat.type === 'clip' && beat.clip
  return (
    <li
      id={id}
      className={`grid scroll-mt-32 gap-3 border-l-4 p-3 md:grid-cols-[88px_1fr_280px] ${beat.added ? 'border-dashed bg-cyan-950/10' : 'bg-black/30'}`}
      style={{ borderColor: isClip ? color : beat.added ? '#22d3ee' : '#525252' }}
    >
      <div className="flex items-center gap-2 md:block">
        <p className="font-mono text-xs font-bold text-neutral-300">{fmtTime(clock)}</p>
        <p className="font-mono text-[10px] text-neutral-500">~{Math.round(beat.est_seconds)}s</p>
        <span
          className="mt-1 inline-block px-1.5 py-0.5 font-mono text-[10px] font-bold uppercase tracking-wider"
          style={isClip ? { backgroundColor: color, color: '#000' } : { border: '1px solid #737373', color: '#d4d4d4' }}
        >
          {isClip ? '🎞 Clip' : '🎙 Anchor'}
        </span>
        {beat.added && (
          <span className="mt-1 inline-block font-mono text-[9px] font-bold uppercase tracking-widest text-cyan-400 md:block">
            ＋ Added
          </span>
        )}
        {isClip && (
          <span className="mt-1 inline-block font-mono text-[10px] text-neutral-400 md:block">
            {beat.clip_audio ? '🔊 sound on' : '🔇 muted'}
          </span>
        )}
      </div>

      <div className="min-w-0">
        <div className="mb-1 flex flex-wrap items-center gap-x-3 gap-y-1">
          <p className="font-mono text-[10px] uppercase tracking-widest text-neutral-500">{beatHeading(beat)}</p>
          {!e.isFirst && !beat.added && (
            <span className="flex items-center gap-1 font-mono text-[10px] uppercase tracking-wider text-neutral-600">
              Starts:
              <button className={TOOL} disabled={e.busy || !e.canCutEarlier} onClick={() => e.onCut(-1)}
                title="Move the cut up: this beat starts one script line earlier">▲ line earlier</button>
              <button className={TOOL} disabled={e.busy || !e.canCutLater} onClick={() => e.onCut(1)}
                title="Move the cut down: this beat starts one script line later">▼ line later</button>
            </span>
          )}
        </div>
        {beat.text ? (
          <p className={`whitespace-pre-line text-sm leading-relaxed ${beat.added ? 'text-cyan-100' : 'text-neutral-200'}`}>{beat.text}</p>
        ) : (
          <p className="text-sm italic text-neutral-500">No script read here — the clip runs on its own.</p>
        )}
        {beat.note && <p className="mt-2 text-xs italic text-neutral-500">Direction: {beat.note}</p>}

        {isClip && (
          <div className="mt-3">
            <AudioToggle on={!!beat.clip_audio} disabled={e.busy} onChange={e.onAudio} />
          </div>
        )}

        <div className="mt-3 flex flex-wrap gap-1.5">
          {beat.added ? (
            <>
              {isClip ? (
                <button className={TOOL} disabled={e.busy} onClick={e.onReplace}>⇄ Replace</button>
              ) : (
                <button className={TOOL} disabled={e.busy} onClick={e.onEditWording}>✎ Edit wording</button>
              )}
              <button className={`${TOOL} hover:border-brand-500 hover:text-brand-300`} disabled={e.busy} onClick={e.onDelete}
                title="Take this added beat out of the plan">✕ Delete</button>
            </>
          ) : isClip ? (
            <>
              <button className={TOOL} disabled={e.busy || !e.canMoveUp} onClick={() => e.onMove(-1)}
                title="Shift this clip to the beat above (this beat becomes whatever was there)">↑ Shift clip up</button>
              <button className={TOOL} disabled={e.busy || !e.canMoveDown} onClick={() => e.onMove(1)}
                title="Shift this clip to the beat below">↓ Shift clip down</button>
              <button className={TOOL} disabled={e.busy} onClick={e.onReplace}>⇄ Replace</button>
              <button className={`${TOOL} hover:border-brand-500 hover:text-brand-300`} disabled={e.busy} onClick={e.onRemove}
                title="Take the clip out — the anchor speaks to camera here">✕ Remove clip</button>
              {beat.clip?.keyword_id && (
                <button className={`${TOOL} border-brand-800 text-brand-300`} disabled={e.busy || e.freshRunning} onClick={e.onFresh}
                  title={`Search YouTube again for "${beat.clip.keyword_text}", skipping videos already found`}>
                  {e.freshRunning ? '⟳ Searching…' : `⟳ New videos for “${beat.clip.keyword_text}”`}
                </button>
              )}
            </>
          ) : (
            <button className={`${TOOL} border-brand-800 text-brand-300`} disabled={e.busy} onClick={e.onReplace}>
              ＋ Add footage here
            </button>
          )}
        </div>
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

// The gap between two beats: insert the anchor's own wording or a clip here.
function InsertBar({
  busy,
  onAnchor,
  onClip,
}: {
  busy: boolean
  onAnchor: () => void
  onClip: () => void
}) {
  return (
    <li className="group flex items-center gap-2 py-0.5" aria-label="Insert between beats">
      <span className="h-px flex-1 bg-neutral-800 group-hover:bg-cyan-800" />
      <span className="font-mono text-[9px] uppercase tracking-widest text-neutral-700 group-hover:text-neutral-400">Insert</span>
      <button className={`${TOOL} border-neutral-800 text-neutral-500`} disabled={busy} onClick={onAnchor}
        title="Add the anchor's own wording here (not from the script)">🎙 Anchor wording</button>
      <button className={`${TOOL} border-neutral-800 text-neutral-500`} disabled={busy} onClick={onClip}
        title="Drop a clip in here that plays on its own, between the beats">🎞 Clip</button>
      <span className="h-px flex-1 bg-neutral-800 group-hover:bg-cyan-800" />
    </li>
  )
}

// Inline editor for anchor wording that isn't in the script.
function WordingComposer({
  initial,
  busy,
  onSave,
  onCancel,
}: {
  initial: string
  busy: boolean
  onSave: (text: string) => void
  onCancel: () => void
}) {
  const [text, setText] = useState(initial)
  const words = text.trim() ? text.trim().split(/\s+/).length : 0
  return (
    <li className="space-y-2 border-2 border-dashed border-cyan-800 bg-cyan-950/10 p-3">
      <p className="font-mono text-[11px] uppercase tracking-widest text-cyan-400">🎙 Anchor wording — not from the script</p>
      <textarea
        autoFocus
        value={text}
        onChange={(ev) => setText(ev.target.value)}
        onKeyDown={(ev) => {
          if (ev.key === 'Escape') onCancel()
          if (ev.key === 'Enter' && (ev.metaKey || ev.ctrlKey) && text.trim()) onSave(text)
        }}
        rows={3}
        maxLength={2000}
        placeholder="What the anchor says here, e.g. “But the verdicts were only the beginning…”"
        className="w-full border-2 border-neutral-700 bg-black px-3 py-2 text-sm text-neutral-100 placeholder-neutral-600 outline-none focus:border-cyan-500"
      />
      <div className="flex flex-wrap items-center gap-2">
        <Button size="sm" variant="primary" disabled={busy || !text.trim()} onClick={() => onSave(text)}>Save wording</Button>
        <Button size="sm" variant="ghost" onClick={onCancel}>Cancel</Button>
        <span className="font-mono text-[10px] text-neutral-500">
          {words} words · ~{Math.round(words / 2.5)}s on camera · ⌘↵ to save
        </span>
      </div>
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
      <p className="text-xs font-bold uppercase leading-tight text-neutral-100">{c.label || 'Untitled clip'}</p>
      <p className="line-clamp-2 font-mono text-[10px] text-neutral-500">
        {c.video_title}
        {c.keyword_text && <> · via <span style={{ color }}>“{c.keyword_text}”</span></>}
      </p>
      <p className={`font-mono text-[9px] uppercase tracking-wider ${sourceTag(c).cls}`}>{sourceTag(c).text}</p>
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
  onSave,
  saving,
  candidatesFor,
  onFresh,
  isKeywordRunning,
}: {
  project: FootageProject
  colorOf: (keywordId: string) => string
  clipFor: (c: FootagePlanClip) => FootageClip | undefined
  onBuild: (mode: FootagePlanMode) => void
  building: boolean
  onPlay: (segmentId: string, c: FootagePlanClip) => void
  onDownload: (segmentPosition: number, clips: FootagePlanClip[]) => void
  onSave: (segmentId: string, beats: FootagePlanBeat[]) => void
  saving: boolean
  candidatesFor: (segmentId: string) => FootagePlanClip[]
  onFresh: (keywordId: string) => void
  isKeywordRunning: (keywordId: string) => boolean
}) {
  const ep = project.edit_plan
  const [picker, setPicker] = useState<{ segment: FootagePlanSegment; index: number; insert?: boolean } | null>(null)
  // Anchor wording being typed: inserted before beat `index`, or editing it.
  const [composer, setComposer] = useState<{ segmentId: string; index: number; edit: boolean } | null>(null)
  const edited = !!ep?.plan?.edited
  const segments = ep?.plan?.segments ?? []
  const isBuilding = building || ep?.status === 'building'
  const pickCount = project.picks.length
  const [mode, setMode] = useState<FootagePlanMode>(ep?.mode ?? (pickCount ? 'picks' : 'auto'))
  const builtMode = ep?.plan?.mode ?? ep?.mode
  const needsPicks = mode === 'picks' && pickCount === 0
  const t = totals(segments)
  const notDownloaded = segments.flatMap((s) =>
    s.beats.filter((b) => b.clip && (!clipFor(b.clip) || clipFor(b.clip)?.status === 'error')).map((b) => ({ s, c: b.clip! })),
  )
  const downloaded = t.clips.filter((c) => clipFor(c)?.status === 'done').length

  // ---- hand edits: each one rewrites one segment's beats and saves it.
  // Script lines always stay in order; only which beat they belong to, and
  // what plays over each beat, changes. Added beats (anchor wording or an
  // inserted clip) sit outside the script, so moves and cuts skip over them.
  const lines = (b: FootagePlanBeat) => b.text.split('\n')
  const save = (s: FootagePlanSegment, beats: FootagePlanBeat[]) => onSave(s.segment_id, beats)
  const asAnchor = (b: FootagePlanBeat): FootagePlanBeat => ({ ...b, type: 'anchor', clip: null, note: '', clip_audio: false })
  // Nearest script (non-added) beat from i in direction dir, or -1.
  function scriptNeighbor(s: FootagePlanSegment, i: number, dir: -1 | 1) {
    for (let j = i + dir; j >= 0 && j < s.beats.length; j += dir) if (!s.beats[j].added) return j
    return -1
  }

  function removeClip(s: FootagePlanSegment, i: number) {
    save(s, s.beats.map((b, j) => (j === i ? asAnchor(b) : b)))
  }
  function moveClip(s: FootagePlanSegment, i: number, dir: -1 | 1) {
    const j = scriptNeighbor(s, i, dir)
    const beats = [...s.beats]
    // Swap what plays over the two beats; their script lines stay put.
    const a = beats[i]
    const b = beats[j]
    beats[i] = { ...a, type: b.type, clip: b.clip, note: b.note, clip_audio: b.clip_audio }
    beats[j] = { ...b, type: a.type, clip: a.clip, note: a.note, clip_audio: a.clip_audio }
    save(s, beats)
  }
  function moveCut(s: FootagePlanSegment, i: number, dir: -1 | 1) {
    const p = scriptNeighbor(s, i, -1)
    const beats = [...s.beats]
    const prev = lines(beats[p])
    const cur = lines(beats[i])
    if (dir === -1) cur.unshift(prev.pop()!)
    else prev.push(cur.shift()!)
    beats[p] = { ...beats[p], text: prev.join('\n') }
    beats[i] = { ...beats[i], text: cur.join('\n') }
    save(s, beats)
  }
  function chooseClip(s: FootagePlanSegment, i: number, clip: FootagePlanClip | null, insert = false) {
    if (insert && clip) {
      // An inserted clip has nothing read over it, so its own sound is on unless
      // it was pushed muted.
      const beat: FootagePlanBeat = {
        type: 'clip', text: '', est_seconds: clip.end - clip.start, note: '', clip, added: true, clip_audio: clip.clip_audio ?? true,
      }
      save(s, [...s.beats.slice(0, i), beat, ...s.beats.slice(i)])
    } else {
      save(s, s.beats.map((b, j) => (j !== i ? b : clip ? { ...b, type: 'clip', clip, note: '', clip_audio: clip.clip_audio ?? b.clip_audio } : asAnchor(b))))
    }
    setPicker(null)
  }
  function setAudio(s: FootagePlanSegment, i: number, on: boolean) {
    save(s, s.beats.map((b, j) => (j === i ? { ...b, clip_audio: on } : b)))
  }
  function deleteAdded(s: FootagePlanSegment, i: number) {
    save(s, s.beats.filter((_, j) => j !== i))
  }
  function saveWording(s: FootagePlanSegment, i: number, edit: boolean, text: string) {
    const beat: FootagePlanBeat = { type: 'anchor', text: text.trim(), est_seconds: 0, note: '', clip: null, added: true }
    save(s, edit ? s.beats.map((b, j) => (j === i ? beat : b)) : [...s.beats.slice(0, i), beat, ...s.beats.slice(i)])
    setComposer(null)
  }

  let clock = 0
  return (
    <Card id="edit-plan" className="scroll-mt-28 space-y-5 p-4 sm:p-5">
      <div className="flex flex-wrap items-start gap-3">
        <div className="min-w-0 flex-1">
          <p className="font-mono text-[11px] uppercase tracking-widest text-brand-500">Final step</p>
          <h2 className="font-display text-3xl uppercase leading-none tracking-wide text-neutral-50">🎬 Edit plan — full script</h2>
          <p className="mt-2 max-w-2xl text-sm text-neutral-400">
            Your whole script, beat by beat: where the anchor speaks to camera, and where a clip runs under the
            anchor's voice-over — with the exact part of the video to use. Choose who picks the clips below.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button
            variant="primary"
            onClick={() => {
              if (edited && !window.confirm('Rebuilding replaces the edits you made to this plan. Continue?')) return
              onBuild(mode)
            }}
            disabled={isBuilding || needsPicks}
            title={needsPicks ? 'Push some clips first, or switch to AI picks' : undefined}
          >
            {isBuilding ? 'Building…' : segments.length ? '↻ Rebuild plan' : 'Build edit plan'}
          </Button>
          {segments.length > 0 && (
            <Button onClick={() => downloadText(`${project.title || 'edit-plan'} rundown.txt`, rundownText(project, segments))}>
              Export rundown (.txt)
            </Button>
          )}
        </div>
      </div>

      <div>
        <p className="mb-2 font-mono text-[11px] uppercase tracking-widest text-neutral-500">Who picks the clips?</p>
        <div className="grid gap-2 sm:grid-cols-3" role="radiogroup" aria-label="Who picks the clips">
          {MODES.map((m) => (
            <button
              key={m.id}
              role="radio"
              aria-checked={mode === m.id}
              onClick={() => setMode(m.id)}
              className={`border-2 p-3 text-left transition ${
                mode === m.id ? 'border-brand-500 bg-brand-950/40' : 'border-neutral-800 hover:border-neutral-600'
              }`}
            >
              <p className="font-display text-lg uppercase tracking-wide text-neutral-100">
                <span className="mr-1.5">{m.icon}</span>{m.title}
                {builtMode === m.id && segments.length > 0 && (
                  <span className="ml-2 align-middle font-mono text-[9px] tracking-widest text-brand-400">current plan</span>
                )}
              </p>
              <p className="text-xs text-neutral-400">{m.desc}</p>
              {m.id !== 'auto' && (
                <p className="mt-1 font-mono text-[10px] text-neutral-500">
                  {pickCount} clip{pickCount === 1 ? '' : 's'} pushed
                </p>
              )}
            </button>
          ))}
        </div>
      </div>

      {isBuilding && (
        <Badge tone="info" dot pulse>Writing the plan, one segment at a time…</Badge>
      )}
      {edited && !isBuilding && segments.length > 0 && (
        <p className="font-mono text-[11px] uppercase tracking-widest text-cyan-400">
          ✎ Edited by you — changes save automatically{saving ? ' · saving…' : ''}
        </p>
      )}
      {ep?.status === 'error' && <p className="font-mono text-sm text-brand-400">{ep.error_message}</p>}
      {ep?.stale && !isBuilding && builtMode && (
        <p className="border-l-2 border-orange-500 pl-3 font-mono text-xs text-orange-400">
          {STALE_REASON[builtMode]} — rebuild it to bring it up to date.
        </p>
      )}
      {!segments.length && !isBuilding && ep?.status !== 'error' && (
        <p className="border-2 border-dashed border-neutral-800 p-5 text-center font-mono text-sm text-neutral-500">
          {mode === 'auto'
            ? 'Build the plan and the AI will place its best footage in your script. Segments with no footage fetched yet are planned as anchor on camera.'
            : needsPicks
              ? 'Push clips to the plan first: press 📌 Push to plan on any moment above, or open a video and set your own timestamps. Or switch to AI picks.'
              : mode === 'mixed'
                ? `Your ${pickCount} pushed clip${pickCount === 1 ? '' : 's'} will always be used, and the AI fills the gaps with its best footage.`
                : `${pickCount} clip${pickCount === 1 ? '' : 's'} pushed — build the plan to place ${pickCount === 1 ? 'it' : 'them'} in your script. Segments with no pushed clips are planned as anchor on camera.`}
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
                  <ol className="space-y-1">
                    {[...s.beats, null].map((b, i) => {
                      const busy = saving || isBuilding
                      const composing = composer?.segmentId === s.segment_id && composer.index === i
                      const gap =
                        composing && !composer.edit ? (
                          <WordingComposer key={`c${i}`} initial="" busy={busy}
                            onSave={(text) => saveWording(s, i, false, text)} onCancel={() => setComposer(null)} />
                        ) : (
                          <InsertBar key={`g${i}`} busy={busy}
                            onAnchor={() => setComposer({ segmentId: s.segment_id, index: i, edit: false })}
                            onClip={() => setPicker({ segment: s, index: i, insert: true })} />
                        )
                      if (!b) return gap
                      if (composing && composer.edit) {
                        return [gap, <WordingComposer key={`e${i}`} initial={b.text} busy={busy}
                          onSave={(text) => saveWording(s, i, true, text)} onCancel={() => setComposer(null)} />]
                      }
                      const at = clock
                      clock += b.est_seconds
                      const color = b.clip ? colorOf(b.clip.keyword_id ?? '') : ANCHOR_COLOR
                      const prev = scriptNeighbor(s, i, -1)
                      return [
                        gap,
                        <BeatRow
                          key={i}
                          id={`plan-${s.segment_id}-${i}`}
                          beat={b}
                          clock={at}
                          color={color}
                          clip={b.clip ? clipFor(b.clip) : undefined}
                          onPlay={() => b.clip && onPlay(s.segment_id, b.clip)}
                          onDownload={() => b.clip && onDownload(s.position, [b.clip])}
                          edits={{
                            busy,
                            isFirst: prev < 0,
                            canMoveUp: prev >= 0,
                            canMoveDown: scriptNeighbor(s, i, 1) >= 0,
                            canCutEarlier: prev >= 0 && lines(s.beats[prev]).length > 1,
                            canCutLater: prev >= 0 && lines(b).length > 1,
                            freshRunning: !!b.clip?.keyword_id && isKeywordRunning(b.clip.keyword_id),
                            onRemove: () => removeClip(s, i),
                            onMove: (dir) => moveClip(s, i, dir),
                            onCut: (dir) => moveCut(s, i, dir),
                            onReplace: () => setPicker({ segment: s, index: i }),
                            onFresh: () => b.clip?.keyword_id && onFresh(b.clip.keyword_id),
                            onAudio: (on) => setAudio(s, i, on),
                            onEditWording: () => setComposer({ segmentId: s.segment_id, index: i, edit: true }),
                            onDelete: () => deleteAdded(s, i),
                          }}
                        />,
                      ]
                    })}
                  </ol>
                </div>
              )
            })}
          </div>
        </>
      )}

      {picker && (
        <ClipPicker
          title={`Segment ${String(picker.segment.position + 1).padStart(2, '0')} — ${picker.segment.title}`}
          lines={picker.insert ? '' : picker.segment.beats[picker.index]?.text ?? ''}
          candidates={candidatesFor(picker.segment.segment_id)}
          current={picker.insert ? null : picker.segment.beats[picker.index]?.clip ?? null}
          inserting={picker.insert || !!picker.segment.beats[picker.index]?.added}
          usedKeys={new Set(segments.flatMap((s) => s.beats.filter((b) => b.clip).map((b) => planClipKey(b.clip!))))}
          colorOf={colorOf}
          onChoose={(clip) => chooseClip(picker.segment, picker.index, clip, picker.insert)}
          onPreview={(clip) => onPlay(picker.segment.segment_id, clip)}
          onClose={() => setPicker(null)}
        />
      )}
    </Card>
  )
}
