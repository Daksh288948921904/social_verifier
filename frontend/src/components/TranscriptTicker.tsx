import { useEffect, useRef } from 'react'

function formatTs(seconds: number): string {
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  const s = Math.floor(seconds % 60)
  return [h, m, s].map((n) => String(n).padStart(2, '0')).join(':')
}

export function TranscriptTicker({ ticks }: { ticks: { text: string; start: number }[] }) {
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [ticks])

  return (
    <div className="overflow-hidden border-2 border-neutral-800 bg-black shadow-[4px_4px_0_0_#000]">
      <div className="hazard-stripes flex items-center gap-2 border-b-2 border-black px-3 py-1.5">
        <span className="relative flex h-2 w-2">
          <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-black opacity-75" />
          <span className="relative inline-flex h-2 w-2 rounded-full bg-black" />
        </span>
        <span className="font-display text-sm uppercase tracking-widest text-black">Live Transcript</span>
      </div>
      <div className="h-40 overflow-y-auto p-3 font-mono text-sm text-neutral-500">
        {ticks.length === 0 && <p className="text-neutral-600">Waiting for transcript…</p>}
        {ticks.map((t) => (
          <p key={t.start} className="mb-1 animate-slide-up">
            <span className="text-brand-500">[{formatTs(t.start)}]</span> {t.text}
          </p>
        ))}
        <div ref={bottomRef} />
      </div>
    </div>
  )
}
