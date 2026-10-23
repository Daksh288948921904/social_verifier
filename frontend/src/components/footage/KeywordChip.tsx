import type { FootageKeyword } from '../../api/types'
import { isRunning } from './format'

function StatusTag({ keyword }: { keyword: FootageKeyword }) {
  switch (keyword.status) {
    case 'queued':
      return <span className="opacity-70">· queued</span>
    case 'searching':
    case 'analyzing':
      return <span className="h-2.5 w-2.5 animate-spin rounded-full border-2 border-current border-t-transparent" />
    case 'done':
      return <span className="opacity-70">· {keyword.videos.length} videos</span>
    case 'error':
      return <span className="text-brand-400">· failed</span>
    default:
      return null
  }
}

export function KeywordChip({
  keyword,
  color,
  selected,
  onToggle,
  onDelete,
}: {
  keyword: FootageKeyword
  color: string
  selected: boolean
  onToggle: () => void
  onDelete: () => void
}) {
  const running = isRunning(keyword.status)
  const tooltip = [
    keyword.rationale,
    running ? keyword.progress : null,
    keyword.status === 'error' ? keyword.error_message : null,
    keyword.status === 'done' ? 'Already fetched -- select it again to re-run' : null,
  ].filter(Boolean).join('\n')

  return (
    <span
      className={`group inline-flex items-stretch border-2 font-mono text-xs transition ${
        running ? 'cursor-wait' : ''
      }`}
      style={{
        borderColor: color,
        backgroundColor: selected ? color : 'transparent',
        color: selected ? '#000' : color,
      }}
      title={tooltip || undefined}
    >
      <button
        type="button"
        onClick={onToggle}
        disabled={running}
        aria-pressed={selected}
        className="inline-flex items-center gap-1.5 px-2.5 py-1 font-bold disabled:cursor-wait"
      >
        <span
          className="flex h-3 w-3 items-center justify-center border text-[9px] leading-none"
          style={{ borderColor: selected ? '#000' : color }}
        >
          {selected ? '✓' : ''}
        </span>
        {keyword.text}
        <StatusTag keyword={keyword} />
      </button>
      {!running && (
        <button
          type="button"
          onClick={onDelete}
          aria-label={`Remove keyword ${keyword.text}`}
          className="px-1.5 opacity-40 transition hover:opacity-100"
          style={{ borderLeft: `1px solid ${selected ? '#0004' : `${color}55`}` }}
        >
          ✕
        </button>
      )}
    </span>
  )
}
