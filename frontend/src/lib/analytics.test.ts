import { describe, expect, it } from 'vitest'
import { interactionRows, median, sessionRows, summarize, toCsv, type InteractionRecord, type SessionRecord } from './analytics'

const s = (id: string, mode: SessionRecord['mode'], extra: Partial<SessionRecord> = {}): SessionRecord => ({
  id, mode, startedAt: 0, durationS: 60, source: 'DEMO_DATA',
  calibrationErrorPx: null, cursorStabilityPx: 4, offlineAccuracy: null, ...extra,
})
const e = (sessionId: string, outcome: InteractionRecord['outcome'], latencyMs: number, acq: number | null = null): InteractionRecord => ({
  sessionId, timestamp: 0, kind: 'CLICK', outcome, latencyMs, acquisitionMs: acq,
})

describe('summarize', () => {
  it('returns null (not zeros) when there are no sessions', () => {
    expect(summarize([], [])).toBeNull()
  })

  it('computes counts, medians and per-mode splits from the given events only', () => {
    const sessions = [s('v', 'VISION', { calibrationErrorPx: 30 }), s('n', 'NEURAL', { offlineAccuracy: 0.8 })]
    const events = [e('v', 'success', 100, 900), e('v', 'incorrect', 300, 1100), e('n', 'success', 700, 2000), e('n', 'false', 900)]
    const sum = summarize(sessions, events)!
    expect(sum.byOutcome).toEqual({ success: 2, incorrect: 1, false: 1 })
    expect(sum.medianLatencyMs).toBe(500)
    expect(sum.medianAcquisitionMs).toBe(1100)
    expect(sum.meanCalibrationErrorPx).toBe(30)
    expect(sum.perMode.VISION.successRate).toBe(0.5)
    expect(sum.perMode.NEURAL.medianLatencyMs).toBe(800)
  })

  it('keeps offline EEG accuracy separate from online success rate', () => {
    const sum = summarize([s('n', 'NEURAL', { offlineAccuracy: 0.9 })], [e('n', 'success', 1), e('n', 'false', 1)])!
    expect(sum.offlineEegAccuracy).toBe(0.9)
    expect(sum.onlineEegSuccessRate).toBe(0.5)
  })

  it('has null EEG numbers when there are no neural sessions', () => {
    const sum = summarize([s('v', 'VISION')], [e('v', 'success', 1)])!
    expect(sum.offlineEegAccuracy).toBeNull()
    expect(sum.onlineEegSuccessRate).toBeNull()
  })
})

describe('median', () => {
  it('handles empty, odd and even lengths', () => {
    expect(median([])).toBeNull()
    expect(median([3, 1, 2])).toBe(2)
    expect(median([1, 2, 3, 4])).toBe(2.5)
  })
})

describe('csv', () => {
  it('escapes commas, quotes and newlines and keeps the data_source column', () => {
    const csv = toCsv([{ a: 'x,y', b: 'say "hi"', c: null, data_source: 'DEMO_DATA' }])
    expect(csv).toBe('a,b,c,data_source\n"x,y","say ""hi""",,DEMO_DATA')
  })

  it('returns an empty string for no rows', () => {
    expect(toCsv([])).toBe('')
  })

  it('labels every session and event row with its source', () => {
    const sessions = [s('v', 'VISION')]
    const rows = sessionRows(sessions)
    expect(rows[0]!.data_source).toBe('DEMO_DATA')
    const ev = interactionRows([e('v', 'success', 1)], new Map(sessions.map((x) => [x.id, x.source])))
    expect(ev[0]!.data_source).toBe('DEMO_DATA')
  })
})
