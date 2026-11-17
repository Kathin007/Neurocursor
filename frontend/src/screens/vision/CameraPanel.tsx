import { Button } from '@/components/ui/button'
import { Panel, Readout } from '@/design/Panel'
import type { DataSource } from '@/lib/telemetry'
import { PREVIEW_URL } from '@/lib/visionApi'
import type { VisionSession } from './useVisionSession'
import type { VisionSnapshot } from './useVisionTelemetry'

interface Props {
  session: VisionSession
  snap: VisionSnapshot
}

/** Start/stop the real camera and show its live preview (separate MJPEG stream, never the telemetry socket). */
export function CameraPanel({ session, snap }: Props) {
  const { status, starting, error } = session
  const running = status?.state === 'RUNNING'
  const g = snap.gaze

  return (
    <Panel title="Camera" source={running ? (status?.source as DataSource) : undefined} active={running}>
      {running ? (
        <>
          <img
            src={PREVIEW_URL}
            alt="Live camera preview with eye landmarks"
            className="aspect-[4/3] w-full rounded-lg border border-white/8 bg-black/40 object-cover"
          />
          <div className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-4">
            <Readout label="Face" value={g ? (g.face_found ? 'found' : 'lost') : '…'} tone={g && !g.face_found ? 'bad' : g ? 'ok' : undefined} />
            <Readout label="FPS" value={status?.tracking.fps ?? 0} />
            <Readout label="Latency" value={status?.tracking.latency_ms_median ?? '—'} unit="ms" />
            <Readout label="Eye (EAR)" value={g?.ear != null ? g.ear.toFixed(2) : '—'} tone={g?.eyes_closed ? 'warn' : undefined} />
          </div>
          <p className="mt-3 text-xs text-text2">
            {status?.calibration.calibrated
              ? `Calibrated: profile ${status.calibration.profile?.id ?? '(unsaved)'}${status.calibration.profile ? `, held-out error ${status.calibration.profile.held_out_error_px} px` : ''}.`
              : 'Not calibrated yet. Calibrate before using the live test.'}
          </p>
          <Button className="mt-3" size="sm" variant="secondary" onClick={() => void session.stop()}>
            Stop camera
          </Button>
        </>
      ) : (
        <>
          <p className="text-sm text-text2">
            {starting
              ? 'Opening the camera and loading the face model… the first start can take up to ~20 seconds.'
              : 'The camera is off. Starting it turns on your webcam (the LED will light). Video stays on this machine and is never stored.'}
          </p>
          <Button className="mt-3" onClick={() => void session.start()} disabled={starting}>
            {starting ? 'Starting…' : 'Start camera'}
          </Button>
        </>
      )}
      {(error || status?.last_error) && (
        <p role="alert" className="mt-3 text-xs text-error">
          {error ?? status?.last_error}
        </p>
      )}
    </Panel>
  )
}
