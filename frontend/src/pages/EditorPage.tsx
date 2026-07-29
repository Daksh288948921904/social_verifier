import { useEffect, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useParams } from 'react-router-dom'
import { apiUrl } from '../api/base'
import { api } from '../api/client'
import type { TimelineItem } from '../api/types'
import { PageHeader } from '../components/ui/PageHeader'
import { Button } from '../components/ui/Button'
import { Card } from '../components/ui/Card'
import { Skeleton } from '../components/ui/Skeleton'

const VERDICT_DOT: Record<string, string> = {
  true: 'bg-emerald-500',
  false: 'bg-red-500',
  misleading: 'bg-orange-500',
  'partially true': 'bg-yellow-500',
  unverifiable: 'bg-neutral-500',
}

function formatDuration(seconds: number): string {
  const m = Math.floor(seconds / 60)
  const s = Math.round(seconds % 60)
  return `${m}:${String(s).padStart(2, '0')}`
}

function InstagramPushPanel({ checkId, exportId }: { checkId: string; exportId: string }) {
  const [copied, setCopied] = useState(false)

  const createKit = useMutation({
    mutationFn: () => api.createInstagramKit(checkId, exportId),
  })

  const { data: kit } = useQuery({
    queryKey: ['instagram-kit', checkId, exportId, createKit.data?.id],
    queryFn: () => api.getInstagramKit(checkId, exportId, createKit.data!.id),
    enabled: !!createKit.data,
    refetchInterval: (query) => (query.state.data?.status === 'generating' ? 1500 : false),
  })

  const thumbnailUrl =
    kit?.status === 'done'
      ? apiUrl(`/api/verify/${checkId}/editor/exports/${exportId}/instagram/${kit.id}/thumbnail`)
      : null

  return (
    <Card className="mb-6 p-4">
      <div className="mb-3 flex items-center justify-between gap-3">
        <h2 className="font-display text-lg uppercase tracking-widest text-neutral-300">
          📸 Instagram Push
        </h2>
        <Button
          size="sm"
          disabled={createKit.isPending || kit?.status === 'generating'}
          onClick={() => createKit.mutate()}
        >
          {kit?.status === 'generating'
            ? 'Preparing…'
            : kit?.status === 'done'
              ? 'Regenerate'
              : 'Prepare Post'}
        </Button>
      </div>

      <p className="mb-3 font-mono text-xs text-neutral-600">
        Note: this doesn't auto-publish to Instagram — it prepares a thumbnail, caption, and
        posting guidance for you to use when you upload the downloaded video yourself.
      </p>

      {createKit.isError && (
        <p className="font-mono text-sm text-brand-400">
          Failed to start: {(createKit.error as Error).message}
        </p>
      )}
      {kit?.status === 'error' && (
        <p className="font-mono text-sm text-brand-400">Failed: {kit.error_message}</p>
      )}

      {kit?.status === 'done' && (
        <div className="grid animate-slide-up gap-4 sm:grid-cols-[200px_1fr]">
          {thumbnailUrl && (
            <div>
              <img
                src={thumbnailUrl}
                alt="AI-generated Instagram thumbnail"
                className="mb-2 aspect-[2/3] w-full border-2 border-neutral-800 object-cover shadow-[4px_4px_0_0_#000]"
              />
              <a
                href={thumbnailUrl}
                download="thumbnail.png"
                className="inline-block w-full border-2 border-neutral-700 bg-neutral-900 px-2 py-1 text-center font-mono text-xs uppercase text-neutral-300 transition hover:border-brand-500"
              >
                ⬇ Download
              </a>
            </div>
          )}

          <div className="space-y-4">
            <div>
              <div className="mb-1 flex items-center justify-between">
                <span className="font-display text-sm uppercase tracking-widest text-neutral-500">
                  Caption
                </span>
                <button
                  onClick={() => {
                    navigator.clipboard.writeText(kit.caption ?? '')
                    setCopied(true)
                    setTimeout(() => setCopied(false), 1500)
                  }}
                  className="font-mono text-xs uppercase text-brand-400 hover:text-brand-300"
                >
                  {copied ? '✓ Copied' : 'Copy'}
                </button>
              </div>
              <p className="whitespace-pre-wrap border-2 border-neutral-800 bg-black p-3 text-sm text-neutral-300">
                {kit.caption}
              </p>
            </div>

            <div>
              <span className="mb-1 block font-display text-sm uppercase tracking-widest text-neutral-500">
                Best Time to Post
              </span>
              <p className="border-2 border-neutral-800 bg-black p-3 text-sm text-neutral-300">
                {kit.best_time}
              </p>
            </div>

            <div>
              <span className="mb-1 block font-display text-sm uppercase tracking-widest text-neutral-500">
                Audio Style
              </span>
              <p className="border-2 border-neutral-800 bg-black p-3 text-sm text-neutral-300">
                {kit.audio_style}
              </p>
            </div>
          </div>
        </div>
      )}
    </Card>
  )
}

