import { useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { apiUrl } from '../api/base'
import { api } from '../api/client'
import type { NewspaperContent } from '../api/types'
import { Button } from './ui/Button'

const TODAY = new Date().toLocaleDateString(undefined, {
  weekday: 'long',
  year: 'numeric',
  month: 'long',
  day: 'numeric',
})

function parseContent(raw: string | undefined): NewspaperContent | null {
  if (!raw) return null
  try {
    return JSON.parse(raw) as NewspaperContent
  } catch {
    return null
  }
}

function FullArticleModal({
  clipId,
  headline,
  onClose,
}: {
  clipId: string
  headline: string
  onClose: () => void
}) {
  const { data, isPending, isError } = useQuery({
    queryKey: ['full-article', clipId],
    queryFn: () => api.getFullArticle(clipId),
  })

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/70 p-4 sm:p-10"
      onClick={onClose}
    >
      <div
        className="relative w-full max-w-2xl rounded-sm bg-[#f4ecd8] p-6 shadow-2xl sm:p-10"
        onClick={(e) => e.stopPropagation()}
      >
        <button
          onClick={onClose}
          aria-label="Close"
          className="absolute right-4 top-4 font-serif text-2xl leading-none text-neutral-600 hover:text-black"
        >
          ✕
        </button>
        <img
          src={apiUrl(`/api/clips/${clipId}/thumbnail`)}
          alt={headline}
          className="mb-4 aspect-[16/9] w-full border border-black/20 object-cover grayscale"
        />
        <h2 className="mb-4 font-serif text-3xl font-bold leading-tight text-black">{headline}</h2>
        {isPending && <p className="font-serif italic text-neutral-600">Setting the type…</p>}
        {isError && <p className="font-serif italic text-red-700">Failed to load the full article.</p>}
        {data && (
          <div className="font-serif text-[15px] leading-relaxed text-neutral-900 [text-align:justify]">
            {data.article.split('\n').filter(Boolean).map((para, i) => (
              <p key={i} className="mb-3">
                {para}
              </p>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

function Article({
  clipId,
  headline,
  body,
  lead = false,
}: {
  clipId: string
  headline: string
  body: string
  lead?: boolean
}) {
  const [playing, setPlaying] = useState(false)
  const [showFull, setShowFull] = useState(false)

  return (
    <article className="mb-6 break-inside-avoid">
      {playing ? (
        <video
          controls
          autoPlay
          className={`mb-1 w-full bg-black object-cover ${lead ? 'aspect-[16/9]' : 'aspect-[4/3]'}`}
          src={apiUrl(`/api/clips/${clipId}/video`)}
        />
      ) : (
        <button onClick={() => setPlaying(true)} className="group relative mb-1 block w-full cursor-pointer">
          <img
            src={apiUrl(`/api/clips/${clipId}/thumbnail`)}
            alt={headline}
            className={`w-full border border-black/20 object-cover grayscale transition group-hover:grayscale-0 ${lead ? 'aspect-[16/9]' : 'aspect-[4/3]'}`}
          />
          <span className="absolute inset-0 flex items-center justify-center bg-black/0 transition group-hover:bg-black/30">
            <span className="flex h-11 w-11 items-center justify-center rounded-full bg-white/0 text-2xl text-white opacity-0 shadow transition group-hover:bg-black/50 group-hover:opacity-100">
              ▶
            </span>
          </span>
        </button>
      )}
      <p className="mb-1.5 font-serif text-[11px] italic text-neutral-600">
        {playing ? 'Now playing' : 'Click photo to play clip'}
      </p>
      <h3
        className={`font-serif font-bold leading-tight text-black ${lead ? 'text-3xl' : 'text-lg'}`}
      >
        {headline}
      </h3>
      <p
        className={`mt-1.5 font-serif text-[15px] leading-snug text-neutral-900 [text-align:justify] ${
          lead ? 'first-letter:float-left first-letter:mr-1 first-letter:text-6xl first-letter:font-bold first-letter:leading-[0.8]' : ''
        }`}
      >
        {body}
      </p>
      <button
        onClick={() => setShowFull(true)}
        className="mt-1.5 font-serif text-[13px] font-semibold uppercase tracking-wide text-neutral-800 underline decoration-dotted underline-offset-2 hover:text-black"
      >
        Read full article &rarr;
      </button>
      {showFull && (
        <FullArticleModal clipId={clipId} headline={headline} onClose={() => setShowFull(false)} />
      )}
    </article>
  )
}

export function NewspaperPanel({ sessionId }: { sessionId: string }) {
  const { data: newspaper } = useQuery({
    queryKey: ['newspaper', sessionId],
    queryFn: () => api.getNewspaper(sessionId),
    retry: false,
    throwOnError: false,
  })

  const generate = useMutation({
    mutationFn: () => api.generateNewspaper(sessionId),
  })

  const raw = generate.data?.content ?? newspaper?.content
  const paper = parseContent(raw)

  return (
    <div className="mb-4">
      <div className="mb-2 flex items-center justify-between gap-4">
        <h2 className="text-sm font-medium uppercase tracking-wide text-neutral-500">Newspaper</h2>
        <Button size="sm" onClick={() => generate.mutate()} disabled={generate.isPending}>
          {generate.isPending ? 'Typesetting…' : paper ? 'Regenerate' : 'Generate Newspaper'}
        </Button>
      </div>

      {generate.isError && (
        <p className="mb-2 text-xs text-red-400">Failed to generate: {(generate.error as Error).message}</p>
      )}

      {paper && (
        <div className="overflow-x-auto rounded-sm border border-black/10 bg-[#f4ecd8] p-6 shadow-lg sm:p-10">
          <div className="min-w-[640px]">
            <header className="text-center">
              <h1 className="font-serif text-5xl font-black uppercase tracking-tight text-black sm:text-6xl">
                {paper.masthead}
              </h1>
              <div className="mt-2 flex items-center justify-center gap-3 font-serif text-xs uppercase tracking-[0.2em] text-neutral-700">
                <span className="h-px flex-1 bg-black/40" />
                <span>{TODAY} &middot; Special Edition &middot; Price: Free</span>
                <span className="h-px flex-1 bg-black/40" />
              </div>
              <div className="mt-1.5 h-[3px] bg-black" />
              <div className="mt-0.5 h-px bg-black" />
            </header>

            {paper.sections.length === 0 ? (
              <p className="mt-8 text-center font-serif italic text-neutral-600">
                No stories to print in this edition yet.
              </p>
            ) : (
              paper.sections.map((section, si) => (
                <section key={section.name + si} className="mt-6">
                  {section.name && (
                    <h2 className="mb-3 border-b-2 border-black pb-1 font-serif text-sm font-bold uppercase tracking-[0.15em] text-black">
                      {section.name}
                    </h2>
                  )}
                  <div
                    className={
                      si === 0
                        ? 'columns-1 gap-8 [column-rule:1px_solid_rgba(0,0,0,0.25)] sm:columns-2 lg:columns-3'
                        : 'columns-1 gap-8 [column-rule:1px_solid_rgba(0,0,0,0.25)] sm:columns-2'
                    }
                  >
                    {section.articles.map((article, ai) => (
                      <Article
                        key={article.clip_id}
                        clipId={article.clip_id}
                        headline={article.headline}
                        body={article.body}
                        lead={si === 0 && ai === 0}
                      />
                    ))}
                  </div>
                </section>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  )
}
