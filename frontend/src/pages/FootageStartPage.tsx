import { useRef, useState } from 'react'
import type { ClipboardEvent, DragEvent, FormEvent, KeyboardEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useMutation, useQuery } from '@tanstack/react-query'
import { api } from '../api/client'
import type { FootageProjectSummary } from '../api/types'
import { NavBar } from '../components/ui/NavBar'
import { Button } from '../components/ui/Button'
import { Card } from '../components/ui/Card'
import { Badge } from '../components/ui/Badge'
import { errorText, keywordColor } from '../components/footage/format'

type Mode = 'script' | 'keywords'

function splitKeywords(text: string): string[] {
  return text.split(/[\n,;]+/).map((k) => k.trim()).filter(Boolean)
}

function ProjectRow({ p }: { p: FootageProjectSummary }) {
  const status =
    p.status === 'analyzing' ? <Badge tone="info" dot pulse>Reading script</Badge>
    : p.status === 'error' ? <Badge tone="danger">Failed</Badge>
    : p.keyword_count && p.done_keyword_count === p.keyword_count ? <Badge tone="success">All fetched</Badge>
    : null
  return (
    <Link to={`/footage/${p.id}`}>
      <Card hover className="flex flex-wrap items-center gap-x-4 gap-y-2 p-4">
        <div className="min-w-0 flex-1">
          <p className="font-mono text-[11px] uppercase tracking-widest text-brand-500">
            {p.mode === 'script' ? 'Script' : 'Keywords'} · {p.created_at.slice(0, 16)}
          </p>
          <p className="truncate font-display text-2xl uppercase tracking-wide text-neutral-100">
            {p.title || 'Untitled project'}
          </p>
        </div>
        <p className="font-mono text-xs text-neutral-400">
          {p.mode === 'script' && `${p.segment_count} segments · `}
          {p.done_keyword_count}/{p.keyword_count} keywords fetched · {p.video_count} videos
        </p>
        {status}
      </Card>
    </Link>
  )
}

