import { useEffect, useRef, useState } from 'react'
import { Button } from '@/components/ui/button'
import { Panel } from '@/design/Panel'
import { prefersReducedMotion } from '@/lib/browserProbes'
import { useRefreshRate } from '@/lib/hooks'
import { checkFrequency, type SsvepTarget } from '@/lib/ssvep'

/**
 * Frame-locked flicker: each target toggles on a whole number of display frames per half-cycle.
 * Off by default: flashing 6-15 Hz stimuli can trigger seizures in photosensitive people.
 */
export function StimulusTargets({ targets, highlightId }: { targets: SsvepTarget[]; highlightId?: string }) {
  const refresh = useRefreshRate()
  const [on, setOn] = useState(false)
  const refs = useRef<Record<string, HTMLDivElement | null>>({})
  const reduced = prefersReducedMotion()

  useEffect(() => {
    if (!on || typeof refresh !== 'number') return
    const half = Object.fromEntries(
      targets.map((t) => [t.id, checkFrequency(t.hz, refresh).framesPerCycle / 2] as const),
    )
    const els = refs.current
    let frame = 0
    let id = 0
    const tick = () => {
      frame++
      for (const t of targets) {
        const el = els[t.id]
        if (!el) continue
        const lit = Math.floor(frame / Math.max(1, Math.round(half[t.id] ?? 1))) % 2 === 0
        el.style.opacity = lit ? '1' : '0.12'
      }
      id = requestAnimationFrame(tick)
    }
    id = requestAnimationFrame(tick)
    return () => {
      cancelAnimationFrame(id)
      for (const t of targets) {
        const el = els[t.id]
        if (el) el.style.opacity = '0.5'
      }
    }
  }, [on, refresh, targets])

  return (
    <Panel title="SSVEP stimulus targets" actions={
      <Button size="sm" variant={on ? 'destructive' : 'secondary'} disabled={reduced || typeof refresh !== 'number'} onClick={() => setOn((v) => !v)}>
        {on ? 'Stop flicker' : 'Start flicker'}
      </Button>
    }>
      <p role="note" className="mb-3 rounded-md border border-warning/40 bg-warning/10 p-2 text-xs text-warning">
        Photosensitivity warning: flicker is off until you start it. Stop immediately if you feel unwell.
        {reduced && ' Disabled because your system requests reduced motion.'}
      </p>
      <div className="grid grid-cols-5 gap-2">
        {targets.map((t) => {
          const c = typeof refresh === 'number' ? checkFrequency(t.hz, refresh) : null
          return (
            <div key={t.id} className="text-center">
              <div
                ref={(el) => { refs.current[t.id] = el }}
                data-testid={`stim-${t.id}`}
                className={`mx-auto aspect-square w-full rounded-lg bg-text opacity-50 ${highlightId === t.id ? 'ring-2 ring-cyan' : ''}`}
              />
              <div className="mt-1 text-xs font-medium">{t.label}</div>
              <div className="font-mono text-[0.68rem] text-text2">{t.hz} Hz</div>
              {c && !c.compatible && <div className="font-mono text-[0.68rem] text-warning">≈{c.realizedHz} Hz actual</div>}
            </div>
          )
        })}
      </div>
    </Panel>
  )
}
