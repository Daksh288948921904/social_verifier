import { apiUrl } from '../../api/base'
import type { FootageClip, FootageKeywordStatus } from '../../api/types'

// Each keyword gets its own accent so its chip, its results group and the
// "via" tag on a best-pick all read as the same thing at a glance. Brand red
// is deliberately left out -- it already means "selected"/primary action.
const KEYWORD_COLORS = [
  '#f59e0b', '#22d3ee', '#a3e635', '#c084fc', '#f472b6',
  '#34d399', '#60a5fa', '#fb923c', '#facc15', '#2dd4bf',
]

export function keywordColor(index: number): string {
  return KEYWORD_COLORS[index % KEYWORD_COLORS.length]
}

export function fmtTime(seconds: number | null | undefined): string {
  if (seconds == null || !Number.isFinite(seconds)) return '--:--'
  const s = Math.max(0, Math.floor(seconds))
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  const sec = String(s % 60).padStart(2, '0')
  return h ? `${h}:${String(m).padStart(2, '0')}:${sec}` : `${m}:${sec}`
}

export function youtubeAt(videoId: string, seconds: number): string {
  return `https://www.youtube.com/watch?v=${videoId}&t=${Math.floor(seconds)}s`
}

export function isRunning(status: FootageKeywordStatus): boolean {
  return status === 'queued' || status === 'searching' || status === 'analyzing'
}

export function fitLabel(score: number): { text: string; color: string } {
  if (score >= 70) return { text: 'Strong fit', color: '#34d399' }
  if (score >= 40) return { text: 'Partial fit', color: '#f59e0b' }
  return { text: 'Weak fit', color: '#737373' }
}

// request() errors read like `400 Bad Request: {"detail":"..."}` -- surface
// just the backend's human-readable detail when there is one.
export function errorText(error: unknown): string {
  const message = error instanceof Error ? error.message : String(error)
  const match = message.match(/\{.*\}$/)
  if (match) {
    try {
      const detail = JSON.parse(match[0]).detail
      if (typeof detail === 'string') return detail
    } catch {
      // not JSON after all -- fall through to the raw message
    }
  }
  return message
}

// Matches a moment to its downloaded clip (if any) by video and exact range.
export function clipKey(videoId: string, start: number, end: number): string {
  return `${videoId}:${start}:${end}`
}

export function clipFileUrl(clip: FootageClip): string {
  return apiUrl(`/api/footage/clips/${clip.id}/file`)
}
