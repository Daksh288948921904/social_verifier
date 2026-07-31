import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { api } from '../api/client'
import { NavBar } from '../components/ui/NavBar'
import { Button } from '../components/ui/Button'
import { Badge } from '../components/ui/Badge'
import { Card } from '../components/ui/Card'
import { Skeleton } from '../components/ui/Skeleton'

function parseUrls(raw: string): string[] {
  return raw
    .split(/\n+/)
    .map((line) => line.trim())
    .filter(Boolean)
}

export function BatchStartPage() {
  const [raw, setRaw] = useState('')
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const { data: batches, isLoading } = useQuery({ queryKey: ['batches'], queryFn: api.listBatches })

  const urls = parseUrls(raw)

  const createBatch = useMutation({
    mutationFn: (urls: string[]) => api.createBatch(urls),
    onSuccess: (batch) => {
      queryClient.invalidateQueries({ queryKey: ['batches'] })
      navigate(`/verify/batch/${batch.id}`)
    },
  })

  return (
    <div className="mx-auto max-w-2xl px-4 py-12">
      <NavBar />

      <div className="mb-8 animate-slide-up">
        <h1 className="mb-2 font-display text-5xl uppercase leading-[0.95] tracking-wide text-neutral-50 sm:text-6xl">
          Check <span className="bg-brand-500 px-2 text-black">many at once</span>
        </h1>
        <p className="mt-3 max-w-md font-mono text-sm text-neutral-500">
          Paste one link per line. They're queued and fact-checked one at a time — come back
          whenever and see how far it's gotten.
        </p>
      </div>

      <Card className="animate-slide-up p-2" style={{ animationDelay: '60ms' }}>
        <form
          className="flex flex-col gap-2"
          onSubmit={(e) => {
            e.preventDefault()
            if (urls.length > 0) createBatch.mutate(urls)
          }}
        >
          <textarea
            className="h-40 w-full resize-y border-2 border-transparent bg-black px-4 py-3 font-mono text-sm text-neutral-100 placeholder-neutral-600 outline-none transition focus:border-brand-600"
            placeholder={'https://www.instagram.com/reel/...\nhttps://www.youtube.com/shorts/...\ntiktok.com/...'}
            value={raw}
            onChange={(e) => setRaw(e.target.value)}
          />
          <div className="flex items-center justify-between px-1">
            <span className="font-mono text-xs text-neutral-600">
              {urls.length} link{urls.length === 1 ? '' : 's'}
            </span>
            <Button type="submit" variant="primary" disabled={createBatch.isPending || urls.length === 0}>
              {createBatch.isPending ? 'Starting…' : `Check ${urls.length || ''} link${urls.length === 1 ? '' : 's'}`}
            </Button>
          </div>
        </form>
      </Card>
      {createBatch.isError && (
        <p className="mt-2 pl-1 font-mono text-sm text-brand-400">{(createBatch.error as Error).message}</p>
      )}

      <h2 className="mb-3 mt-10 font-display text-lg uppercase tracking-widest text-neutral-500">
        Past batches
      </h2>
      <div className="space-y-2">
        {isLoading && [0, 1].map((i) => <Skeleton key={i} className="h-14 w-full" />)}

        {batches?.map((b, i) => {
          const done = b.checks.filter((c) => c.status === 'done' || c.status === 'error').length
          return (
            <button
              key={b.id}
              onClick={() => navigate(`/verify/batch/${b.id}`)}
              style={{ animationDelay: `${i * 40}ms` }}
              className="group flex w-full animate-slide-up items-center justify-between border-2 border-neutral-800 bg-neutral-950/90 px-4 py-3.5 text-left shadow-[4px_4px_0_0_#000] transition-all duration-150 hover:-translate-x-[2px] hover:-translate-y-[2px] hover:border-brand-600 hover:shadow-[6px_6px_0_0_#000]"
            >
              <span className="truncate font-mono text-sm text-neutral-300 transition group-hover:text-neutral-100">
                {b.checks.length} link{b.checks.length === 1 ? '' : 's'} — started {b.created_at}
              </span>
              <Badge
                className="ml-3 shrink-0"
                tone={b.status === 'done' ? 'success' : 'neutral'}
                dot
                pulse={b.status !== 'done'}
              >
                {b.status === 'done' ? 'Done' : `${done}/${b.checks.length}`}
              </Badge>
            </button>
          )
        })}
        {batches?.length === 0 && (
          <p className="border-2 border-dashed border-neutral-800 p-6 text-center font-mono text-sm text-neutral-600">
            No batches yet — paste some links above.
          </p>
        )}
      </div>
    </div>
  )
}
