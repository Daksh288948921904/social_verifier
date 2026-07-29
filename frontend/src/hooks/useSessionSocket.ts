import { useEffect, useRef, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { wsBase } from '../api/base'
import type { SessionEvent } from '../api/types'

export type ConnectionStatus = 'connecting' | 'open' | 'closed'

export function useSessionSocket(sessionId: string) {
  const queryClient = useQueryClient()
  const [connectionStatus, setConnectionStatus] = useState<ConnectionStatus>('connecting')
  const [transcriptTicks, setTranscriptTicks] = useState<{ text: string; start: number }[]>([])
  const [inProgress, setInProgress] = useState<{ title: string; start: number; end: number } | null>(null)
  const [errors, setErrors] = useState<string[]>([])
  const wsRef = useRef<WebSocket | null>(null)

  useEffect(() => {
    // StrictMode (dev) double-invokes this effect: mount, cleanup, mount again.
    // Closing a WebSocket while it's still CONNECTING doesn't reliably abort
    // the handshake before the second mount opens another one, so without
    // this guard both sockets can end up OPEN and each deliver their own copy
    // of every event -- doubling transcript ticks, errors, etc.
    let active = true
    const ws = new WebSocket(`${wsBase()}/api/sessions/${sessionId}/events`)
    wsRef.current = ws

    ws.onopen = () => active && setConnectionStatus('open')
    ws.onclose = () => active && setConnectionStatus('closed')
    ws.onerror = () => active && setConnectionStatus('closed')

    ws.onmessage = (event) => {
      if (!active) return
      const data: SessionEvent = JSON.parse(event.data)
      switch (data.type) {
        case 'transcript_tick':
          setTranscriptTicks((prev) => [...prev.slice(-49), { text: data.text, start: data.start }])
          break
        case 'segment_boundary_detected':
          setInProgress({ title: data.title, start: data.start, end: data.end })
          break
        case 'clip_ready':
          setInProgress(null)
          queryClient.invalidateQueries({ queryKey: ['clips', sessionId] })
          break
        case 'error':
          setErrors((prev) => [...prev.slice(-9), data.message])
          break
        case 'status':
          break
      }
    }

    return () => {
      active = false
      ws.close()
    }
  }, [sessionId, queryClient])

  return { connectionStatus, transcriptTicks, inProgress, errors }
}
