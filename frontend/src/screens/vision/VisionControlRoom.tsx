import { useCallback, useEffect, useRef, useState } from 'react'
import { Button } from '@/components/ui/button'
import { LabeledSlider, LabeledSwitch } from '@/design/Controls'
import { Panel, Readout, StatusDot } from '@/design/Panel'
import type { DataSource } from '@/lib/telemetry'
import type { Backend } from '@/lib/useBackend'
import { CameraPanel } from './CameraPanel'
import { LiveStage } from './LiveStage'
import type { VisionSession } from './useVisionSession'
import { useVisionTelemetry } from './useVisionTelemetry'

interface Props {
  backend: Pick<Backend, 'subscribe' | 'send'>
  session: VisionSession
  onGoCalibrate: () => void
}

const SEND_DEBOUNCE_MS = 150

/** Live test of the real vision engine. Controls are sent to the backend over the telemetry WebSocket. */
export function VisionControlRoom({ backend, session, onGoCalibrate }: Props) {
  const snap = useVisionTelemetry(backend.subscribe)
  const [stage, setStage] = useState(false)
  const { status } = session
  const running = status?.state === 'RUNNING'
  const calibrated = Boolean(status?.calibration.calibrated)
  const paused = status?.control_state !== 'ACTIVE'

  // Local copies of the tunables; seeded once from the backend's real config, then pushed back on change.
  const [cfg, setCfg] = useState({ sensitivity: 1, smoothing_alpha: 0.35, dwell_ms: 1200, dwell_enabled: true, blink_click_enabled: true, ear_threshold: 0.2 })
  const seeded = useRef(false)
  useEffect(() => {
    if (status && !seeded.current) {
      seeded.current = true
      const c = status.config
      setCfg({ sensitivity: c.sensitivity, smoothing_alpha: c.smoothing_alpha, dwell_ms: c.dwell_ms, dwell_enabled: c.dwell_enabled, blink_click_enabled: c.blink_click_enabled, ear_threshold: c.ear_threshold })
    }
  }, [status])

  const timer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const update = (patch: Partial<typeof cfg>) => {
    setCfg((prev) => ({ ...prev, ...patch }))
    if (timer.current) clearTimeout(timer.current)
    timer.current = setTimeout(() => backend.send({ type: 'set_vision_config', config: patch }), SEND_DEBOUNCE_MS)
  }
  useEffect(() => () => { if (timer.current) clearTimeout(timer.current) }, [])

  const closeStage = useCallback(() => setStage(false), [])

  return (
    <div className="mx-auto max-w-6xl px-6 py-8">
      <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-3xl font-semibold tracking-tight">Live test</h1>
          <p className="mt-1 text-sm text-text2">
            Webcam gaze control (computer vision, not a BCI). The cursor is simulated: it never moves your real mouse.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <span className="label-caps" data-testid="control-state">{status?.control_state ?? '—'}</span>
          <Button variant="secondary" disabled={!running} onClick={() => void (paused ? session.resume() : session.pause())}>
            {paused ? 'Resume' : 'Pause'}
          </Button>
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-[1.1fr_1fr]">
        <div className="space-y-4">
          <CameraPanel session={session} snap={snap} />

          <Panel title="Live stage" active={running && calibrated}>
            <p className="text-sm text-text2">
              Opens a full-screen stage with six target tiles. Your simulated cursor follows your gaze; dwell (hold still) or a blink presses the tile under it.
            </p>
            <div className="mt-3 flex flex-wrap items-center gap-3">
              <Button onClick={() => setStage(true)} disabled={!running || !calibrated}>
                Open live stage
              </Button>
              {!running && <span className="text-xs text-text2">Start the camera first.</span>}
              {running && !calibrated && (
                <span className="text-xs text-warning">
                  Not calibrated.{' '}
                  <button className="underline" onClick={onGoCalibrate}>Calibrate now</button>
                </span>
              )}
            </div>
          </Panel>
        </div>

        <div className="space-y-4">
          <Panel title="Gaze → cursor" source={running ? (status?.source as DataSource) : undefined}>
            <div className="grid grid-cols-2 gap-4">
              <Readout label="Cursor (0–1)" value={snap.cursor ? `${snap.cursor.x.toFixed(2)}, ${snap.cursor.y.toFixed(2)}` : '—'} />
              <Readout label="Raw gaze" value={snap.gaze?.gaze ? `${snap.gaze.gaze.x.toFixed(2)}, ${snap.gaze.gaze.y.toFixed(2)}` : '—'} />
              <Readout label="Eyes" value={snap.gaze ? (snap.gaze.eyes_closed ? 'CLOSED' : 'open') : '—'} tone={snap.gaze?.eyes_closed ? 'warn' : undefined} />
              <Readout label="Dwell" value={snap.gaze ? `${Math.round(snap.gaze.dwell * 100)}%` : '—'} />
              <Readout label="Clicks accepted" value={snap.accepted} tone="ok" />
              <Readout label="Clicks rejected" value={snap.rejected} tone={snap.rejected ? 'warn' : undefined} />
            </div>
            <ul aria-label="Recent clicks" className="mt-3 space-y-1 font-mono text-xs">
              {snap.clicks.slice(0, 5).map((c) => (
                <li key={c.id} className={c.accepted ? 'text-success' : 'text-error'}>
                  {c.trigger} {c.accepted ? 'click accepted' : `rejected: ${c.reason}`} · confidence {c.confidence.toFixed(2)}
                </li>
              ))}
              {snap.clicks.length === 0 && <li className="text-text2">No clicks yet.</li>}
            </ul>
          </Panel>

          <Panel title="Controls">
            <div className="space-y-5">
              <LabeledSlider label="Sensitivity" value={cfg.sensitivity} min={0.5} max={3} step={0.1} onChange={(v) => update({ sensitivity: Math.round(v * 10) / 10 })} />
              <LabeledSlider label="Smoothing α" value={cfg.smoothing_alpha} min={0.05} max={1} step={0.05} onChange={(v) => update({ smoothing_alpha: Math.round(v * 100) / 100 })} />
              <LabeledSwitch label="Dwell click" checked={cfg.dwell_enabled} onChange={(v) => update({ dwell_enabled: v })} />
              <LabeledSlider label="Dwell time" value={cfg.dwell_ms} min={300} max={3000} step={100} unit="ms" onChange={(v) => update({ dwell_ms: v })} />
              <LabeledSwitch label="Blink click" checked={cfg.blink_click_enabled} onChange={(v) => update({ blink_click_enabled: v })} />
              <LabeledSlider label="Blink EAR threshold" value={cfg.ear_threshold} min={0.1} max={0.3} step={0.01} onChange={(v) => update({ ear_threshold: Math.round(v * 100) / 100 })} />
            </div>
            <p className="mt-3 flex items-center gap-2 text-xs text-text2">
              <StatusDot state={running ? 'ok' : 'idle'} />
              Changes apply to the running engine immediately. Tip: your open-eye EAR is shown on the camera panel; set the threshold between it and your blink value.
            </p>
          </Panel>
        </div>
      </div>

      {stage && <LiveStage snap={snap} session={session} onClose={closeStage} />}
    </div>
  )
}
