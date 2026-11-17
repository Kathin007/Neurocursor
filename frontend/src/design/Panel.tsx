import type { ReactNode } from 'react'
import { cn } from '@/lib/utils'
import type { DataSource } from '@/lib/telemetry'
import { SourceBadge } from './SourceBadge'

interface PanelProps {
  title?: string
  source?: DataSource
  active?: boolean
  actions?: ReactNode
  className?: string
  children: ReactNode
}

/** Glass panel. `active` adds the restrained glow reserved for live elements. */
export function Panel({ title, source, active, actions, className, children }: PanelProps) {
  return (
    <section aria-label={title} className={cn('glass p-4', active && 'glow-active', className)}>
      {(title || source || actions) && (
        <header className="mb-3 flex items-center justify-between gap-3">
          <h2 className="label-caps">{title}</h2>
          <div className="flex items-center gap-2">
            {actions}
            {source && <SourceBadge source={source} />}
          </div>
        </header>
      )}
      {children}
    </section>
  )
}

export function Readout({ label, value, unit, tone }: { label: string; value: ReactNode; unit?: string; tone?: 'ok' | 'warn' | 'bad' }) {
  const color = tone === 'ok' ? 'text-success' : tone === 'warn' ? 'text-warning' : tone === 'bad' ? 'text-error' : 'text-text'
  return (
    <div>
      <div className="label-caps">{label}</div>
      <div className={cn('font-mono text-xl tabular-nums', color)}>
        {value}
        {unit && <span className="ml-1 text-xs text-text2">{unit}</span>}
      </div>
    </div>
  )
}

export function Meter({ value, label, tone }: { value: number; label: string; tone?: 'ok' | 'warn' | 'bad' }) {
  const pct = Math.round(Math.min(1, Math.max(0, value)) * 100)
  const fill = tone === 'bad' ? 'bg-error' : tone === 'warn' ? 'bg-warning' : 'bg-cyan'
  return (
    <div role="meter" aria-label={label} aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100} className="h-1.5 w-full rounded-full bg-white/8">
      <div className={cn('h-full rounded-full', fill)} style={{ width: `${pct}%` }} />
    </div>
  )
}

export function EmptyState({ title, hint }: { title: string; hint: string }) {
  return (
    <div className="glass flex flex-col items-center gap-2 px-6 py-14 text-center">
      <div aria-hidden className="mb-1 size-10 rounded-full border border-dashed border-lavender/50" />
      <p className="text-base font-medium">{title}</p>
      <p className="max-w-md text-sm text-text2">{hint}</p>
    </div>
  )
}

export function StatusDot({ state }: { state: 'ok' | 'warn' | 'bad' | 'idle' }) {
  const c = { ok: 'bg-success', warn: 'bg-warning', bad: 'bg-error', idle: 'bg-text2/50' }[state]
  return <span aria-hidden className={cn('inline-block size-2 shrink-0 rounded-full', c)} />
}
