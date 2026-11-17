import { useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { Button } from '@/components/ui/button'
import { StatusDot } from '@/design/Panel'
import { enterFullscreen, exitFullscreen } from '@/lib/fullscreen'
import { useScrollLock } from '@/lib/useScrollLock'
import { PREVIEW_URL } from '@/lib/visionApi'
import { hitTile, TILES } from './tiles'
import type { VisionSession } from './useVisionSession'
import type { VisionSnapshot } from './useVisionTelemetry'

interface Props {
  snap: VisionSnapshot
  session: VisionSession
  onClose: () => void
}

const FLASH_MS = 700
const pct = (v: number) => `${v * 100}%`

/** Full-screen live test. The cursor here is SIMULATED: it is drawn from backend cursor_update events and never moves the real mouse. */
export function LiveStage({ snap, session, onClose }: Props) {
  const root = useRef<HTMLDivElement>(null)
  const [counts, setCounts] = useState<Record<string, number>>({})
  const [flash, setFlash] = useState<string | null>(null)
  const status = session.status
  useScrollLock()
  const paused = status?.control_state !== 'ACTIVE'
  const g = snap.gaze
  const click = snap.lastClick

  useEffect(() => {
    void enterFullscreen(root.current ?? undefined)
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    const onFs = () => !document.fullscreenElement && onClose()
    window.addEventListener('keydown', onKey)
    document.addEventListener('fullscreenchange', onFs)
    return () => {
      window.removeEventListener('keydown', onKey)
      document.removeEventListener('fullscreenchange', onFs)
    }
  }, [onClose])

  // An accepted click presses whichever tile the cursor was over when it fired.
  const lastId = click?.id
  useEffect(() => {
    if (!click || !click.accepted) return
    const tile = hitTile(click.x, click.y)
    if (!tile) return
    setCounts((c) => ({ ...c, [tile.id]: (c[tile.id] ?? 0) + 1 }))
    setFlash(tile.id)
    const timer = setTimeout(() => setFlash(null), FLASH_MS)
    return () => clearTimeout(timer)
    // eslint-disable-next-line react-hooks/exhaustive-deps -- fire once per click id
  }, [lastId])

  const close = () => {
    exitFullscreen()
    onClose()
  }
  const dwell = g?.dwell ?? 0
  const r = 22
  const circ = 2 * Math.PI * r

  return createPortal(
    <div ref={root} role="dialog" aria-label="Live test" className="fixed inset-0 z-50 select-none overflow-hidden bg-bg">
      {TILES.map((t) => (
        <div
          key={t.id}
          data-testid={`tile-${t.id}`}
          data-pressed={flash === t.id}
          className={`glass absolute grid place-items-center transition-colors duration-150 ${
            flash === t.id ? 'glow-violet bg-violet/40' : ''
          }`}
          style={{ left: pct(t.x), top: pct(t.y), width: pct(t.w), height: pct(t.h) }}
        >
          <span className="text-5xl font-semibold text-text/80">{t.label}</span>
          <span className="absolute bottom-2 right-3 font-mono text-xs text-text2" data-testid={`count-${t.id}`}>
            pressed {counts[t.id] ?? 0}
          </span>
        </div>
      ))}

      {g?.gaze && (
        <span
          data-testid="gaze-marker"
          title="raw gaze estimate"
          className="absolute size-8 -translate-x-1/2 -translate-y-1/2 rounded-full border border-lavender/70"
          style={{ left: pct(g.gaze.x), top: pct(g.gaze.y) }}
        />
      )}

      {snap.cursor && (
        <div
          data-testid="sim-cursor"
          data-closed={Boolean(g?.eyes_closed)}
          className="absolute -translate-x-1/2 -translate-y-1/2 transition-[left,top] duration-100 ease-linear"
          style={{ left: pct(snap.cursor.x), top: pct(snap.cursor.y) }}
        >
          <svg width="56" height="56" viewBox="0 0 56 56" className="absolute -left-7 -top-7" aria-hidden>
            <circle cx="28" cy="28" r={r} fill="none" stroke="rgb(255 255 255 / 0.12)" strokeWidth="3" />
            <circle
              cx="28" cy="28" r={r} fill="none" stroke="#22d3ee" strokeWidth="3" strokeLinecap="round"
              strokeDasharray={circ} strokeDashoffset={circ * (1 - dwell)} transform="rotate(-90 28 28)"
            />
          </svg>
          <span className={`block rounded-full ${g?.eyes_closed ? 'size-2 bg-warning' : 'glow-active size-4 bg-cyan'}`} />
        </div>
      )}

      {click && (
        <span
          key={click.id}
          data-testid="click-ripple"
          data-accepted={click.accepted}
          className={`ripple pointer-events-none absolute -translate-x-1/2 -translate-y-1/2 rounded-full border-2 ${
            click.accepted ? 'border-success' : 'border-error'
          }`}
          style={{ left: pct(click.x), top: pct(click.y) }}
        />
      )}

      {/* HUD */}
      <div className="absolute left-4 top-4 space-y-1 font-mono text-xs text-text2">
        <div className="flex items-center gap-2"><StatusDot state={g?.face_found ? 'ok' : 'bad'} />face {g?.face_found ? 'found' : 'lost'}</div>
        <div data-testid="eye-state" className={g?.eyes_closed ? 'text-warning' : ''}>eyes {g?.eyes_closed ? 'CLOSED' : 'open'} · EAR {g?.ear != null ? g.ear.toFixed(2) : '—'}</div>
        <div>{status?.tracking.fps ?? 0} fps · {g ? g.latency_ms.toFixed(0) : '—'} ms</div>
        <div>clicks accepted {snap.accepted} · rejected {snap.rejected}</div>
        <div className="text-warning">SIMULATED cursor: your real mouse is not touched</div>
      </div>

      <div className="absolute right-4 top-4 flex items-center gap-2">
        <Button size="sm" variant="secondary" onClick={() => void (paused ? session.resume() : session.pause())}>
          {paused ? 'Resume' : 'Pause'}
        </Button>
        <Button size="sm" variant="outline" onClick={close}>Exit (Esc)</Button>
      </div>

      {status && !status.calibration.calibrated && (
        <p role="alert" className="absolute inset-x-0 top-20 text-center text-warning">
          Not calibrated: the cursor will not move. Exit and calibrate first.
        </p>
      )}
      {paused && status?.calibration.calibrated && (
        <p role="status" className="absolute inset-x-0 top-20 text-center text-warning">Control is {status?.control_state.toLowerCase()}: the cursor is frozen.</p>
      )}

      <p className="absolute inset-x-0 bottom-5 text-center text-sm text-text2">
        Look at a tile. Hold still to press it (dwell ring), or blink once. A long eye closure never clicks.
      </p>

      <ul aria-label="Click log" className="absolute bottom-16 left-4 space-y-1 font-mono text-xs">
        {snap.clicks.slice(0, 5).map((c) => (
          <li key={c.id} className={c.accepted ? 'text-success' : 'text-error'}>
            {c.trigger} {c.accepted ? 'click' : `rejected: ${c.reason}`} · {c.confidence.toFixed(2)}
          </li>
        ))}
      </ul>

      <img
        src={PREVIEW_URL}
        alt="Camera preview"
        className="absolute bottom-4 right-4 w-48 rounded-lg border border-white/10 opacity-90"
      />
    </div>,
    document.body,
  )
}
