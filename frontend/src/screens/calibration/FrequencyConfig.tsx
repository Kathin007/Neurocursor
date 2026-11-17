import { useMemo } from 'react'
import { NumberField } from '@/design/Controls'
import { Panel } from '@/design/Panel'
import { useRefreshRate } from '@/lib/hooks'
import { checkFrequency, harmonicConflicts, type SsvepTarget } from '@/lib/ssvep'

interface Props {
  targets: SsvepTarget[]
  onChange: (t: SsvepTarget[]) => void
}

/** Real validation (not demo data): each frequency is checked against the measured display refresh rate. */
export function FrequencyConfig({ targets, onChange }: Props) {
  const refresh = useRefreshRate()
  const conflicts = useMemo(() => harmonicConflicts(targets), [targets])
  const label = (id: string) => targets.find((t) => t.id === id)?.label ?? id

  return (
    <Panel title="SSVEP stimulus frequencies">
      <p className="mb-3 text-xs text-text2" data-testid="refresh-line">
        Display refresh: {refresh === 'pending' ? 'measuring…' : refresh === null ? 'could not be measured' : `${refresh} Hz (measured)`}
      </p>
      <ul className="space-y-3">
        {targets.map((t) => {
          const check = typeof refresh === 'number' ? checkFrequency(t.hz, refresh) : null
          return (
            <li key={t.id} data-testid={`freq-${t.id}`}>
              <div className="flex flex-wrap items-center gap-3">
                <NumberField
                  label={t.label}
                  value={t.hz}
                  unit="Hz"
                  onChange={(hz) => onChange(targets.map((x) => (x.id === t.id ? { ...x, hz } : x)))}
                />
                {check && (
                  <span className={`font-mono text-xs ${check.compatible ? 'text-success' : 'text-warning'}`}>
                    {check.framesPerCycle} frames/cycle · {check.compatible ? 'frame-compatible' : 'NOT frame-compatible'}
                    {check.compatible && !check.balanced && ' (odd frame count: uneven duty cycle)'}
                  </span>
                )}
              </div>
              {check && !check.compatible && (
                <p role="alert" className="mt-1 pl-16 text-xs text-warning">
                  {t.hz} Hz would flicker at {check.realizedHz} Hz on this display. Frame-compatible alternatives: {check.alternatives.join(', ')} Hz.
                </p>
              )}
            </li>
          )
        })}
      </ul>
      {conflicts.length > 0 && (
        <p role="alert" className="mt-3 text-xs text-warning">
          Harmonic overlap: {conflicts.map((c) => `${label(c.a)} ×${c.harmonic} ≈ ${label(c.b)}`).join('; ')}. CCA may confuse these targets.
        </p>
      )}
    </Panel>
  )
}
