export function SegmentInProgressBanner({
  segment,
}: {
  segment: { title: string; start: number; end: number } | null
}) {
  if (!segment) return null
  return (
    <div className="flex animate-slide-up items-center gap-3 border-2 border-orange-500 bg-black px-4 py-3 font-mono text-sm text-orange-300 shadow-[4px_4px_0_0_#000]">
      <span className="relative flex h-2 w-2 shrink-0">
        <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-orange-400 opacity-75" />
        <span className="relative inline-flex h-2 w-2 rounded-full bg-orange-400" />
      </span>
      <span className="uppercase tracking-wide">Cutting clip:</span>{' '}
      <span className="font-bold text-orange-100">{segment.title}</span>
    </div>
  )
}
