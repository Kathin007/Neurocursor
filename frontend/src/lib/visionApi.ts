// REST client for the backend vision engine (backend/api/routes_vision.py). Everything here talks to the real backend.
import { backendHttpBase } from './telemetry'

export interface VisionConfig {
  sensitivity: number
  smoothing_alpha: number
  dwell_enabled: boolean
  dwell_ms: number
  blink_click_enabled: boolean
  ear_threshold: number
}

export interface ProfileInfo {
  id: number
  name: string
  created_at_ms: number
  data_source: string
  screen: [number, number]
  held_out_error_px: number
}

export interface VisionStatus {
  state: 'IDLE' | 'RUNNING' | 'ERROR'
  source: string
  last_error: string | null
  camera: { index: number; width: number; height: number } | null
  tracking: { face_found: boolean; fps: number; frames: number; latency_ms_median: number | null; latency_ms_p95: number | null }
  calibration: { calibrated: boolean; active_session: boolean; unsaved_result: boolean; profile: ProfileInfo | null; points: { x: number; y: number }[] }
  control_state: 'ACTIVE' | 'PAUSED' | 'STOPPED'
  cursor_backend: string
  config: VisionConfig & Record<string, unknown>
}

export interface CalibrationResult {
  saved: boolean
  degree: number
  alpha: number
  held_out_error_px: number
  worst_point_error_px: number
  per_point_error_px: Record<string, number>
  train_error_px: number
  n_samples: number
  n_points: number
  screen: [number, number]
}

export class ApiError extends Error {
  readonly status: number

  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

async function call<T>(method: 'GET' | 'POST', path: string, body?: unknown, signal?: AbortSignal): Promise<T> {
  const res = await fetch(`${backendHttpBase()}${path}`, {
    method,
    signal,
    headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  const data: unknown = await res.json().catch(() => ({}))
  if (!res.ok) {
    const detail = (data as { detail?: unknown }).detail
    throw new ApiError(res.status, typeof detail === 'string' ? detail : `HTTP ${res.status}`)
  }
  return data as T
}

export type CalibrateBody =
  | { step: 'start'; screen_w: number; screen_h: number }
  | { step: 'capture'; point_index: number; n_samples?: number }
  | { step: 'finish' }
  | { step: 'save'; name: string }
  | { step: 'cancel' }

export interface VisionApi {
  status(signal?: AbortSignal): Promise<VisionStatus>
  /** Opens the camera and loads the landmark model: the first call can take ~20 s. */
  start(): Promise<VisionStatus>
  stop(): Promise<VisionStatus>
  pause(): Promise<{ control_state: string }>
  resume(): Promise<{ control_state: string }>
  calibrateStart(w: number, h: number): Promise<{ points: { x: number; y: number }[]; screen: [number, number] }>
  calibrateCapture(pointIndex: number, nSamples: number): Promise<{ point_index: number; samples: number }>
  calibrateFinish(): Promise<CalibrationResult>
  calibrateSave(name: string): Promise<{ saved: boolean; profile: ProfileInfo | null }>
  calibrateCancel(): Promise<{ cancelled: boolean }>
}

export const PREVIEW_URL = '/api/vision/preview.mjpg'

export const visionApi: VisionApi = {
  status: (signal) => call('GET', '/api/vision/status', undefined, signal),
  start: () => call('POST', '/api/vision/start', {}),
  stop: () => call('POST', '/api/vision/stop'),
  pause: () => call('POST', '/api/control/pause'),
  resume: () => call('POST', '/api/control/resume'),
  calibrateStart: (w, h) => call('POST', '/api/vision/calibrate', { step: 'start', screen_w: w, screen_h: h }),
  calibrateCapture: (i, n) => call('POST', '/api/vision/calibrate', { step: 'capture', point_index: i, n_samples: n }),
  calibrateFinish: () => call('POST', '/api/vision/calibrate', { step: 'finish' }),
  calibrateSave: (name) => call('POST', '/api/vision/calibrate', { step: 'save', name }),
  calibrateCancel: () => call('POST', '/api/vision/calibrate', { step: 'cancel' }),
}
