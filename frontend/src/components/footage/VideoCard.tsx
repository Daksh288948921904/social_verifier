import type { FootageClip, FootageMoment, FootageVideo } from '../../api/types'
import { ClipButton } from './ClipButton'
import { MomentTimeline } from './MomentTimeline'
import { fitLabel, fmtTime } from './format'

export function VideoCard({
  video,
  color,
  onPlay,
  clipFor,
  onDownload,
}: {
  video: FootageVideo
  color: string
  onPlay: (video: FootageVideo, moment: FootageMoment | null) => void
  clipFor: (video: FootageVideo, moment: FootageMoment) => FootageClip | undefined
  onDownload: (video: FootageVideo, moment: FootageMoment) => void
}) {
  const fit = video.relevance != null ? fitLabel(video.relevance) : null
  const best = video.moments[0] ?? null

  return (
    <div className="flex flex-col border-2 border-neutral-800 bg-neutral-950 transition hover:border-neutral-600">
      <button className="group relative block text-left" onClick={() => onPlay(video, best)}>
        <img
          src={video.thumbnail_url ?? `https://i.ytimg.com/vi/${video.video_id}/mqdefault.jpg`}
          alt=""
          loading="lazy"
          className="aspect-video w-full object-cover opacity-90 transition group-hover:opacity-100"
        />
        <span className="absolute inset-0 flex items-center justify-center opacity-0 transition group-hover:opacity-100">
          <span className="bg-black/80 px-3 py-1 font-display text-lg uppercase text-white">
            ▶ {best ? `Play from ${fmtTime(best.start)}` : 'Play'}
          </span>
        </span>
        {video.duration_seconds != null && (
          <span className="absolute bottom-1.5 right-1.5 bg-black/85 px-1.5 font-mono text-[11px] text-neutral-200">
            {fmtTime(video.duration_seconds)}
          </span>
        )}
        {!video.has_transcript && video.analyzed && (
          <span
            className="absolute left-1.5 top-1.5 bg-black/85 px-1.5 font-mono text-[10px] uppercase tracking-wider text-neutral-400"
            title="This video has no captions, so it was judged from its title, description and chapters only"
          >
            no captions
          </span>
        )}
      </button>

      <div className="flex flex-1 flex-col gap-2 p-3">
        {video.analyzed && fit ? (
          <div className="flex items-center gap-2">
            <div className="h-1.5 flex-1 bg-neutral-800">
              <div className="h-full" style={{ width: `${video.relevance}%`, backgroundColor: fit.color }} />
            </div>
            <span className="font-mono text-[11px] font-bold uppercase" style={{ color: fit.color }}>
              {fit.text} · {video.relevance}
            </span>
          </div>
        ) : (
          <div className="flex items-center gap-2 font-mono text-[11px] uppercase tracking-wider text-neutral-500">
            <span className="h-3 w-3 animate-spin rounded-full border-2 border-neutral-600 border-t-transparent" />
            Analysing…
          </div>
        )}

        <div>
          <h4 className="line-clamp-2 text-sm font-bold leading-snug text-neutral-100" title={video.title}>
            {video.title}
          </h4>
          <p className="font-mono text-[11px] text-neutral-500">{video.channel}</p>
        </div>

        {video.verdict && <p className="text-xs leading-relaxed text-neutral-400">{video.verdict}</p>}

        {video.moments.length > 0 && (
          <>
            <MomentTimeline video={video} onSelect={(m) => onPlay(video, m)} color={color} />
            <ol className="space-y-1.5">
              {video.moments.map((m) => (
                <li
                  key={`${m.start}-${m.end}`}
                  className="border border-neutral-800 bg-black/40 transition hover:border-neutral-500"
                >
                  <button onClick={() => onPlay(video, m)} className="group w-full p-2 pb-1.5 text-left">
                    <div className="flex items-baseline gap-2">
                      <span
                        className="shrink-0 px-1.5 font-mono text-[11px] font-bold text-black"
                        style={{ backgroundColor: color }}
                      >
                        {fmtTime(m.start)}–{fmtTime(m.end)}
                      </span>
                      <span className="text-xs font-bold uppercase text-neutral-200 group-hover:text-white">
                        {m.label}
                      </span>
                    </div>
                    {m.estimated && (
                      <p className="mt-1 font-mono text-[10px] uppercase tracking-wider text-orange-400">
                        ≈ Estimated time — no captions to confirm it
                      </p>
                    )}
                    <p className="mt-1 text-xs text-neutral-400">{m.description}</p>
                    {m.fit && (
                      <p className="mt-1 text-[11px] italic text-neutral-500">↳ {m.fit}</p>
                    )}
                  </button>
                  <div className="px-2 pb-2">
                    <ClipButton clip={clipFor(video, m)} onDownload={() => onDownload(video, m)} compact />
                  </div>
                </li>
              ))}
            </ol>
          </>
        )}
        {video.analyzed && video.moments.length === 0 && (
          <p className="font-mono text-[11px] text-neutral-600">No usable moments found in this video.</p>
        )}
      </div>
    </div>
  )
}
