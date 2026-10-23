import type { FootageMoment, FootageVideo } from '../../api/types'
import { fmtTime } from './format'

export function MomentTimeline({
  video,
  active,
  onSelect,
  color,
  tall,
}: {
  video: FootageVideo
  active?: FootageMoment | null
  onSelect: (moment: FootageMoment) => void
  color: string
  tall?: boolean
}) {
  if (video.moments.length === 0) return null
  // Duration is unknown when captions couldn't be fetched; scale to the
  // last moment instead so the blocks still sit in the right order.
  const total = video.duration_seconds || Math.max(...video.moments.map((m) => m.end)) * 1.1
  const byTime = [...video.moments].sort((a, b) => a.start - b.start)

  return (
    <div>
      <div
        className={`relative w-full border border-neutral-800 bg-neutral-900 ${tall ? 'h-7' : 'h-4'}`}
        aria-label="Where the matching moments are in this video"
      >
        {byTime.map((m) => {
          const left = (m.start / total) * 100
          const width = Math.max(((m.end - m.start) / total) * 100, 1.2)
          const isActive = active && active.start === m.start && active.end === m.end
          return (
            <button
              key={`${m.start}-${m.end}`}
              onClick={(e) => {
                e.stopPropagation()
                onSelect(m)
              }}
              title={`${fmtTime(m.start)}–${fmtTime(m.end)} · ${m.label}`}
              className="absolute top-0 h-full transition hover:brightness-125 focus:outline-none"
              style={{
                left: `${left}%`,
                width: `${width}%`,
                backgroundColor: color,
                opacity: active && !isActive ? 0.35 : 0.85,
                outline: isActive ? '2px solid #fff' : undefined,
              }}
            />
          )
        })}
      </div>
      <div className="mt-0.5 flex justify-between font-mono text-[10px] text-neutral-600">
        <span>0:00</span>
        <span>{video.duration_seconds ? fmtTime(video.duration_seconds) : 'length unknown'}</span>
      </div>
    </div>
  )
}
