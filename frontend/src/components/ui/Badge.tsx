import type { ReactNode } from 'react'

type Tone = 'neutral' | 'brand' | 'success' | 'danger' | 'warning' | 'info'

const TONE_CLASSES: Record<Tone, string> = {
  neutral: 'border-neutral-500 text-neutral-300',
  brand: 'border-brand-500 text-brand-400',
  success: 'border-emerald-500 text-emerald-400',
  danger: 'border-brand-500 text-brand-400',
  warning: 'border-orange-500 text-orange-400',
  info: 'border-yellow-500 text-yellow-400',
}

export function Badge({
  tone = 'neutral',
  dot,
  pulse,
  children,
  className = '',
}: {
  tone?: Tone
  dot?: boolean
  pulse?: boolean
  children: ReactNode
  className?: string
}) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 border-2 bg-black px-2.5 py-1 font-mono text-[11px] font-bold uppercase tracking-wider ${TONE_CLASSES[tone]} ${className}`}
    >
      {dot && <span className={`h-1.5 w-1.5 rounded-full bg-current ${pulse ? 'animate-pulse' : ''}`} />}
      {children}
    </span>
  )
}
