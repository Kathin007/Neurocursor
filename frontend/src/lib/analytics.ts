// Analytics aggregation. Pure functions over recorded sessions / interactions: no data in, no metrics out.
import type { DataSource } from './telemetry'

export type InputMode = 'VISION' | 'NEURAL'
export type Outcome = 'success' | 'incorrect' | 'false'

export interface SessionRecord {
  id: string
  mode: InputMode
  startedAt: number // ms since epoch
  durationS: number
  source: DataSource
  calibrationErrorPx: number | null // vision only
  cursorStabilityPx: number // dispersion while holding still
  offlineAccuracy: number | null // 0-1, neural validation set; kept separate from online performance
}

export interface InteractionRecord {
  sessionId: string
  timestamp: number
  kind: string
  outcome: Outcome
  latencyMs: number
  acquisitionMs: number | null
}

export interface ModeSummary {
  sessions: number
  interactions: number
  successRate: number | null
  medianLatencyMs: number | null
  medianAcquisitionMs: number | null
}

export interface Summary {
  sessions: number
  interactions: number
  byOutcome: Record<Outcome, number>
  byKind: Record<string, number>
  medianLatencyMs: number | null
  medianAcquisitionMs: number | null
  meanStabilityPx: number | null
  meanCalibrationErrorPx: number | null
  /** Neural only. Offline = held-out validation windows; online = live control success. Never merged. */
  offlineEegAccuracy: number | null
  onlineEegSuccessRate: number | null
  perMode: Record<InputMode, ModeSummary>
}

export function median(xs: number[]): number | null {
  if (xs.length === 0) return null
  const s = [...xs].sort((a, b) => a - b)
  const m = Math.floor(s.length / 2)
  return s.length % 2 ? s[m]! : (s[m - 1]! + s[m]!) / 2
}

export function mean(xs: number[]): number | null {
  return xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : null
}

function modeSummary(mode: InputMode, sessions: SessionRecord[], events: InteractionRecord[]): ModeSummary {
  const ids = new Set(sessions.filter((s) => s.mode === mode).map((s) => s.id))
  const ev = events.filter((e) => ids.has(e.sessionId))
  return {
    sessions: ids.size,
    interactions: ev.length,
    successRate: ev.length ? ev.filter((e) => e.outcome === 'success').length / ev.length : null,
    medianLatencyMs: median(ev.map((e) => e.latencyMs)),
    medianAcquisitionMs: median(ev.flatMap((e) => (e.acquisitionMs === null ? [] : [e.acquisitionMs]))),
  }
}

/** Returns null when there are no sessions, so the UI shows an empty state instead of zeros. */
export function summarize(sessions: SessionRecord[], events: InteractionRecord[]): Summary | null {
  if (sessions.length === 0) return null
  const byOutcome: Record<Outcome, number> = { success: 0, incorrect: 0, false: 0 }
  const byKind: Record<string, number> = {}
  for (const e of events) {
    byOutcome[e.outcome] += 1
    byKind[e.kind] = (byKind[e.kind] ?? 0) + 1
  }
  const neural = modeSummary('NEURAL', sessions, events)
  return {
    sessions: sessions.length,
    interactions: events.length,
    byOutcome,
    byKind,
    medianLatencyMs: median(events.map((e) => e.latencyMs)),
    medianAcquisitionMs: median(events.flatMap((e) => (e.acquisitionMs === null ? [] : [e.acquisitionMs]))),
    meanStabilityPx: mean(sessions.map((s) => s.cursorStabilityPx)),
    meanCalibrationErrorPx: mean(sessions.flatMap((s) => (s.calibrationErrorPx === null ? [] : [s.calibrationErrorPx]))),
    offlineEegAccuracy: mean(sessions.flatMap((s) => (s.offlineAccuracy === null ? [] : [s.offlineAccuracy]))),
    onlineEegSuccessRate: neural.successRate,
    perMode: { VISION: modeSummary('VISION', sessions, events), NEURAL: neural },
  }
}

type Cell = string | number | null

export function toCsv(rows: Record<string, Cell>[]): string {
  if (rows.length === 0) return ''
  const headers = Object.keys(rows[0]!)
  const esc = (v: Cell) => {
    const s = v === null ? '' : String(v)
    return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s
  }
  return [headers.join(','), ...rows.map((r) => headers.map((h) => esc(r[h] ?? null)).join(','))].join('\n')
}

export function sessionRows(sessions: SessionRecord[]): Record<string, Cell>[] {
  return sessions.map((s) => ({
    session_id: s.id,
    data_source: s.source,
    mode: s.mode,
    started_at_iso: new Date(s.startedAt).toISOString(),
    duration_s: s.durationS,
    calibration_error_px: s.calibrationErrorPx,
    cursor_stability_px: s.cursorStabilityPx,
    offline_accuracy: s.offlineAccuracy,
  }))
}

export function interactionRows(
  events: InteractionRecord[],
  sourceById: Map<string, DataSource>,
): Record<string, Cell>[] {
  return events.map((e) => ({
    session_id: e.sessionId,
    data_source: sourceById.get(e.sessionId) ?? null,
    timestamp_ms: e.timestamp,
    kind: e.kind,
    outcome: e.outcome,
    latency_ms: e.latencyMs,
    acquisition_ms: e.acquisitionMs,
  }))
}
