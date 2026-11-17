// SSVEP stimulus planning: validate flicker frequencies against the display refresh rate.
// A square-wave flicker only realises frequency f exactly if refresh / f is a whole number of frames.

export interface SsvepTarget {
  id: string
  label: string
  hz: number
}

// Select is configurable; 6.67 Hz (9 frames at 60 Hz) avoids landing on a 2nd harmonic of the other four.
export const DEFAULT_TARGETS: SsvepTarget[] = [
  { id: 'up', label: 'Up', hz: 8 },
  { id: 'down', label: 'Down', hz: 10 },
  { id: 'left', label: 'Left', hz: 12 },
  { id: 'right', label: 'Right', hz: 15 },
  { id: 'select', label: 'Select', hz: 6.67 },
]

export interface FrameCheck {
  hz: number
  framesPerCycle: number
  compatible: boolean
  /** Even frame count per cycle gives an exact 50% duty cycle. */
  balanced: boolean
  /** Frequency actually produced when rounded to a whole number of frames. */
  realizedHz: number
  /** Nearest frame-compatible frequencies, even frame counts first on ties. */
  alternatives: number[]
}

const round2 = (n: number) => Math.round(n * 100) / 100

export function checkFrequency(hz: number, refreshHz: number, toleranceFrames = 0.05): FrameCheck {
  const framesPerCycle = refreshHz / hz
  const n = Math.max(2, Math.round(framesPerCycle))
  const compatible = Math.abs(framesPerCycle - n) <= toleranceFrames
  const candidates = [n - 2, n - 1, n, n + 1, n + 2]
    .filter((k) => k >= 2)
    .map((k) => ({ k, f: refreshHz / k }))
    .sort((a, b) => Math.abs(a.f - hz) - Math.abs(b.f - hz) || (a.k % 2) - (b.k % 2))
  return {
    hz,
    framesPerCycle: round2(framesPerCycle),
    compatible,
    balanced: compatible && n % 2 === 0,
    realizedHz: round2(refreshHz / n),
    alternatives: candidates.slice(0, 3).map((c) => round2(c.f)),
  }
}

export interface HarmonicConflict {
  a: string
  b: string
  harmonic: number
}

/** Pairs where a harmonic (2nd..maxHarmonic) of one target lands within tolHz of another target. */
export function harmonicConflicts(targets: SsvepTarget[], maxHarmonic = 3, tolHz = 0.3): HarmonicConflict[] {
  const out: HarmonicConflict[] = []
  for (const a of targets) {
    for (const b of targets) {
      if (a.id === b.id) continue
      for (let h = 2; h <= maxHarmonic; h++) {
        if (Math.abs(a.hz * h - b.hz) <= tolHz) out.push({ a: a.id, b: b.id, harmonic: h })
      }
    }
  }
  return out
}
