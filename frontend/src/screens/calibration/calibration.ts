export interface CalibrationTimings {
  countdownMs: number
  settleMs: number
  samples: number
  maxRetries: number
}

export const DEFAULT_TIMINGS: CalibrationTimings = { countdownMs: 3000, settleMs: 1000, samples: 25, maxRetries: 2 }

/** Honest verdict from the held-out error as a fraction of screen width (a heuristic, not a standard). */
export function verdict(errorPx: number, screenW: number): { label: 'good' | 'fair' | 'poor'; text: string } {
  const frac = errorPx / screenW
  if (frac < 0.05) return { label: 'good', text: 'Good: the cursor should land close to where you look.' }
  if (frac < 0.12) return { label: 'fair', text: 'Fair: usable for large targets, expect some drift.' }
  return {
    label: 'poor',
    text: 'Poor: the cursor will be inaccurate. Recalibrate: sit about 50 cm away, face a light source, keep your head still and follow each dot with your eyes only.',
  }
}
