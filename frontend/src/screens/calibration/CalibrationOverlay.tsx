import { useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { Button } from '@/components/ui/button'
import { enterFullscreen, exitFullscreen } from '@/lib/fullscreen'
import { useScrollLock } from '@/lib/useScrollLock'
import { ApiError, type CalibrationResult, type ProfileInfo, type VisionApi } from '@/lib/visionApi'
import { DEFAULT_TIMINGS, verdict, type CalibrationTimings } from './calibration'

type Point = { x: number; y: number }
type Phase =
  | { kind: 'starting' }
  | { kind: 'intro'; seconds: number }
  | { kind: 'point'; index: number; stage: 'settle' | 'capture' }
  | { kind: 'fitting' }
  | { kind: 'result'; result: CalibrationResult }
  | { kind: 'error'; message: string }

interface Props {
  api: VisionApi
  onClose: () => void
  timings?: Partial<CalibrationTimings>
}

const sleep = (ms: number) => new Promise<void>((r) => setTimeout(r, ms))

export function CalibrationOverlay({ api, onClose, timings }: Props) {
  const t = { ...DEFAULT_TIMINGS, ...timings }
  const cfg = useRef({ api, t })
  useEffect(() => {
    cfg.current = { api, t }
  })
  const root = useRef<HTMLDivElement>(null)
  const [runId, setRunId] = useState(0)
  const [phase, setPhase] = useState<Phase>({ kind: 'starting' })
  const [points, setPoints] = useState<Point[]>([])
  const [done, setDone] = useState(0)
  const [notice, setNotice] = useState<string | null>(null)
  const [saved, setSaved] = useState<ProfileInfo | null>(null)
  const finished = useRef(false)
  useScrollLock()

  // The whole calibration run. `cancelled` makes every await bail out if the overlay is closed or restarted.
  useEffect(() => {
    let cancelled = false
    finished.current = false
    void (async () => {
      const { api: a, t: tm } = cfg.current
      try {
        await enterFullscreen(root.current ?? undefined)
        await sleep(300) // let the fullscreen resize settle so the reported screen size is the real one
        if (cancelled) return
        const start = await a.calibrateStart(window.innerWidth, window.innerHeight)
        if (cancelled) return
        setPoints(start.points)

        const secs = Math.max(1, Math.round(tm.countdownMs / 1000))
        for (let s = secs; s > 0; s--) {
          setPhase({ kind: 'intro', seconds: s })
          await sleep(tm.countdownMs / secs)
          if (cancelled) return
        }
        for (let i = 0; i < start.points.length; i++) {
          let ok = false
          for (let attempt = 0; attempt <= tm.maxRetries && !ok; attempt++) {
            setPhase({ kind: 'point', index: i, stage: 'settle' })
            await sleep(tm.settleMs) // give the eyes time to land on the dot before sampling
            if (cancelled) return
            setPhase({ kind: 'point', index: i, stage: 'capture' })
            try {
              await a.calibrateCapture(i, tm.samples)
              ok = true
            } catch (e) {
              if (e instanceof ApiError && e.status === 408 && attempt < tm.maxRetries) {
                setNotice(`Point ${i + 1}: face not seen clearly, retrying (${attempt + 1}/${tm.maxRetries})…`)
                continue
              }
              throw e
            }
          }
          setNotice(null)
          setDone(i + 1)
        }
        setPhase({ kind: 'fitting' })
        const result = await a.calibrateFinish()
        if (cancelled) return
        finished.current = true
        setPhase({ kind: 'result', result })
      } catch (e) {
        if (!cancelled) setPhase({ kind: 'error', message: e instanceof Error ? e.message : String(e) })
      }
    })()
    return () => {
      cancelled = true
      if (!finished.current) void cfg.current.api.calibrateCancel().catch(() => {})
    }
  }, [runId])

  // Esc, or leaving fullscreen, closes the overlay.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    const onFs = () => !document.fullscreenElement && onClose()
    window.addEventListener('keydown', onKey)
    document.addEventListener('fullscreenchange', onFs)
    return () => {
      window.removeEventListener('keydown', onKey)
      document.removeEventListener('fullscreenchange', onFs)
    }
  }, [onClose])

  const close = () => {
    exitFullscreen()
    onClose()
  }

  const restart = () => {
    setPhase({ kind: 'starting' })
    setDone(0)
    setNotice(null)
    setSaved(null)
    setRunId((n) => n + 1)
  }

  const save = async () => {
    try {
      const r = await api.calibrateSave(`ui ${new Date().toISOString().slice(0, 16).replace('T', ' ')}`)
      setSaved(r.profile)
    } catch (e) {
      setNotice(e instanceof Error ? e.message : String(e))
    }
  }

  const current = phase.kind === 'point' ? points[phase.index] : undefined

  return createPortal(
    <div ref={root} role="dialog" aria-label="Calibration" className="fixed inset-0 z-50 select-none bg-bg">
      {points.map((p, i) => (
        <span
          key={i}
          data-testid={`cal-dot-${i}`}
          data-state={i < done ? 'done' : phase.kind === 'point' && phase.index === i ? phase.stage : 'pending'}
          className={`absolute size-5 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 transition-colors ${
            i < done ? 'border-success bg-success/50' : 'border-text2/30'
          }`}
          style={{ left: `${p.x * 100}%`, top: `${p.y * 100}%` }}
        />
      ))}

      {current && phase.kind === 'point' && (
        <span
          data-testid="cal-active-dot"
          className={`absolute size-9 -translate-x-1/2 -translate-y-1/2 rounded-full ${
            phase.stage === 'settle' ? 'bg-lavender/70 animate-pulse' : 'glow-active bg-cyan'
          }`}
          style={{ left: `${current.x * 100}%`, top: `${current.y * 100}%` }}
        />
      )}

      <div className="absolute inset-x-0 top-6 mx-auto max-w-xl text-center">
        {phase.kind === 'starting' && <p className="text-lg">Preparing…</p>}
        {phase.kind === 'intro' && (
          <>
            <p className="text-2xl font-medium">Get ready: {phase.seconds}</p>
            <p className="mt-2 text-sm text-text2">Follow each dot with your eyes only. Keep your head still. Esc cancels.</p>
          </>
        )}
        {phase.kind === 'point' && (
          <p className="text-lg">
            Dot {phase.index + 1} of {points.length}: {phase.stage === 'settle' ? 'look at it…' : 'hold your gaze'}
          </p>
        )}
        {phase.kind === 'fitting' && <p className="text-lg">Fitting the model…</p>}
        {notice && <p role="status" className="mt-2 text-sm text-warning">{notice}</p>}
      </div>

      {phase.kind === 'error' && (
        <div className="absolute inset-0 grid place-items-center">
          <div className="glass max-w-md p-6 text-center">
            <p className="text-lg font-medium">Calibration stopped</p>
            <p role="alert" className="mt-2 text-sm text-error">{phase.message}</p>
            <div className="mt-4 flex justify-center gap-3">
              <Button onClick={restart}>Try again</Button>
              <Button variant="secondary" onClick={close}>Close</Button>
            </div>
          </div>
        </div>
      )}

      {phase.kind === 'result' && <ResultCard result={phase.result} saved={saved} notice={notice} onSave={() => void save()} onRedo={restart} onClose={close} />}
    </div>,
    document.body,
  )
}

