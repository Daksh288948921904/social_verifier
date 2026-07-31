import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { api } from '../api/client'
import { NavBar } from '../components/ui/NavBar'
import { Button } from '../components/ui/Button'
import { Badge } from '../components/ui/Badge'
import { Card } from '../components/ui/Card'
import { Skeleton } from '../components/ui/Skeleton'

const STATUS_LABEL: Record<string, string> = {
  downloading: 'Downloading…',
  transcribing: 'Transcribing…',
  extracting_claims: 'Extracting claims…',
  verifying_claims: 'Verifying claims…',
  concluding: 'Concluding…',
  done: 'Done',
  error: 'Failed',
}

export function VerifyStartPage() {
  const [url, setUrl] = useState('')
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const { data: checks, isLoading } = useQuery({ queryKey: ['reel-checks'], queryFn: api.listReelChecks })

  const createCheck = useMutation({
    mutationFn: (url: string) => api.createReelCheck(url),
    onSuccess: (check) => {
      queryClient.invalidateQueries({ queryKey: ['reel-checks'] })
      navigate(`/verify/${check.id}`)
    },
  })

  return (
    <div className="mx-auto max-w-2xl px-4 py-12">
      <NavBar />

      <div className="mb-8 animate-slide-up">
        <div className="mb-3 flex items-center justify-between gap-3">
          <h1 className="font-display text-5xl uppercase leading-[0.95] tracking-wide text-neutral-50 sm:text-6xl">
            Know what's <span className="bg-brand-500 px-2 text-black">actually true</span>
          </h1>
        </div>
        <p className="mt-3 max-w-md font-mono text-sm text-neutral-500">
          Paste a reel/short link. We'll transcribe it, pull out every factual claim with an exact
          quote, and fact-check each one in depth against live web sources.
        </p>
        <button
          onClick={() => navigate('/verify/batch')}
          className="mt-3 font-mono text-xs uppercase tracking-widest text-neutral-500 underline decoration-neutral-700 underline-offset-4 transition hover:text-brand-400 hover:decoration-brand-500"
        >
          Got several links? Check them as a batch →
        </button>
      </div>

      <Card className="animate-slide-up p-2" style={{ animationDelay: '60ms' }}>
        <form
          className="flex flex-col gap-2 sm:flex-row"
          onSubmit={(e) => {
            e.preventDefault()
            if (url.trim()) createCheck.mutate(url.trim())
          }}
        >
          <input
            className="flex-1 border-2 border-transparent bg-black px-4 py-3 font-mono text-sm text-neutral-100 placeholder-neutral-600 outline-none transition focus:border-brand-600"
            placeholder="https://www.youtube.com/shorts/..., tiktok.com/..., instagram.com/reel/..."
            value={url}
            onChange={(e) => setUrl(e.target.value)}
          />
          <Button type="submit" variant="primary" disabled={createCheck.isPending || !url.trim()}>
            {createCheck.isPending ? 'Starting…' : 'Verify'}
          </Button>
        </form>
      </Card>
      {createCheck.isError && (
        <p className="mt-2 pl-1 font-mono text-sm text-brand-400">{(createCheck.error as Error).message}</p>
      )}

      <h2 className="mb-3 mt-10 font-display text-lg uppercase tracking-widest text-neutral-500">
        Past checks
      </h2>
      <div className="space-y-2">
        {isLoading && [0, 1].map((i) => <Skeleton key={i} className="h-14 w-full" />)}

        {checks?.map((c, i) => (
          <button
            key={c.id}
            onClick={() => navigate(`/verify/${c.id}`)}
            style={{ animationDelay: `${i * 40}ms` }}
            className="group flex w-full animate-slide-up items-center justify-between border-2 border-neutral-800 bg-neutral-950/90 px-4 py-3.5 text-left shadow-[4px_4px_0_0_#000] transition-all duration-150 hover:-translate-x-[2px] hover:-translate-y-[2px] hover:border-brand-600 hover:shadow-[6px_6px_0_0_#000]"
          >
            <span className="truncate font-mono text-sm text-neutral-300 transition group-hover:text-neutral-100">
              {c.url}
            </span>
            <Badge
              className="ml-3 shrink-0"
              tone={c.status === 'done' ? 'success' : c.status === 'error' ? 'danger' : 'neutral'}
              dot
              pulse={c.status !== 'done' && c.status !== 'error'}
            >
              {STATUS_LABEL[c.status] ?? c.status}
            </Badge>
          </button>
        ))}
        {checks?.length === 0 && (
          <p className="border-2 border-dashed border-neutral-800 p-6 text-center font-mono text-sm text-neutral-600">
            No checks yet — paste a link above.
          </p>
        )}
      </div>
    </div>
  )
}
