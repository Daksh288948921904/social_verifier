import { useClips } from '../hooks/useClips'
import { ClipCard } from './ClipCard'
import { Skeleton } from './ui/Skeleton'

export function ClipsGallery({ sessionId }: { sessionId: string }) {
  const { data: clips, isLoading } = useClips(sessionId)

  if (isLoading) {
    return (
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {[0, 1, 2].map((i) => (
          <Skeleton key={i} className="aspect-video w-full rounded-none" />
        ))}
      </div>
    )
  }
  if (!clips || clips.length === 0) {
    return (
      <p className="border-2 border-dashed border-neutral-800 p-8 text-center font-mono text-sm text-neutral-600">
        No clips yet — they'll appear here as stories finish.
      </p>
    )
  }

  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {clips.map((clip, i) => (
        <div key={clip.id} style={{ animationDelay: `${i * 30}ms` }}>
          <ClipCard clip={clip} />
        </div>
      ))}
    </div>
  )
}
