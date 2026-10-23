import { apiUrl } from '../../api/base'
import type { FootageClip } from '../../api/types'
import { Card } from '../ui/Card'
import { ClipButton } from './ClipButton'
import { fmtTime } from './format'

export function DownloadsPanel({
  projectId,
  clips,
  onRetry,
  onDelete,
}: {
  projectId: string
  clips: FootageClip[]
  onRetry: (clip: FootageClip) => void
  onDelete: (clip: FootageClip) => void
}) {
  if (clips.length === 0) return null
  const ready = clips.filter((c) => c.status === 'done').length
  const cutting = clips.filter((c) => c.status === 'downloading').length
  const failed = clips.filter((c) => c.status === 'error').length

  return (
    <Card id="downloads" className="mb-6 scroll-mt-28 p-4">
      <div className="mb-3 flex flex-wrap items-center gap-x-4 gap-y-2">
        <h2 className="font-display text-2xl uppercase tracking-wide text-neutral-50">⬇ Downloaded clips</h2>
        <span className="font-mono text-[11px] uppercase tracking-widest text-neutral-500">
          {ready} ready{cutting ? ` · ${cutting} cutting` : ''}{failed ? ` · ${failed} failed` : ''}
        </span>
        {ready > 0 && (
          <a
            href={apiUrl(`/api/footage/projects/${projectId}/clips.zip`)}
            className="ml-auto border-2 border-black bg-brand-500 px-3 py-1.5 font-display text-base uppercase tracking-wider text-white shadow-[4px_4px_0_0_#000] transition hover:bg-brand-400"
          >
            Download all {ready} as .zip
          </a>
        )}
      </div>
      <ul className="divide-y divide-neutral-800 border border-neutral-800">
        {clips.map((c) => (
          <li key={c.id} className="flex flex-wrap items-center gap-x-3 gap-y-1 px-3 py-2">
            <span className="w-28 shrink-0 font-mono text-xs font-bold text-neutral-300">
              {fmtTime(c.start_seconds)}–{fmtTime(c.end_seconds)}
            </span>
            <div className="min-w-0 flex-1">
              <p className="truncate font-mono text-xs text-neutral-100">{c.filename}</p>
              <p className="truncate text-[11px] text-neutral-500">
                {c.status === 'error' ? <span className="text-brand-400">{c.error_message}</span> : c.video_title}
              </p>
            </div>
            <ClipButton clip={c} onDownload={() => onRetry(c)} compact />
            {c.status !== 'downloading' && (
              <button
                onClick={() => onDelete(c)}
                aria-label={`Remove ${c.filename}`}
                className="font-mono text-xs text-neutral-600 hover:text-brand-400"
              >
                ✕
              </button>
            )}
          </li>
        ))}
      </ul>
    </Card>
  )
}
