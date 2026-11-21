import type { HTMLAttributes } from 'react'

type Tone = 'neutral' | 'demo' | 'fact' | 'opinion' | 'inference' | 'high' | 'medium' | 'low'

export function Badge({ tone = 'neutral', className = '', ...props }: HTMLAttributes<HTMLSpanElement> & { tone?: Tone }) {
  return <span className={`badge badge--${tone} ${className}`} {...props} />
}