function ResultCard({ result, saved, notice, onSave, onRedo, onClose }: {
  result: CalibrationResult
  saved: ProfileInfo | null
  notice: string | null
  onSave: () => void
  onRedo: () => void
  onClose: () => void
}) {
  const [w, h] = result.screen
  const v = verdict(result.held_out_error_px, w)
  const tone = v.label === 'good' ? 'text-success' : v.label === 'fair' ? 'text-warning' : 'text-error'
  return (
    <div className="absolute inset-0 grid place-items-center bg-bg/80">
      <div className="glass w-full max-w-xl p-6">
        <p className="label-caps">Calibration result · measured on your face, held-out points</p>
        <p className="mt-2 font-mono text-4xl tabular-nums" data-testid="held-out-error">
          {Math.round(result.held_out_error_px)} px
        </p>
        <p className="text-xs text-text2">
          mean error on points left out of the fit, on a {w}×{h} screen ({((result.held_out_error_px / w) * 100).toFixed(1)}% of its width) · worst point{' '}
          {Math.round(result.worst_point_error_px)} px · training error {Math.round(result.train_error_px)} px (optimistic)
        </p>
        <p role="status" data-testid="verdict" data-verdict={v.label} className={`mt-3 text-sm ${tone}`}>{v.text}</p>
        <div className="mt-4 grid grid-cols-3 gap-2 font-mono text-xs" aria-label="Held-out error per point">
          {Array.from({ length: 9 }, (_, i) => (
            <div key={i} className="rounded-md bg-white/5 px-2 py-1 text-center">
              <span className="text-text2">{i + 1}</span> {Math.round(result.per_point_error_px[String(i)] ?? 0)} px
            </div>
          ))}
        </div>
        {saved && <p role="status" className="mt-3 text-sm text-success">Saved as profile {saved.id}. It loads automatically next time.</p>}
        {notice && <p role="alert" className="mt-3 text-sm text-error">{notice}</p>}
        <div className="mt-5 flex flex-wrap gap-3">
          <Button onClick={onSave} disabled={saved !== null}>{saved ? 'Saved' : 'Save profile'}</Button>
          <Button variant="secondary" onClick={onRedo}>Recalibrate</Button>
          <Button variant="outline" onClick={onClose}>Done</Button>
        </div>
        <p className="mt-3 text-xs text-text2">Not saved? The calibration still works for this session. Saved profiles are stored as model numbers only, never images.</p>
      </div>
    </div>
  )
}
