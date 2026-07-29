import type { ButtonHTMLAttributes } from 'react'

type Variant = 'primary' | 'secondary' | 'ghost' | 'danger'
type Size = 'sm' | 'md'

const VARIANT_CLASSES: Record<Variant, string> = {
  primary: 'border-2 border-black bg-brand-500 text-white shadow-[4px_4px_0_0_#000] hover:bg-brand-400',
  secondary:
    'border-2 border-neutral-700 bg-neutral-900 text-neutral-100 shadow-[4px_4px_0_0_#000] hover:border-neutral-500',
  ghost: 'text-neutral-400 hover:text-brand-400',
  danger: 'border-2 border-brand-500 bg-black text-brand-400 shadow-[4px_4px_0_0_#000] hover:bg-brand-950',
}

const SIZE_CLASSES: Record<Size, string> = {
  sm: 'px-3 py-1.5 text-xs',
  md: 'px-5 py-2.5 text-sm',
}

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant
  size?: Size
}

export function Button({ variant = 'secondary', size = 'md', className = '', ...props }: ButtonProps) {
  const hasShadow = variant !== 'ghost'
  return (
    <button
      className={`inline-flex items-center justify-center gap-2 font-display text-base uppercase tracking-wider transition-all duration-100 disabled:cursor-not-allowed disabled:opacity-40 ${
        hasShadow ? 'active:translate-x-[4px] active:translate-y-[4px] active:shadow-none disabled:active:translate-x-0 disabled:active:translate-y-0' : ''
      } ${VARIANT_CLASSES[variant]} ${SIZE_CLASSES[size]} ${className}`}
      {...props}
    />
  )
}
