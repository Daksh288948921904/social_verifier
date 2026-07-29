import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { api } from '../api/client'
import { NavBar } from '../components/ui/NavBar'
import { Button } from '../components/ui/Button'
import { Badge } from '../components/ui/Badge'
import { Card } from '../components/ui/Card'
import { Skeleton } from '../components/ui/Skeleton'

function detectSourceType(url: string): string {
  return /youtube\.com|youtu\.be/.test(url) ? 'YouTube Live' : 'Direct HLS/RTMP'
}

export function StartSessionPage() {
  const [url, setUrl] = useState('')
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const { data: sessions, isLoading } = useQuery({ queryKey: ['sessions'], queryFn: api.listSessions })

  const createSession = useMutation({
    mutationFn: (url: string) => api.createSession(url),
    onSuccess: (session) => {
      queryClient.invalidateQueries({ queryKey: ['sessions'] })
      navigate(`/sessions/${session.id}`)
    },
  })

  return (
    <div className="mx-auto max-w-2xl px-4 py-12">
      <NavBar />

      <div className="mb-8 animate-slide-up">
        <h1 className="mb-2 font-display text-5xl uppercase leading-[0.95] tracking-wide text-neutral-50 sm:text-6xl">
          Capture the story <span className="bg-brand-500 px-2 text-black">as it breaks</span>
        </h1>
        <p className="mt-3 max-w-md font-mono text-sm text-neutral-500">
          Paste a live newsroom broadcast URL. We'll transcribe it in real time, detect story
          boundaries, and cut individual clips automatically.
        </p>
      </div>

      <Card className="animate-slide-up p-2" style={{ animationDelay: '60ms' }}>
        <form
          className="flex flex-col gap-2 sm:flex-row"
          onSubmit={(e) => {
            e.preventDefault()
            if (url.trim()) createSession.mutate(url.trim())
          }}
        >
          <input
            className="flex-1 border-2 border-transparent bg-black px-4 py-3 font-mono text-sm text-neutral-100 placeholder-neutral-600 outline-none transition focus:border-brand-600"
            placeholder="https://www.youtube.com/@channel/live or an .m3u8/rtmp:// URL"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
          />
          <Button type="submit" variant="primary" disabled={createSession.isPending || !url.trim()}>
            {createSession.isPending ? 'Starting…' : 'Start Capturing'}
          </Button>
        </form>
      </Card>
      {url.trim() && (
        <p className="mt-2 pl-1 font-mono text-xs uppercase text-neutral-600">Detected: {detectSourceType(url)}</p>
      )}
      {createSession.isError && (
        <p className="mt-2 pl-1 font-mono text-sm text-brand-400">{(createSession.error as Error).message}</p>
      )}

      <h2 className="mb-3 mt-10 font-display text-lg uppercase tracking-widest text-neutral-500">Sessions</h2>
      <div className="space-y-2">
        {isLoading &&
          [0, 1].map((i) => <Skeleton key={i} className="h-14 w-full" />)}

        {sessions?.map((s, i) => (
          <button
            key={s.id}
            onClick={() => navigate(`/sessions/${s.id}`)}
            style={{ animationDelay: `${i * 40}ms` }}
            className="group flex w-full animate-slide-up items-center justify-between border-2 border-neutral-800 bg-neutral-950/90 px-4 py-3.5 text-left shadow-[4px_4px_0_0_#000] transition-all duration-150 hover:-translate-x-[2px] hover:-translate-y-[2px] hover:border-brand-600 hover:shadow-[6px_6px_0_0_#000]"
          >
            <span className="truncate font-mono text-sm text-neutral-300 transition group-hover:text-neutral-100">
              {s.url}
            </span>
            <Badge
              className="ml-3 shrink-0"
              tone={s.status === 'capturing' ? 'success' : s.status === 'error' ? 'danger' : 'neutral'}
              dot
              pulse={s.status === 'capturing'}
            >
              {s.status}
            </Badge>
          </button>
        ))}
        {sessions?.length === 0 && (
          <p className="border-2 border-dashed border-neutral-800 p-6 text-center font-mono text-sm text-neutral-600">
            No sessions yet — start one above.
          </p>
        )}
      </div>
    </div>
  )
}
