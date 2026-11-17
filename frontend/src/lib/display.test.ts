import { describe, expect, it } from 'vitest'
import { measureRefreshRate, medianRefreshHz } from './display'

describe('medianRefreshHz', () => {
  it('computes 60 Hz from ~16.67 ms frame deltas, ignoring a dropped-frame outlier', () => {
    const t = [0, 16.67, 33.33, 50, 66.67, 133.3, 150, 166.67]
    expect(medianRefreshHz(t)).toBeCloseTo(60, 0)
  })

  it('returns null with too few frames', () => {
    expect(medianRefreshHz([0, 16, 33])).toBeNull()
  })
})

describe('measureRefreshRate', () => {
  it('measures from injected animation frames', async () => {
    let t = 0
    const raf = (cb: (t: number) => void) => {
      t += 1000 / 144
      queueMicrotask(() => cb(t))
      return 1
    }
    expect(await measureRefreshRate(20, 1000, raf, () => {})).toBeCloseTo(144, 0)
  })

  it('resolves null when frames never arrive', async () => {
    expect(await measureRefreshRate(20, 20, () => 1, () => {})).toBeNull()
  })
})
