import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../api/client'
import type {
  FootageClip,
  FootageClipRequest,
  FootagePlanClip,
  FootageKeyword,
  FootageMoment,
  FootageProject,
  FootageSegment,
  FootageVideo,
} from '../api/types'
import { NavBar } from '../components/ui/NavBar'
import { PageHeader } from '../components/ui/PageHeader'
import { Button } from '../components/ui/Button'
import { Card } from '../components/ui/Card'
import { Badge } from '../components/ui/Badge'
import { SegmentSection } from '../components/footage/SegmentSection'
import type { SegmentHandlers } from '../components/footage/SegmentSection'
import { MomentPlayer } from '../components/footage/MomentPlayer'
import type { PlayerTarget } from '../components/footage/MomentPlayer'
import { clipKey, errorText, isRunning, keywordColor, youtubeAt } from '../components/footage/format'
import { DownloadsPanel } from '../components/footage/DownloadsPanel'
import { EditPlanSection } from '../components/footage/EditPlanSection'

const STRONG_MOMENT = 70

function segmentStats(segment: FootageSegment) {
  const done = segment.keywords.filter((k) => k.status === 'done').length
  const running = segment.keywords.some((k) => isRunning(k.status))
  const best = Math.max(0, ...segment.keywords.flatMap((k) => k.videos.flatMap((v) => v.moments.map((m) => m.score))))
  return { done, running, best, total: segment.keywords.length }
}

