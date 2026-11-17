import { vi } from 'vitest'
import { TelemetryClient } from '@/lib/telemetry'

export class FakeSocket {
  sent: string[] = []
  onopen: (() => void) | null = null
  onclose: (() => void) | null = null
  onmessage: ((m: { data: string }) => void) | null = null
  send(d: string) {
    this.sent.push(d)
  }
  close() {
    this.onclose?.()
  }
}

export const STATUS = {
  app: 'neurocursor', version: '0.1.0', milestone: 'M1', timestamp: 1, uptime_s: 3.5,
  python: '3.12.8', platform: 'test', telemetry: { clients: 0, dropped_events: 0 },
  subsystems: { vision: 'NOT_IMPLEMENTED', eeg: 'NOT_IMPLEMENTED', cursor: 'NOT_IMPLEMENTED' },
}

export function stubFetchOk() {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve(STATUS) }))
}

/** A client factory with a stable identity (App's effect depends on it). */
export function makeFactory(sock = new FakeSocket()) {
  const create = () => new TelemetryClient('ws://x', () => sock as unknown as WebSocket)
  return { sock, create }
}

// ---------------------------------------------------------------- vision fixtures
import type { CalibrationResult, VisionApi, VisionStatus } from '@/lib/visionApi'
import type { TelemetryEvent } from '@/lib/telemetry'
import type { VisionSession } from '@/screens/vision/useVisionSession'

export const POINTS = [0.1, 0.5, 0.9].flatMap((y) => [0.1, 0.5, 0.9].map((x) => ({ x, y })))

export function visionStatus(over: { state?: VisionStatus['state']; calibrated?: boolean; face?: boolean; control?: VisionStatus['control_state'] } = {}): VisionStatus {
  const calibrated = over.calibrated ?? false
  return {
    state: over.state ?? 'IDLE', source: 'REAL_WEBCAM', last_error: null,
    camera: over.state === 'RUNNING' ? { index: 0, width: 640, height: 480 } : null,
    tracking: { face_found: over.face ?? false, fps: 27.5, frames: 100, latency_ms_median: 34.7, latency_ms_p95: 41 },
    calibration: {
      calibrated, active_session: false, unsaved_result: false, points: POINTS,
      profile: calibrated ? { id: 3, name: 'p', created_at_ms: 1, data_source: 'REAL_WEBCAM', screen: [1920, 1080], held_out_error_px: 88 } : null,
    },
    control_state: over.control ?? 'ACTIVE', cursor_backend: 'SimulatedCursor',
    config: { sensitivity: 1, smoothing_alpha: 0.35, dwell_enabled: true, dwell_ms: 1200, blink_click_enabled: true, ear_threshold: 0.2 },
  }
}

export function calibrationResult(errorPx: number, screen: [number, number] = [1920, 1080]): CalibrationResult {
  return {
    saved: false, degree: 1, alpha: 1, held_out_error_px: errorPx, worst_point_error_px: errorPx * 2, train_error_px: errorPx / 2,
    n_samples: 225, n_points: 9, screen, per_point_error_px: Object.fromEntries(Array.from({ length: 9 }, (_, i) => [String(i), errorPx + i])),
  }
}

/** A VisionApi whose every method is a vi.fn with a sensible default; override per test. */
export function fakeVisionApi(over: Partial<VisionApi> = {}): { [K in keyof VisionApi]: ReturnType<typeof vi.fn> } & VisionApi {
  const api = {
    status: vi.fn().mockResolvedValue(visionStatus()),
    start: vi.fn().mockResolvedValue(visionStatus({ state: 'RUNNING', face: true })),
    stop: vi.fn().mockResolvedValue(visionStatus()),
    pause: vi.fn().mockResolvedValue({ control_state: 'PAUSED' }),
    resume: vi.fn().mockResolvedValue({ control_state: 'ACTIVE' }),
    calibrateStart: vi.fn().mockResolvedValue({ points: POINTS, screen: [1024, 768] }),
    calibrateCapture: vi.fn().mockImplementation((i: number, n: number) => Promise.resolve({ point_index: i, samples: n })),
    calibrateFinish: vi.fn().mockResolvedValue(calibrationResult(80)),
    calibrateSave: vi.fn().mockResolvedValue({ saved: true, profile: visionStatus({ calibrated: true }).calibration.profile }),
    calibrateCancel: vi.fn().mockResolvedValue({ cancelled: true }),
    ...over,
  }
  return api as never
}

/** A fake telemetry backend: tests push events with emit(). */
export function fakeBackend() {
  const listeners = new Set<(e: TelemetryEvent) => void>()
  const send = vi.fn().mockReturnValue(true)
  return {
    subscribe: (fn: (e: TelemetryEvent) => void) => {
      listeners.add(fn)
      return () => void listeners.delete(fn)
    },
    send,
    emit: (type: TelemetryEvent['type'], payload: Record<string, unknown>) =>
      listeners.forEach((fn) => fn({ type, timestamp: Date.now(), source: 'REAL_WEBCAM', payload })),
  }
}

export function fakeSession(status: VisionStatus | null, api: VisionApi = fakeVisionApi()): VisionSession & { start: ReturnType<typeof vi.fn> } {
  return {
    api, status, starting: false, error: null,
    start: vi.fn().mockResolvedValue(undefined), stop: vi.fn().mockResolvedValue(undefined), refresh: vi.fn().mockResolvedValue(undefined),
    pause: vi.fn().mockResolvedValue(undefined), resume: vi.fn().mockResolvedValue(undefined),
  } as never
}

export const gazePayload = (over: Record<string, unknown> = {}) => ({
  face_found: true, ear: 0.28, quality: 0.9, eyes_closed: false, blink: false, head_pose: null, gaze: { x: 0.3, y: 0.4 },
  calibrated: true, dwell: 0.25, fps: 27, latency_ms: 35, proc_ms: 20, ...over,
})
