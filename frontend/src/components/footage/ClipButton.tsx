import type { FootageClip } from '../../api/types'
import { clipFileUrl } from './format'

// One button for the whole life of a clip: queue it, watch it cut, then save
// the finished .mp4 (or retry a failed one).
export function ClipButton({
  clip,
  onDownload,
  compact,
}: {
  clip: FootageClip | undefined
  onDownload: () => void
  compact?: boolean
}) {
  const base = `inline-flex items-center gap-1.5 border-2 font-mono font-bold uppercase tracking-wider transition ${
    compact ? 'px-2 py-0.5 text-[10px]' : 'px-3 py-1.5 text-xs'
  }`

  if (clip?.status === 'done') {
    return (
      <a
        href={clipFileUrl(clip)}
        download={clip.filename}
        onClick={(e) => e.stopPropagation()}
        title={`Save ${clip.filename}`}
        className={`${base} border-emerald-500 bg-emerald-500 text-black hover:bg-emerald-400`}
      >
        ⬇ Save .mp4
      </a>
    )
  }
  if (clip?.status === 'downloading') {
    return (
      <span className={`${base} cursor-wait border-neutral-600 text-neutral-300`}>
        <span className="h-2.5 w-2.5 animate-spin rounded-full border-2 border-current border-t-transparent" />
        Cutting…
      </span>
    )
  }
  return (
    <button
      type="button"
      onClick={(e) => {
        e.stopPropagation()
        onDownload()
      }}
      title={clip?.status === 'error' ? `Failed: ${clip.error_message}` : 'Download just this part of the video'}
      className={`${base} ${
        clip?.status === 'error'
          ? 'border-brand-500 text-brand-400 hover:bg-brand-950'
          : 'border-neutral-600 text-neutral-200 hover:border-neutral-300 hover:text-white'
      }`}
    >
      {clip?.status === 'error' ? '↻ Retry download' : '⬇ Download clip'}
    </button>
  )
}
