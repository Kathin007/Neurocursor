import { cn } from '@/lib/utils'
import type { DataSource } from '@/lib/telemetry'

const STYLE: Record<DataSource, string> = {
  DEMO_DATA: 'border-warning/70 bg-warning/15 text-warning',
  REAL_WEBCAM: 'border-cyan/60 bg-cyan/10 text-cyan',
  REAL_EEG: 'border-success/60 bg-success/10 text-success',
  SYNTHETIC_EEG: 'border-violet/60 bg-violet/15 text-lavender',
  RECORDED_EEG: 'border-lavender/50 bg-lavender/10 text-lavender',
}

/** Every data-bearing panel carries one of these. DEMO_DATA is deliberately loud. */
export function SourceBadge({ source, className }: { source: DataSource; className?: string }) {
  return (
    <span
      data-source={source}
      title={source === 'DEMO_DATA' ? 'Scripted placeholder values, not measured from any device' : source}
      className={cn(
        'inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 font-mono text-[0.68rem] font-semibold tracking-wider',
        STYLE[source],
        className,
      )}
    >
      <span aria-hidden className="size-1.5 rounded-full bg-current" />
      {source}
    </span>
  )
}
