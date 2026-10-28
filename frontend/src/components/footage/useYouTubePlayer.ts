import { useEffect, useRef, useState } from 'react'

// Just the slice of YouTube's IFrame Player API used here.
interface YTPlayer {
  getCurrentTime(): number
  loadVideoById(opts: { videoId: string; startSeconds?: number; endSeconds?: number }): void
  destroy(): void
}

interface YTNamespace {
  Player: new (
    el: HTMLElement,
    opts: {
      host?: string
      videoId: string
      playerVars?: Record<string, number | string>
      events?: { onReady?: () => void }
    },
  ) => YTPlayer
}

declare global {
  interface Window {
    YT?: YTNamespace
    onYouTubeIframeAPIReady?: () => void
  }
}

let apiPromise: Promise<YTNamespace> | null = null

function loadApi(): Promise<YTNamespace> {
  if (window.YT?.Player) return Promise.resolve(window.YT)
  if (!apiPromise) {
    apiPromise = new Promise((resolve) => {
      const previous = window.onYouTubeIframeAPIReady
      window.onYouTubeIframeAPIReady = () => {
        previous?.()
        resolve(window.YT!)
      }
      const script = document.createElement('script')
      script.src = 'https://www.youtube.com/iframe_api'
      document.head.appendChild(script)
    })
  }
  return apiPromise
}

/**
 * Embeds a YouTube player via the official IFrame API -- unlike a bare
 * <iframe src>, this lets the page read the current playback time (for the
 * "set start/end to now" buttons) and jump to a range without remounting.
 * The player's iframe is created inside a child div this hook owns, so
 * React never tries to reconcile the element YouTube swaps in.
 */
export function useYouTubePlayer(videoId: string, start: number, end: number | null) {
  const hostRef = useRef<HTMLDivElement>(null)
  const playerRef = useRef<YTPlayer | null>(null)
  const [ready, setReady] = useState(false)
  // Captured once for the initial load; later ranges go through playRange().
  const initial = useRef({ start, end })

  useEffect(() => {
    let cancelled = false
    const mount = document.createElement('div')
    mount.style.width = '100%'
    mount.style.height = '100%'
    hostRef.current?.appendChild(mount)

    loadApi().then((YT) => {
      if (cancelled) return
      const vars: Record<string, number | string> = {
        autoplay: 1,
        rel: 0,
        playsinline: 1,
        start: Math.floor(initial.current.start),
      }
      if (initial.current.end != null) vars.end = Math.ceil(initial.current.end)
      playerRef.current = new YT.Player(mount, {
        host: 'https://www.youtube-nocookie.com',
        videoId,
        playerVars: vars,
        events: { onReady: () => !cancelled && setReady(true) },
      })
    })

    return () => {
      cancelled = true
      playerRef.current?.destroy()
      playerRef.current = null
      mount.remove()
      setReady(false)
    }
  }, [videoId])

  return {
    hostRef,
    ready,
    currentTime: () => playerRef.current?.getCurrentTime() ?? null,
    playRange: (from: number, to: number | null) =>
      playerRef.current?.loadVideoById({
        videoId,
        startSeconds: from,
        ...(to != null ? { endSeconds: to } : {}),
      }),
  }
}
