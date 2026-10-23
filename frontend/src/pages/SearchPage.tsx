import { useState } from 'react'
import type { FormEvent } from 'react'
import { useMutation } from '@tanstack/react-query'
import { api } from '../api/client'
import { NavBar } from '../components/ui/NavBar'
import { Button } from '../components/ui/Button'
import { Card } from '../components/ui/Card'
import { SearchResultCard } from '../components/SearchResultCard'

export function SearchPage() {
  const [query, setQuery] = useState('')
  const search = useMutation({ mutationFn: (q: string) => api.search(q) })

  function handleSubmit(e: FormEvent) {
    e.preventDefault()
    if (query.trim()) search.mutate(query.trim())
  }

  return (
    <div className="mx-auto max-w-6xl px-4 py-12">
      <NavBar />

      <div className="mb-8 animate-slide-up">
        <h1 className="mb-2 font-display text-5xl uppercase leading-[0.95] tracking-wide text-neutral-50 sm:text-6xl">
          Find the clip <span className="bg-brand-500 px-2 text-black">before anyone else</span>
        </h1>
        <p className="mt-3 max-w-md font-mono text-sm text-neutral-500">
          Search YouTube, the web, and Instagram Reels for a keyword and pull down matching
          clips.
        </p>
      </div>

      <Card className="animate-slide-up p-2" style={{ animationDelay: '60ms' }}>
        <form className="flex flex-col gap-2 sm:flex-row" onSubmit={handleSubmit}>
          <input
            className="flex-1 border-2 border-transparent bg-black px-4 py-3 font-mono text-sm text-neutral-100 placeholder-neutral-600 outline-none transition focus:border-brand-600"
            placeholder="Search a keyword…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            autoFocus
          />
          <Button type="submit" variant="primary" disabled={search.isPending || !query.trim()}>
            {search.isPending ? 'Searching…' : 'Search'}
          </Button>
        </form>
      </Card>

      {search.isError && (
        <p className="mt-2 pl-1 font-mono text-sm text-brand-400">
          {(search.error as Error).message}
        </p>
      )}

      {search.data && (
        <>
          {Object.keys(search.data.errors).length > 0 && (
            <div className="mt-4 space-y-1">
              {Object.entries(search.data.errors).map(([source, message]) => (
                <p key={source} className="font-mono text-xs text-brand-400">
                  {source}: {message}
                </p>
              ))}
            </div>
          )}

          {search.data.results.length === 0 ? (
            <p className="mt-6 border-2 border-dashed border-neutral-800 p-6 text-center font-mono text-sm text-neutral-600">
              No results found.
            </p>
          ) : (
            <div className="mt-6 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {search.data.results.map((r) => (
                <SearchResultCard key={r.id} result={r} />
              ))}
            </div>
          )}
        </>
      )}
    </div>
  )
}
