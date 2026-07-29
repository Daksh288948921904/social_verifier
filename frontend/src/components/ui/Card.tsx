import type { HTMLAttributes } from 'react'

export function Card({
  hover,
  className = '',
  children,
  ...rest
}: HTMLAttributes<HTMLDivElement> & { hover?: boolean }) {
  return (
    <div
      className={`border-2 border-neutral-800 bg-neutral-950/90 shadow-[4px_4px_0_0_#000] ${
        hover
          ? 'transition-all duration-150 hover:-translate-x-[2px] hover:-translate-y-[2px] hover:border-brand-600 hover:shadow-[6px_6px_0_0_#000]'
          : ''
      } ${className}`}
      {...rest}
    >
      {children}
    </div>
  )
}
