export function Marquee({ text }: { text: string }) {
  return (
    <div className="hazard-stripes overflow-hidden border-y-2 border-black py-1.5">
      <div className="flex w-max animate-marquee whitespace-nowrap">
        {[0, 1].map((i) => (
          <span
            key={i}
            className="px-4 font-mono text-xs font-bold uppercase tracking-[0.2em] text-black"
          >
            {text}
          </span>
        ))}
      </div>
    </div>
  )
}
