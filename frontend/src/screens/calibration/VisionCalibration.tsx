import { useCallback, useState } from 'react'
import { Button } from '@/components/ui/button'
import { Panel, StatusDot } from '@/design/Panel'
import type { Backend } from '@/lib/useBackend'
import { CalibrationOverlay } from './CalibrationOverlay'
import type { CalibrationTimings } from './calibration'
import { CameraPanel } from '../vision/CameraPanel'
import { useVisionTelemetry } from '../vision/useVisionTelemetry'
import type { VisionSession } from '../vision/useVisionSession'

interface Props {
  backend: Pick<Backend, 'subscribe'>
  session: VisionSession
  onGoLive: () => void
  /** Test hook: shorten the waits. */
  timings?: Partial<CalibrationTimings>
}

export function VisionCalibration({ backend, session, onGoLive, timings }: Props) {
  const snap = useVisionTelemetry(backend.subscribe)
  const [open, setOpen] = useState(false)
  const running = session.status?.state === 'RUNNING'
  const cal = session.status?.calibration
  const close = useCallback(() => {
    setOpen(false)
    void session.refresh()
  }, [session])

  return (
    <div className="grid gap-4 lg:grid-cols-[1fr_1fr]">
      <CameraPanel session={session} snap={snap} />

      <div className="space-y-4">
        <Panel title="9-point calibration">
          <ol className="list-decimal space-y-1 pl-5 text-sm text-text2">
            <li>Start the camera and check your face is found.</li>
            <li>Click <strong className="text-text">Calibrate</strong>. The screen goes full-size and shows 9 dots.</li>
            <li>Look at each dot with your eyes only and keep your head still (about 50 cm from the screen, face a light).</li>
            <li>You get the real measured error, and can save it or redo it.</li>
          </ol>
          <div className="mt-4 flex flex-wrap items-center gap-3">
            <Button onClick={() => setOpen(true)} disabled={!running || !session.status?.tracking.face_found}>
              {cal?.calibrated ? 'Recalibrate' : 'Calibrate'}
            </Button>
            <Button variant="secondary" onClick={onGoLive} disabled={!cal?.calibrated}>
              Go to live test
            </Button>
          </div>
          {!running && <p className="mt-2 text-xs text-text2">Start the camera first.</p>}
          {running && !session.status?.tracking.face_found && <p className="mt-2 text-xs text-warning">No face detected yet: face the camera.</p>}
        </Panel>

        <Panel title="Current calibration">
          <ul className="space-y-2 text-sm">
            <li className="flex items-center gap-2">
              <StatusDot state={cal?.calibrated ? 'ok' : 'warn'} />
              {cal?.calibrated ? 'Calibrated' : 'Not calibrated'}
              {cal?.unsaved_result && <span className="text-xs text-warning">(not saved)</span>}
            </li>
            {cal?.profile && (
              <li className="font-mono text-xs text-text2" data-testid="profile-line">
                profile {cal.profile.id} · {cal.profile.data_source} · held-out error {cal.profile.held_out_error_px} px · screen {cal.profile.screen[0]}×{cal.profile.screen[1]}
              </li>
            )}
          </ul>
        </Panel>
      </div>

      {open && <CalibrationOverlay api={session.api} onClose={close} timings={timings} />}
    </div>
  )
}