function BatchBar({
  project,
  selected,
  onRun,
  onClear,
  pending,
}: {
  project: FootageProject
  selected: number
  onRun: () => void
  onClear: () => void
  pending: boolean
}) {
  const allKeywords = project.segments.flatMap((s) => s.keywords)
  const active = allKeywords.filter((k) => k.status === 'searching' || k.status === 'analyzing')
  const queued = allKeywords.filter((k) => k.status === 'queued').length
  const running = project.batches.filter((b) => b.status === 'running')
  const total = running.reduce((n, b) => n + b.total, 0)
  const finished = running.reduce((n, b) => n + b.finished, 0)

  return (
    <div className="sticky top-0 z-30 -mx-4 mb-6 border-b-2 border-neutral-800 bg-[#060606]/95 px-4 py-3 backdrop-blur sm:mx-0 sm:border-2 sm:shadow-[4px_4px_0_0_#000]">
      <div className="flex flex-wrap items-center gap-3">
        <span className="font-display text-xl uppercase tracking-wide text-neutral-100">
          {selected} keyword{selected === 1 ? '' : 's'} selected
        </span>
        {selected > 0 && (
          <button
            onClick={onClear}
            className="font-mono text-[11px] uppercase tracking-widest text-neutral-500 hover:text-brand-400"
          >
            Clear
          </button>
        )}
        <Button variant="primary" className="ml-auto" disabled={selected === 0 || pending} onClick={onRun}>
          {pending ? 'Queuing…' : `▶ Fetch footage${selected ? ` (${selected})` : ''}`}
        </Button>
      </div>
      {total > 0 && (
        <div className="mt-3 space-y-1.5">
          <div className="flex items-center justify-between font-mono text-[11px] uppercase tracking-widest text-neutral-400">
            <span>
              Batch running · {finished}/{total} keywords done{queued ? ` · ${queued} waiting` : ''}
            </span>
            <span className="text-neutral-600">{project.keywords_per_wave} at a time</span>
          </div>
          <div className="h-1.5 bg-neutral-800">
            <div className="h-full bg-brand-500 transition-all" style={{ width: `${(finished / total) * 100}%` }} />
          </div>
          {active.length > 0 && (
            <div className="flex flex-wrap gap-x-4 gap-y-1 font-mono text-[11px] text-neutral-500">
              {active.map((k) => (
                <span key={k.id}>
                  <span className="text-neutral-300">“{k.text}”</span> — {k.progress}
                </span>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function toClipRequest(segmentPosition: number, video: FootageVideo, moment: FootageMoment): FootageClipRequest {
  return {
    video_id: video.video_id,
    video_title: video.title,
    segment_position: segmentPosition,
    label: moment.label,
    start: moment.start,
    end: moment.end,
  }
}

// A failed clip only knows its own times; its segment number is already
// baked into the filename, so read it back from there for the retry.
function clipRetryRequest(clip: FootageClip): FootageClipRequest {
  const match = clip.filename.match(/^S(\d+)_/)
  return {
    video_id: clip.video_id,
    video_title: clip.video_title,
    segment_position: match ? Number(match[1]) - 1 : 0,
    label: clip.label,
    start: clip.start_seconds,
    end: clip.end_seconds,
  }
}

export function FootageProjectPage() {
  const { projectId = '' } = useParams()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [player, setPlayer] = useState<PlayerTarget | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)
  const preselected = useRef(false)

  const { data: project, error, isLoading } = useQuery({
    queryKey: ['footage-project', projectId],
    queryFn: () => api.getFootageProject(projectId),
    refetchInterval: (q) => {
      const p = q.state.data
      if (!p) return false
      const busy =
        p.status === 'analyzing' ||
        p.segments.some((s) => s.keywords.some((k) => isRunning(k.status))) ||
        p.clips.some((c) => c.status === 'downloading') ||
        p.edit_plan?.status === 'building'
      return busy ? 2000 : false
    },
  })

  // A keyword-only project exists to be fetched -- start with all of its
  // keywords ticked. A script's suggestions are left for the user to pick.
  useEffect(() => {
    if (!project || preselected.current || project.status !== 'ready') return
    preselected.current = true
    if (project.mode === 'keywords') {
      setSelected(new Set(project.segments.flatMap((s) => s.keywords.filter((k) => k.status === 'idle').map((k) => k.id))))
    }
  }, [project])

  const setProject = (p: FootageProject) => queryClient.setQueryData(['footage-project', projectId], p)
  const onError = (e: unknown) => setActionError(errorText(e))

  const runBatch = useMutation({
    mutationFn: (ids: string[]) => api.runFootageBatch(projectId, ids),
    onSuccess: (p, ids) => {
      setProject(p)
      setSelected((prev) => new Set([...prev].filter((id) => !ids.includes(id))))
      setActionError(null)
    },
    onError,
  })
  const addKeyword = useMutation({
    mutationFn: ({ segmentId, text }: { segmentId: string; text: string }) =>
      api.addFootageKeyword(projectId, segmentId, text),
    onSuccess: (p) => {
      setProject(p)
      // Select the keyword just added -- typing one in means you want it.
      const fresh = p.segments.flatMap((s) => s.keywords).filter((k) => k.status === 'idle')
      const newest = fresh.find((k) => !project?.segments.some((s) => s.keywords.some((o) => o.id === k.id)))
      if (newest) setSelected((prev) => new Set(prev).add(newest.id))
    },
    onError,
  })
  const deleteKeyword = useMutation({
    mutationFn: (id: string) => api.deleteFootageKeyword(id),
    onSuccess: (p, id) => {
      setProject(p)
      setSelected((prev) => {
        const next = new Set(prev)
        next.delete(id)
        return next
      })
    },
    onError,
  })
  const downloadClips = useMutation({
    mutationFn: (clips: FootageClipRequest[]) => api.downloadFootageClips(projectId, clips),
    onSuccess: (p) => {
      setProject(p)
      setActionError(null)
    },
    onError,
  })
  const buildPlan = useMutation({
    mutationFn: () => api.buildFootageEditPlan(projectId),
    onSuccess: (p) => {
      setProject(p)
      setActionError(null)
    },
    onError,
  })
  const deleteClip = useMutation({
    mutationFn: (id: string) => api.deleteFootageClip(id),
    onSuccess: setProject,
    onError,
  })
  const deleteProject = useMutation({
    mutationFn: () => api.deleteFootageProject(projectId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['footage-projects'] })
      navigate('/footage')
    },
    onError,
  })

  const colors = useMemo(() => {
    const map = new Map<string, string>()
    project?.segments.flatMap((s) => s.keywords).forEach((k, i) => map.set(k.id, keywordColor(i)))
    return map
  }, [project])

  const clipsByKey = useMemo(
    () => new Map((project?.clips ?? []).map((c) => [clipKey(c.video_id, c.start_seconds, c.end_seconds), c])),
    [project],
  )

  const toggle = useCallback((id: string) => {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }, [])

  // A plan clip points at a video row and keyword; open the player with the
  // live objects so its timeline shows every moment of that video.
  function playPlanClip(p: FootageProject, segmentId: string, c: FootagePlanClip) {
    const segment = p.segments.find((s) => s.id === segmentId)
    const keyword = segment?.keywords.find((k) => k.id === c.keyword_id)
    const video = keyword?.videos.find((v) => v.id === c.video_row_id)
    if (!segment || !keyword || !video) {
      window.open(youtubeAt(c.video_id, c.start), '_blank', 'noreferrer')
      return
    }
    const moment = video.moments.find((m) => m.start === c.start && m.end === c.end) ?? null
    handlers.play(segment, keyword, video, moment)
  }

  const handlers: SegmentHandlers = {
    colorOf: (id) => colors.get(id) ?? '#a3a3a3',
    isSelected: (id) => selected.has(id),
    toggle,
    selectMany: (ids) => setSelected((prev) => new Set([...prev, ...ids])),
    play: (segment: FootageSegment, keyword: FootageKeyword, video: FootageVideo, moment: FootageMoment | null) =>
      setPlayer({
        video,
        moment,
        keywordText: keyword.text,
        keywordColor: colors.get(keyword.id) ?? '#a3a3a3',
        segmentTitle: segment.title,
        segmentPosition: segment.position,
      }),
    addKeyword: (segmentId, text) => addKeyword.mutate({ segmentId, text }),
    deleteKeyword: (id) => deleteKeyword.mutate(id),
    rerun: (id) => runBatch.mutate([id]),
    clipFor: (video, moment) => clipsByKey.get(clipKey(video.video_id, moment.start, moment.end)),
    download: (segment, items) =>
      downloadClips.mutate(items.map(({ video, moment }) => toClipRequest(segment.position, video, moment))),
  }

  if (isLoading) {
    return (
      <div className="mx-auto max-w-7xl px-4 py-12">
        <NavBar />
        <div className="h-40 animate-shimmer bg-[linear-gradient(90deg,#171717_25%,#262626_50%,#171717_75%)] bg-[length:200%_100%]" />
      </div>
    )
  }
  if (error || !project) {
    return (
      <div className="mx-auto max-w-7xl px-4 py-12">
        <NavBar />
        <PageHeader backTo="/footage" backLabel="All projects" title="Project not found" />
        <p className="font-mono text-sm text-brand-400">{error ? errorText(error) : ''}</p>
      </div>
    )
  }

  const keywords = project.segments.flatMap((s) => s.keywords)
  const videos = keywords.flatMap((k) => k.videos)
  const momentCount = videos.reduce((n, v) => n + v.moments.length, 0)
  const covered = project.segments.filter((s) => segmentStats(s).best >= STRONG_MOMENT).length
  const isScript = project.mode === 'script'
  const anyRunning = keywords.some((k) => isRunning(k.status))

  return (
    <div className="mx-auto max-w-7xl px-4 py-12">
      <NavBar />
      <PageHeader
        backTo="/footage"
        backLabel="All projects"
        title={project.title || 'Untitled project'}
        subtitle={
          project.status === 'ready'
            ? `${isScript ? `${project.segments.length} segments · ` : ''}${keywords.length} keywords · ${videos.length} videos · ${momentCount} moments found`
            : undefined
        }
        actions={
          <Button
            size="sm"
            variant="danger"
            disabled={anyRunning || deleteProject.isPending}
            onClick={() => window.confirm('Delete this project and all its results?') && deleteProject.mutate()}
          >
            Delete project
          </Button>
        }
      />

      {project.status === 'analyzing' && (
        <Card className="space-y-3 p-6">
          <Badge tone="info" dot pulse>Reading your script</Badge>
          <p className="font-display text-2xl uppercase text-neutral-100">
            Splitting it into segments and planning the footage for each…
          </p>
          <p className="font-mono text-xs text-neutral-500">Usually takes 5–30 seconds.</p>
        </Card>
      )}
      {project.status === 'error' && (
        <Card className="p-6">
          <Badge tone="danger">Couldn't read the script</Badge>
          <p className="mt-3 font-mono text-sm text-brand-400">{project.error_message}</p>
        </Card>
      )}

      {project.status === 'ready' && (
        <>
          <BatchBar
            project={project}
            selected={selected.size}
            pending={runBatch.isPending}
            onRun={() => runBatch.mutate([...selected])}
            onClear={() => setSelected(new Set())}
          />
          {actionError && <p className="-mt-3 mb-4 font-mono text-sm text-brand-400">{actionError}</p>}

          <div className={isScript ? 'grid gap-6 lg:grid-cols-[230px_1fr]' : ''}>
            {isScript && (
              <aside className="hidden lg:block">
                <nav className="sticky top-32 space-y-1">
                  <p className="mb-2 font-mono text-[11px] uppercase tracking-widest text-neutral-500">
                    Coverage · {covered}/{project.segments.length} segments
                  </p>
                  {project.segments.map((s, i) => {
                    const st = segmentStats(s)
                    const dot = st.running ? '#facc15' : st.best >= STRONG_MOMENT ? '#34d399' : st.best > 0 ? '#f59e0b' : '#404040'
                    return (
                      <button
                        key={s.id}
                        onClick={() => document.getElementById(`segment-${s.id}`)?.scrollIntoView({ behavior: 'smooth' })}
                        className="flex w-full items-start gap-2 border-l-2 border-neutral-800 px-2 py-1.5 text-left transition hover:border-brand-500 hover:bg-neutral-900"
                      >
                        <span
                          className={`mt-1 h-2 w-2 shrink-0 rounded-full ${st.running ? 'animate-pulse' : ''}`}
                          style={{ backgroundColor: dot }}
                        />
                        <span className="min-w-0">
                          <span className="block truncate text-sm text-neutral-200">
                            <span className="font-mono text-neutral-500">{String(i + 1).padStart(2, '0')}</span> {s.title}
                          </span>
                          <span className="font-mono text-[10px] text-neutral-500">
                            {st.done}/{st.total} fetched{st.best ? ` · best ${st.best}` : ''}
                          </span>
                        </span>
                      </button>
                    )
                  })}
                  <div className="mt-4 space-y-1 border-t border-neutral-800 pt-3 font-mono text-[10px] text-neutral-500">
                    <p><span className="mr-1.5 inline-block h-2 w-2 rounded-full bg-[#34d399]" />Has a strong match</p>
                    <p><span className="mr-1.5 inline-block h-2 w-2 rounded-full bg-[#f59e0b]" />Only partial matches</p>
                    <p><span className="mr-1.5 inline-block h-2 w-2 rounded-full bg-[#404040]" />Nothing fetched yet</p>
                  </div>
                  <button
                    onClick={() => document.getElementById('edit-plan')?.scrollIntoView({ behavior: 'smooth' })}
                    className="mt-4 w-full border-2 border-brand-600 px-2 py-1.5 text-left font-display text-lg uppercase tracking-wide text-brand-400 transition hover:bg-brand-950"
                  >
                    🎬 Edit plan →
                  </button>
                </nav>
              </aside>
            )}

            <div className="min-w-0 space-y-6">
              <DownloadsPanel
                projectId={project.id}
                clips={project.clips}
                onRetry={(c) => downloadClips.mutate([clipRetryRequest(c)])}
                onDelete={(c) => deleteClip.mutate(c.id)}
              />
              {project.segments.map((s, i) => (
                <SegmentSection key={s.id} segment={s} index={i} showHeader={isScript} h={handlers} />
              ))}
              {isScript && (
                <EditPlanSection
                  project={project}
                  colorOf={handlers.colorOf}
                  clipFor={(c) => clipsByKey.get(clipKey(c.video_id, c.start, c.end))}
                  building={buildPlan.isPending}
                  onBuild={() => buildPlan.mutate()}
                  onPlay={(segmentId, c) => playPlanClip(project, segmentId, c)}
                  onDownload={(position, clips) =>
                    downloadClips.mutate(
                      clips.map((c) => ({
                        video_id: c.video_id,
                        video_title: c.video_title,
                        segment_position: position,
                        label: c.label,
                        start: c.start,
                        end: c.end,
                      })),
                    )
                  }
                />
              )}
            </div>
          </div>
        </>
      )}

      {player && (
        <MomentPlayer
          target={player}
          onClose={() => setPlayer(null)}
          clipFor={handlers.clipFor}
          onDownload={(video, moment) =>
            downloadClips.mutate([toClipRequest(player.segmentPosition, video, moment)])
          }
        />
      )}
    </div>
  )
}
