import { describe, expect, it } from 'vitest'
import { buildDemoAnalytics } from './analytics'
import { DEMO_FS, demoDecision, demoHistory, dftSpectrum } from './neural'
import { demoVision } from './vision'

describe('demo generators are deterministic and bounded', () => {
  it('demoVision is a pure function of time and stays inside the unit square', () => {
    expect(demoVision(1234)).toEqual(demoVision(1234))
    for (let t = 0; t < 60_000; t += 137) {
      const d = demoVision(t)
      for (const v of [d.gaze.x, d.gaze.y, d.cursor.x, d.cursor.y]) {
        expect(v).toBeGreaterThanOrEqual(0)
        expect(v).toBeLessThanOrEqual(1)
      }
    }
  })

  it('demo analytics: every session is DEMO_DATA and repeated builds are identical', () => {
    const a = buildDemoAnalytics()
    expect(a.sessions.every((s) => s.source === 'DEMO_DATA')).toBe(true)
    expect(buildDemoAnalytics()).toEqual(a)
  })

  it('demo history only contains accepted/rejected decisions consistent with confidence', () => {
    for (const h of demoHistory(60_000, 8)) {
      expect(h.accepted).toBe(h.confidence >= 0.65)
      expect(demoDecision(h.index)).toEqual(h)
    }
  })
})

describe('dftSpectrum', () => {
  it('peaks at the frequency of an injected 12 Hz sine (ground truth)', () => {
    const sig = Array.from({ length: DEMO_FS }, (_, i) => Math.sin((2 * Math.PI * 12 * i) / DEMO_FS))
    const spec = dftSpectrum(sig, DEMO_FS, 30, 0.5)
    const peak = spec.reduce((a, b) => (b.power > a.power ? b : a))
    expect(peak.hz).toBe(12)
  })
})
