// DEMO_DATA: scripted EEG-like signal and decisions (real engine lands in M4).
// Deterministic functions of time; nothing here comes from a headset.
import { DEFAULT_TARGETS } from '@/lib/ssvep'

export const DEMO_FS = 250
export const DEMO_CHANNELS = ['O1', 'Oz', 'O2', 'PO3', 'POz', 'PO4', 'Pz', 'Cz'] as const

/** Cheap deterministic noise in [-1, 1]. */
function noise(i: number, ch: number): number {
  const x = Math.sin(i * 12.9898 + ch * 78.233) * 43758.5453
  return (x - Math.floor(x)) * 2 - 1
}

export const DECISION_PERIOD_MS = 2500

export interface DemoDecision {
  index: number
  targetId: string
  hz: number
  confidence: number
  accepted: boolean
  reason: string
}

export const DEMO_CONFIDENCE_THRESHOLD = 0.65

export function demoDecision(index: number): DemoDecision {
  const target = DEFAULT_TARGETS[(index * 3 + 1) % DEFAULT_TARGETS.length]!
  const confidence = Math.round((0.38 + 0.6 * Math.abs(noise(index, 3))) * 100) / 100
  const accepted = confidence >= DEMO_CONFIDENCE_THRESHOLD
  return {
    index,
    targetId: target.id,
    hz: target.hz,
    confidence,
    accepted,
    reason: accepted ? 'confidence above threshold, consecutive windows agreed' : 'confidence below threshold',
  }
}

export function demoHistory(t: number, count = 8): DemoDecision[] {
  const current = Math.floor(t / DECISION_PERIOD_MS)
  return Array.from({ length: Math.min(count, current + 1) }, (_, i) => demoDecision(current - i))
}

/** One channel of synthetic signal ending at time tMs: alpha + attended-target SSVEP + noise (microvolts-ish). */
export function demoWaveform(tMs: number, channel: number, seconds = 2): number[] {
  const n = Math.floor(seconds * DEMO_FS)
  const startIdx = Math.floor((tMs / 1000) * DEMO_FS) - n
  const target = demoDecision(Math.floor(tMs / DECISION_PERIOD_MS)) // the waveform carries the attended target's frequency
  const gain = channel < 3 ? 1 : channel < 6 ? 0.6 : 0.15 // occipital channels carry the SSVEP
  return Array.from({ length: n }, (_, k) => {
    const time = (startIdx + k) / DEMO_FS
    return (
      6 * Math.sin(2 * Math.PI * 10 * time + channel) * 0.5 +
      4 * gain * Math.sin(2 * Math.PI * target.hz * time) +
      2.5 * gain * Math.sin(2 * Math.PI * target.hz * 2 * time) +
      5 * noise(startIdx + k, channel)
    )
  })
}

/** Power spectrum by direct DFT of a (short) window; fine for 0-30 Hz at demo rates. */
export function dftSpectrum(signal: number[], fs = DEMO_FS, maxHz = 30, stepHz = 0.5): { hz: number; power: number }[] {
  const n = signal.length
  const out: { hz: number; power: number }[] = []
  for (let f = 1; f <= maxHz; f += stepHz) {
    let re = 0
    let im = 0
    for (let k = 0; k < n; k++) {
      const w = 0.5 - 0.5 * Math.cos((2 * Math.PI * k) / (n - 1)) // Hann
      const a = (2 * Math.PI * f * k) / fs
      re += signal[k]! * w * Math.cos(a)
      im -= signal[k]! * w * Math.sin(a)
    }
    out.push({ hz: f, power: (re * re + im * im) / (n * n) })
  }
  return out
}

/** Per-channel contact quality 0-1 for the demo (not measured impedance). */
export const DEMO_SIGNAL_QUALITY: ReadonlyArray<number> = [0.94, 0.97, 0.91, 0.82, 0.88, 0.79, 0.62, 0.41]
