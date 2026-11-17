import { useEffect, useRef, useState } from 'react'
import type { DataSource, TelemetryEvent } from '@/lib/telemetry'

export interface GazePayload {
  face_found: boolean
  ear: number | null
  quality: number
  eyes_closed: boolean
  blink: boolean
  head_pose: { yaw: number; pitch: number; roll: number } | null
  gaze: { x: number; y: number } | null
  calibrated: boolean
  dwell: number
  fps: number
  latency_ms: number
  proc_ms: number
}

export interface ClickRecord {
  id: number
  trigger: 'BLINK' | 'DWELL'
  accepted: boolean
  reason: string
  confidence: number
  x: number
  y: number
  at: number
}

export interface VisionSnapshot {
  source: DataSource | null
  gaze: GazePayload | null
  cursor: { x: number; y: number } | null
  clicks: ClickRecord[] // newest first
  accepted: number
  rejected: number
  lastClick: ClickRecord | null
}

const EMPTY: VisionSnapshot = { source: null, gaze: null, cursor: null, clicks: [], accepted: 0, rejected: 0, lastClick: null }
const MIN_FLUSH_MS = 50 // at most ~20 renders per second, whatever the event rate
const KEEP = 30

/** Folds gaze_update / cursor_update / interaction_event telemetry into one snapshot, pushed to React at most every 50 ms. */
export function useVisionTelemetry(subscribe: (fn: (e: TelemetryEvent) => void) => () => void): VisionSnapshot {
  const [snap, setSnap] = useState<VisionSnapshot>(EMPTY)
  const store = useRef<VisionSnapshot>(EMPTY)
  const nextId = useRef(1)

  useEffect(() => {
    let timer: ReturnType<typeof setTimeout> | null = null
    let last = 0
    const schedule = () => {
      if (timer) return
      const wait = Math.max(0, MIN_FLUSH_MS - (performance.now() - last))
      timer = setTimeout(() => {
        timer = null
        last = performance.now()
        setSnap(store.current)
      }, wait)
    }

    const off = subscribe((e) => {
      const s = store.current
      if (e.type === 'gaze_update') {
        store.current = { ...s, source: e.source, gaze: e.payload as unknown as GazePayload }
      } else if (e.type === 'cursor_update') {
        const { x, y } = e.payload as { x: number; y: number }
        store.current = { ...s, cursor: { x, y } }
      } else if (e.type === 'interaction_event' && e.payload.kind === 'CLICK') {
        const p = e.payload as { trigger: 'BLINK' | 'DWELL'; accepted: boolean; reason: string; confidence: number; x: number; y: number }
        const rec: ClickRecord = { id: nextId.current++, ...p, at: e.timestamp }
        store.current = {
          ...s,
          clicks: [rec, ...s.clicks].slice(0, KEEP),
          accepted: s.accepted + (rec.accepted ? 1 : 0),
          rejected: s.rejected + (rec.accepted ? 0 : 1),
          lastClick: rec,
        }
      } else {
        return
      }
      schedule()
    })
    return () => {
      off()
      if (timer) clearTimeout(timer)
    }
  }, [subscribe])

  return snap
}
