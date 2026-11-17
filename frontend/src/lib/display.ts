// Measures the real display refresh rate from requestAnimationFrame timestamps.

type Raf = (cb: (t: number) => void) => number
type Caf = (id: number) => void

export function medianRefreshHz(timestamps: number[]): number | null {
  const deltas = timestamps.slice(1).map((t, i) => t - timestamps[i]!).filter((d) => d > 0)
  if (deltas.length < 5) return null
  deltas.sort((a, b) => a - b)
  const median = deltas[Math.floor(deltas.length / 2)]!
  return Math.round((1000 / median) * 10) / 10
}

/** Resolves with the measured Hz, or null if frames did not arrive (hidden tab, no rAF). */
export function measureRefreshRate(
  frames = 40,
  timeoutMs = 3000,
  raf: Raf = (cb) => requestAnimationFrame(cb),
  caf: Caf = (id) => cancelAnimationFrame(id),
): Promise<number | null> {
  return new Promise((resolve) => {
    const stamps: number[] = []
    let id = 0
    const timer = setTimeout(() => {
      caf(id)
      resolve(null)
    }, timeoutMs)
    const tick = (t: number) => {
      stamps.push(t)
      if (stamps.length >= frames) {
        clearTimeout(timer)
        resolve(medianRefreshHz(stamps))
      } else {
        id = raf(tick)
      }
    }
    id = raf(tick)
  })
}

let cached: Promise<number | null> | null = null

/** Measured once per page load and shared. */
export function getRefreshRate(): Promise<number | null> {
  cached ??= measureRefreshRate()
  return cached
}

export function resetRefreshRateCache(): void {
  cached = null
}