export function FootageStartPage() {
  const navigate = useNavigate()
  const [mode, setMode] = useState<Mode>('script')
  const [title, setTitle] = useState('')
  const [script, setScript] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const [dragging, setDragging] = useState(false)
  const [keywords, setKeywords] = useState<string[]>([])
  const [draft, setDraft] = useState('')
  const fileInput = useRef<HTMLInputElement>(null)

  const projects = useQuery({
    queryKey: ['footage-projects'],
    queryFn: api.listFootageProjects,
    refetchInterval: (q) => (q.state.data?.some((p) => p.status === 'analyzing') ? 3000 : false),
  })

  const create = useMutation({
    mutationFn: async () => {
      if (mode === 'keywords') {
        return api.createFootageProject({ mode, title, keywords: [...keywords, ...splitKeywords(draft)] })
      }
      if (file) return api.createFootageProjectFromFile(file, title)
      return api.createFootageProject({ mode, title, script })
    },
    onSuccess: (p) => navigate(`/footage/${p.id}`),
  })

  function addDraft() {
    const fresh = splitKeywords(draft).filter((k) => !keywords.includes(k))
    if (fresh.length) setKeywords([...keywords, ...fresh])
    setDraft('')
  }

  function onKeywordKey(e: KeyboardEvent<HTMLInputElement>) {
    if (e.key === 'Enter' || e.key === ',') {
      e.preventDefault()
      addDraft()
    } else if (e.key === 'Backspace' && !draft && keywords.length) {
      setKeywords(keywords.slice(0, -1))
    }
  }

  // Pasting a list (one per line or comma-separated) adds them all at once.
  function onKeywordPaste(e: ClipboardEvent<HTMLInputElement>) {
    const text = e.clipboardData.getData('text')
    if (/[\n,;]/.test(text)) {
      e.preventDefault()
      const fresh = splitKeywords(text).filter((k) => !keywords.includes(k))
      setKeywords([...keywords, ...fresh])
    }
  }

  function onDrop(e: DragEvent) {
    e.preventDefault()
    setDragging(false)
    const dropped = e.dataTransfer.files[0]
    if (dropped) setFile(dropped)
  }

  function submit(e: FormEvent) {
    e.preventDefault()
    create.mutate()
  }

  const canSubmit =
    mode === 'keywords' ? keywords.length > 0 || draft.trim().length > 0 : !!file || script.trim().length >= 40

  return (
    <div className="mx-auto max-w-5xl px-4 py-12">
      <NavBar />

      <div className="mb-8 animate-slide-up">
        <h1 className="mb-2 font-display text-5xl uppercase leading-[0.95] tracking-wide text-neutral-50 sm:text-6xl">
          Footage for <span className="bg-brand-500 px-2 text-black">every segment</span>
        </h1>
        <p className="mt-3 max-w-xl font-mono text-sm text-neutral-500">
          Drop in a script and it's split into segments with search keywords for each. Pick the keywords,
          fetch them in batches, and see exactly which part of which YouTube video fits each segment.
        </p>
      </div>

      <Card className="animate-slide-up p-4 sm:p-5" style={{ animationDelay: '60ms' }}>
        <div className="mb-4 inline-flex border-2 border-neutral-700 font-display text-lg uppercase tracking-wide">
          {(['script', 'keywords'] as Mode[]).map((m, i) => (
            <button
              key={m}
              type="button"
              onClick={() => setMode(m)}
              className={`px-4 py-1.5 transition ${i ? 'border-l-2 border-neutral-700' : ''} ${
                mode === m ? 'bg-brand-500 text-black' : 'text-neutral-400 hover:text-neutral-100'
              }`}
            >
              {m === 'script' ? 'From a script' : 'From keywords'}
            </button>
          ))}
        </div>

        <form onSubmit={submit} className="space-y-3">
          <input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder={mode === 'script' ? 'Project title (optional — taken from the script otherwise)' : 'Project title (optional)'}
            className="w-full border-2 border-neutral-800 bg-black px-4 py-2.5 font-mono text-sm text-neutral-100 placeholder-neutral-600 outline-none transition focus:border-brand-600"
          />

          {mode === 'script' ? (
            <>
              <div
                onDragOver={(e) => {
                  e.preventDefault()
                  setDragging(true)
                }}
                onDragLeave={() => setDragging(false)}
                onDrop={onDrop}
                onClick={() => fileInput.current?.click()}
                className={`flex cursor-pointer flex-col items-center justify-center gap-1 border-2 border-dashed px-4 py-5 text-center transition ${
                  dragging ? 'border-brand-500 bg-brand-950/30' : 'border-neutral-700 hover:border-neutral-500'
                }`}
              >
                <input
                  ref={fileInput}
                  type="file"
                  accept=".pdf,.txt,.md,application/pdf,text/plain"
                  className="hidden"
                  onChange={(e) => setFile(e.target.files?.[0] ?? null)}
                />
                {file ? (
                  <>
                    <p className="font-display text-xl uppercase text-neutral-100">📄 {file.name}</p>
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation()
                        setFile(null)
                        if (fileInput.current) fileInput.current.value = ''
                      }}
                      className="font-mono text-[11px] uppercase tracking-widest text-neutral-500 hover:text-brand-400"
                    >
                      Remove file
                    </button>
                  </>
                ) : (
                  <>
                    <p className="font-display text-xl uppercase text-neutral-300">Drop a script PDF or TXT here</p>
                    <p className="font-mono text-xs text-neutral-600">or click to browse — or paste the text below</p>
                  </>
                )}
              </div>
              {!file && (
                <textarea
                  value={script}
                  onChange={(e) => setScript(e.target.value)}
                  rows={12}
                  placeholder={'Paste your script here.\n\nSegment markers like "SEGMENT 2 —" are followed exactly; without them it\'s split at natural topic changes.'}
                  className="w-full resize-y border-2 border-neutral-800 bg-black px-4 py-3 font-mono text-sm leading-relaxed text-neutral-100 placeholder-neutral-600 outline-none transition focus:border-brand-600"
                />
              )}
            </>
          ) : (
            <div className="flex min-h-28 flex-wrap content-start items-center gap-2 border-2 border-neutral-800 bg-black p-3 focus-within:border-brand-600">
              {keywords.map((k, i) => (
                <span
                  key={k}
                  className="inline-flex items-center gap-1.5 border-2 px-2.5 py-1 font-mono text-xs font-bold"
                  style={{ borderColor: keywordColor(i), color: keywordColor(i) }}
                >
                  {k}
                  <button
                    type="button"
                    aria-label={`Remove ${k}`}
                    onClick={() => setKeywords(keywords.filter((x) => x !== k))}
                    className="opacity-50 hover:opacity-100"
                  >
                    ✕
                  </button>
                </span>
              ))}
              <input
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                onKeyDown={onKeywordKey}
                onPaste={onKeywordPaste}
                onBlur={addDraft}
                autoFocus
                placeholder={keywords.length ? 'Add another…' : 'Type a keyword and press Enter — or paste a list'}
                className="min-w-48 flex-1 bg-transparent font-mono text-sm text-neutral-100 placeholder-neutral-600 outline-none"
              />
            </div>
          )}

          <div className="flex flex-wrap items-center gap-3">
            <Button type="submit" variant="primary" disabled={!canSubmit || create.isPending}>
              {create.isPending ? 'Creating…' : mode === 'script' ? 'Split into segments →' : 'Create project →'}
            </Button>
            {mode === 'script' && !file && script.trim().length > 0 && script.trim().length < 40 && (
              <span className="font-mono text-xs text-neutral-500">Paste the full script</span>
            )}
          </div>
          {create.isError && <p className="font-mono text-sm text-brand-400">{errorText(create.error)}</p>}
        </form>
      </Card>

      <div className="mt-10">
        <h2 className="mb-3 font-display text-3xl uppercase tracking-wide text-neutral-100">Your projects</h2>
        {projects.isLoading ? (
          <div className="h-20 animate-shimmer bg-[linear-gradient(90deg,#171717_25%,#262626_50%,#171717_75%)] bg-[length:200%_100%]" />
        ) : projects.data?.length ? (
          <div className="space-y-3">
            {projects.data.map((p) => <ProjectRow key={p.id} p={p} />)}
          </div>
        ) : (
          <p className="border-2 border-dashed border-neutral-800 p-6 text-center font-mono text-sm text-neutral-600">
            No projects yet — every script or keyword set you run is saved here.
          </p>
        )}
      </div>
    </div>
  )
}