function InsertDivider({ onClick, disabled }: { onClick: () => void; disabled: boolean }) {
  return (
    <div className="group relative h-3">
      <div className="absolute inset-x-0 top-1/2 h-px -translate-y-1/2 bg-neutral-800 transition group-hover:bg-brand-700" />
      <button
        onClick={onClick}
        disabled={disabled}
        title="Add your video here"
        className="absolute left-1/2 top-1/2 flex h-5 w-5 -translate-x-1/2 -translate-y-1/2 items-center justify-center border-2 border-neutral-700 bg-black font-mono text-xs text-neutral-500 opacity-60 transition-all duration-150 hover:scale-110 hover:border-brand-500 hover:text-brand-300 group-hover:opacity-100 disabled:opacity-30"
      >
        +
      </button>
    </div>
  )
}

export function EditorPage() {
  const { checkId } = useParams<{ checkId: string }>()
  const queryClient = useQueryClient()
  if (!checkId) return null

  const { data: check } = useQuery({
    queryKey: ['reel-check', checkId],
    queryFn: () => api.getReelCheck(checkId),
  })
  const { data: timeline } = useQuery({
    queryKey: ['timeline', checkId],
    queryFn: () => api.getTimeline(checkId),
  })
  const { data: uploads } = useQuery({
    queryKey: ['uploads', checkId],
    queryFn: () => api.listUploads(checkId),
  })

  const [items, setItems] = useState<TimelineItem[]>([])
  useEffect(() => {
    if (timeline) setItems(timeline.items)
  }, [timeline])

  const saveTimeline = useMutation({
    mutationFn: (next: TimelineItem[]) => api.setTimeline(checkId, next),
  })

  function updateItems(next: TimelineItem[]) {
    setItems(next)
    saveTimeline.mutate(next)
  }

  const fileInputRef = useRef<HTMLInputElement>(null)
  const [insertAt, setInsertAt] = useState<number | null>(null)

  const upload = useMutation({
    mutationFn: (file: File) => api.uploadEditorVideo(checkId, file),
    onSuccess: (u) => {
      queryClient.invalidateQueries({ queryKey: ['uploads', checkId] })
      const at = insertAt ?? items.length
      const next = [...items]
      next.splice(at, 0, { type: 'upload', claim_index: null, upload_id: u.id })
      updateItems(next)
      setInsertAt(null)
    },
  })

  function triggerAddAt(index: number) {
    setInsertAt(index)
    fileInputRef.current?.click()
  }

  const [dragIndex, setDragIndex] = useState<number | null>(null)
  const [dragOverIndex, setDragOverIndex] = useState<number | null>(null)

  function handleDrop(targetIndex: number) {
    setDragOverIndex(null)
    if (dragIndex === null || dragIndex === targetIndex) return
    const next = [...items]
    const [moved] = next.splice(dragIndex, 1)
    next.splice(targetIndex, 0, moved)
    updateItems(next)
    setDragIndex(null)
  }

  function removeItem(index: number) {
    updateItems(items.filter((_, i) => i !== index))
  }

  const compile = useMutation({
    mutationFn: () => api.compileTimeline(checkId),
  })

  const { data: exportStatus } = useQuery({
    queryKey: ['export', checkId, compile.data?.id],
    queryFn: () => api.getExport(checkId, compile.data!.id),
    enabled: !!compile.data,
    refetchInterval: (query) => (query.state.data?.status === 'compiling' ? 1500 : false),
  })

  const uploadsById = new Map((uploads ?? []).map((u) => [u.id, u]))

  return (
    <div className="mx-auto max-w-3xl px-4 py-8">
      <PageHeader backTo={`/verify/${checkId}`} backLabel="Back to fact-check" title="🎬 Editor" subtitle={check?.url} />

      <p className="mb-4 animate-slide-up font-mono text-sm text-neutral-500">
        Drag to reorder. This reel's fact-checked claim clips start the timeline — remove any you
        don't want, and splice in your own video wherever you like.
      </p>

      <input
        ref={fileInputRef}
        type="file"
        accept="video/*"
        className="hidden"
        onChange={(e) => {
          const file = e.target.files?.[0]
          if (file) upload.mutate(file)
          e.target.value = ''
        }}
      />

      {!timeline && (
        <div className="mb-4 space-y-2">
          <Skeleton className="h-14 w-full" />
          <Skeleton className="h-14 w-full" />
          <Skeleton className="h-14 w-full" />
        </div>
      )}

      <div className="mb-4 animate-fade-in">
        {items.length > 0 && <InsertDivider onClick={() => triggerAddAt(0)} disabled={upload.isPending} />}
        {items.map((item, i) => {
          const isUpload = item.type === 'upload'
          const claim = !isUpload && check ? check.claims[item.claim_index!] : undefined
          const uploadInfo = isUpload ? uploadsById.get(item.upload_id!) : undefined
          const isDragging = dragIndex === i
          const isDragOver = dragOverIndex === i && dragIndex !== null && dragIndex !== i

          return (
            <div key={i}>
              <Card
                draggable
                onDragStart={() => setDragIndex(i)}
                onDragOver={(e) => {
                  e.preventDefault()
                  setDragOverIndex(i)
                }}
                onDragLeave={() => setDragOverIndex((cur) => (cur === i ? null : cur))}
                onDragEnd={() => {
                  setDragIndex(null)
                  setDragOverIndex(null)
                }}
                onDrop={() => handleDrop(i)}
                className={`flex cursor-move items-center gap-3 px-3 py-2.5 transition-all duration-150 ${
                  isDragging ? 'scale-[0.98] opacity-40' : ''
                } ${isDragOver ? 'border-brand-600 ring-1 ring-brand-600/50' : ''}`}
              >
                <span className="shrink-0 text-neutral-600">☰</span>
                <span className="shrink-0 border border-neutral-700 bg-neutral-900 px-1.5 py-0.5 font-mono text-xs font-semibold text-neutral-500">
                  #{i + 1}
                </span>

                {claim ? (
                  <>
                    <span className={`h-2 w-2 shrink-0 rounded-full ${VERDICT_DOT[claim.verdict] ?? 'bg-neutral-500'}`} />
                    <span className="min-w-0 flex-1 truncate text-sm text-neutral-300">{claim.claim}</span>
                  </>
                ) : (
                  <>
                    <span className="shrink-0 text-neutral-500">📁</span>
                    <span className="min-w-0 flex-1 truncate text-sm text-neutral-300">
                      {uploadInfo?.filename ?? 'Your video'}
                    </span>
                    {uploadInfo && (
                      <span className="shrink-0 font-mono text-xs text-neutral-600">
                        {formatDuration(uploadInfo.duration_seconds)}
                      </span>
                    )}
                  </>
                )}

                <button
                  onClick={() => removeItem(i)}
                  className="shrink-0 border border-transparent px-2 py-0.5 font-mono text-xs uppercase text-brand-400 transition hover:border-brand-600"
                >
                  Remove
                </button>
              </Card>
              <InsertDivider onClick={() => triggerAddAt(i + 1)} disabled={upload.isPending} />
            </div>
          )
        })}

        {timeline && items.length === 0 && (
          <p className="border-2 border-dashed border-neutral-800 p-6 text-center font-mono text-sm text-neutral-600">
            Nothing in the timeline yet.
          </p>
        )}
      </div>

      {upload.isPending && <p className="mb-4 font-mono text-xs text-neutral-500">Uploading…</p>}
      {upload.isError && (
        <p className="mb-4 font-mono text-xs text-brand-400">Upload failed: {(upload.error as Error).message}</p>
      )}

      <Card className="mb-6 p-4">
        <Button
          variant="primary"
          disabled={compile.isPending || items.length === 0 || exportStatus?.status === 'compiling'}
          onClick={() => compile.mutate()}
        >
          {exportStatus?.status === 'compiling' ? 'Compiling…' : 'Compile Video'}
        </Button>

        {compile.isError && (
          <p className="mt-3 font-mono text-sm text-brand-400">Failed to start compile: {(compile.error as Error).message}</p>
        )}
        {exportStatus?.status === 'error' && (
          <p className="mt-3 font-mono text-sm text-brand-400">Compile failed: {exportStatus.error_message}</p>
        )}
        {exportStatus?.status === 'done' && (
          <a
            href={apiUrl(`/api/verify/${checkId}/editor/exports/${exportStatus.id}/video`)}
            download
            className="mt-3 inline-block animate-slide-up border-2 border-emerald-500 bg-black px-3 py-1.5 font-mono text-sm text-emerald-400 shadow-[3px_3px_0_0_#000] transition hover:bg-emerald-950"
          >
            ⬇ Download compiled video
          </a>
        )}
      </Card>

      {exportStatus?.status === 'done' && <InstagramPushPanel checkId={checkId} exportId={exportStatus.id} />}
    </div>
  )
}
