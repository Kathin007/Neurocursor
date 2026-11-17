// DEMO_DATA: generated sessions/interactions used only to preview the Analytics screen in M2.
// Real analytics (M5) read recorded events from SQLite; this file must never feed them.
import type { InteractionRecord, Outcome, SessionRecord } from '@/lib/analytics'

function mulberry32(seed: number): () => number {
  let a = seed
  return () => {
    a = (a + 0x6d2b79f5) | 0
    let t = Math.imul(a ^ (a >>> 15), 1 | a)
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

const DAY = 86_400_000
const BASE = Date.UTC(2026, 10, 3, 9, 0, 0)

export function buildDemoAnalytics(): { sessions: SessionRecord[]; interactions: InteractionRecord[] } {
  const rand = mulberry32(42)
  const sessions: SessionRecord[] = []
  const interactions: InteractionRecord[] = []
  const plan: Array<[SessionRecord['mode'], number]> = [
    ['VISION', 0], ['NEURAL', 0], ['VISION', 1], ['NEURAL', 2], ['VISION', 3], ['NEURAL', 4],
  ]
  plan.forEach(([mode, day], i) => {
    const id = `demo-${i + 1}`
    sessions.push({
      id, mode, source: 'DEMO_DATA', startedAt: BASE + day * DAY, durationS: 420 + Math.round(rand() * 300),
      calibrationErrorPx: mode === 'VISION' ? Math.round(55 - i * 4 + rand() * 10) : null,
      cursorStabilityPx: Math.round((mode === 'VISION' ? 6 : 11) * (0.8 + rand() * 0.5) * 10) / 10,
      offlineAccuracy: mode === 'NEURAL' ? Math.round((0.78 + rand() * 0.12) * 100) / 100 : null,
    })
    const n = 24 + Math.floor(rand() * 10)
    for (let k = 0; k < n; k++) {
      const r = rand()
      const good = mode === 'VISION' ? 0.82 : 0.68
      const outcome: Outcome = r < good ? 'success' : r < good + (1 - good) * 0.65 ? 'incorrect' : 'false'
      interactions.push({
        sessionId: id, timestamp: BASE + day * DAY + k * 9000,
        kind: mode === 'VISION' ? (rand() < 0.25 ? 'BLINK_CLICK' : 'DWELL_SELECT') : 'SSVEP_COMMAND',
        outcome,
        latencyMs: Math.round(mode === 'VISION' ? 90 + rand() * 120 : 900 + rand() * 900),
        acquisitionMs: outcome === 'false' ? null : Math.round(mode === 'VISION' ? 800 + rand() * 700 : 2400 + rand() * 2200),
      })
    }
  })
  return { sessions, interactions }
}
