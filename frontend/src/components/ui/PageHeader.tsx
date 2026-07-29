import type { ReactNode } from 'react'
import { useNavigate } from 'react-router-dom'

export function PageHeader({
  backTo,
  backLabel = 'Back',
  title,
  subtitle,
  actions,
}: {
  backTo: string
  backLabel?: string
  title: ReactNode
  subtitle?: ReactNode
  actions?: ReactNode
}) {
  const navigate = useNavigate()
  return (
    <div className="mb-6 animate-fade-in">
      <div className="mb-3 flex items-center justify-between gap-3">
        <button
          onClick={() => navigate(backTo)}
          className="group inline-flex items-center gap-1.5 font-mono text-xs uppercase tracking-widest text-neutral-500 transition hover:text-brand-400"
        >
          <span className="transition-transform duration-150 group-hover:-translate-x-0.5">←</span>
          {backLabel}
        </button>
        {actions}
      </div>
      <h1 className="truncate font-display text-3xl uppercase tracking-wide text-neutral-50 sm:text-4xl">
        {title}
      </h1>
      {subtitle && <p className="mt-1 truncate font-mono text-xs text-neutral-500">{subtitle}</p>}
    </div>
  )
}
