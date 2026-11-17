import { useEffect, useState } from 'react'
import { probeCameraPermission, probeCameras, probeWebGL } from '@/lib/browserProbes'
import { useRefreshRate } from '@/lib/hooks'
import type { Backend } from '@/lib/useBackend'

export type CheckStatus = 'pending' | 'ok' | 'warn' | 'fail'
export interface Check {
  id: string
  label: string
  status: CheckStatus
  detail: string
}

/** Real readiness checks: nothing is reported ok unless it was actually observed. */
export function useReadiness(backend: Backend): Check[] {
  const refresh = useRefreshRate()
  const [cams, setCams] = useState<number | null | 'pending'>('pending')
  const [perm, setPerm] = useState<string>('pending')
  const [webgl] = useState(() => probeWebGL())

  useEffect(() => {
    let live = true
    void probeCameras().then((r) => live && setCams(r.count))
    void probeCameraPermission().then((r) => live && setPerm(r))
    return () => {
      live = false
    }
  }, [])

  const checks: Check[] = []

  checks.push(
    backend.rest.kind === 'loading'
      ? { id: 'backend', label: 'Python backend (REST)', status: 'pending', detail: 'Contacting…' }
      : backend.rest.kind === 'error'
        ? { id: 'backend', label: 'Python backend (REST)', status: 'fail', detail: `Unreachable: ${backend.rest.message}` }
        : { id: 'backend', label: 'Python backend (REST)', status: 'ok', detail: `v${backend.rest.status.version}, uptime ${backend.rest.status.uptime_s}s` },
  )

  checks.push({
    id: 'ws',
    label: 'Telemetry WebSocket',
    status: backend.conn === 'open' ? 'ok' : backend.conn === 'connecting' ? 'pending' : 'fail',
    detail: backend.conn,
  })

  checks.push(
    cams === 'pending'
      ? { id: 'camera', label: 'Webcam (browser view)', status: 'pending', detail: 'Enumerating…' }
      : cams === null
        ? { id: 'camera', label: 'Webcam (browser view)', status: 'warn', detail: 'Media-device API unavailable. Backend camera access is verified in M3.' }
        : cams === 0
          ? { id: 'camera', label: 'Webcam (browser view)', status: 'fail', detail: 'No video input device found' }
          : { id: 'camera', label: 'Webcam (browser view)', status: 'ok', detail: `${cams} video input(s) listed. Not opened; backend camera access untested until M3.` },
  )

  checks.push({
    id: 'camera-permission',
    label: 'Camera permission',
    status: perm === 'granted' ? 'ok' : perm === 'denied' ? 'fail' : perm === 'pending' ? 'pending' : 'warn',
    detail: perm === 'pending' ? 'Checking…' : perm,
  })

  const eeg = backend.rest.kind === 'ok' ? backend.rest.status.subsystems.eeg : undefined
  checks.push({
    id: 'eeg',
    label: 'EEG device',
    status: 'warn',
    detail: eeg === undefined ? 'Backend unreachable: no EEG status' : `Backend reports ${eeg}. No headset is detected or assumed.`,
  })

  checks.push(
    refresh === 'pending'
      ? { id: 'refresh', label: 'Display refresh rate', status: 'pending', detail: 'Measuring…' }
      : refresh === null
        ? { id: 'refresh', label: 'Display refresh rate', status: 'warn', detail: 'Could not be measured (tab hidden?)' }
        : { id: 'refresh', label: 'Display refresh rate', status: 'ok', detail: `${refresh} Hz measured. Used to validate SSVEP frequencies.` },
  )

  checks.push({
    id: 'webgl',
    label: 'WebGL (neural background)',
    status: webgl ? 'ok' : 'warn',
    detail: webgl ? 'Available' : 'Unavailable: static background is used',
  })

  return checks
}
