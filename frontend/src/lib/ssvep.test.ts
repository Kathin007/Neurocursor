import { describe, expect, it } from 'vitest'
import { DEFAULT_TARGETS, checkFrequency, harmonicConflicts } from './ssvep'

describe('checkFrequency', () => {
  it('flags 8 Hz as frame-incompatible at 60 Hz (7.5 frames per cycle)', () => {
    const c = checkFrequency(8, 60)
    expect(c.framesPerCycle).toBe(7.5)
    expect(c.compatible).toBe(false)
    expect(c.alternatives).toContain(7.5)
    expect(c.alternatives).toContain(8.57)
  })

  it('accepts 10, 12 and 15 Hz at 60 Hz', () => {
    for (const hz of [10, 12, 15]) expect(checkFrequency(hz, 60).compatible).toBe(true)
  })

  it('reports balanced duty only for even frame counts', () => {
    expect(checkFrequency(10, 60).balanced).toBe(true) // 6 frames
    expect(checkFrequency(12, 60).compatible).toBe(true)
    expect(checkFrequency(12, 60).balanced).toBe(false) // 5 frames per cycle is odd
  })

  it('validates against the measured rate, not an assumed 60 Hz', () => {
    expect(checkFrequency(12, 144).compatible).toBe(true) // 12 frames
    expect(checkFrequency(15, 144).compatible).toBe(false) // 9.6 frames
  })

  it('accepts the default Select frequency at 60 Hz', () => {
    const select = DEFAULT_TARGETS.find((t) => t.id === 'select')!
    expect(checkFrequency(select.hz, 60).compatible).toBe(true)
  })
})

describe('harmonicConflicts', () => {
  it('finds a 2nd-harmonic collision (6 Hz vs 12 Hz)', () => {
    const t = [
      { id: 'a', label: 'A', hz: 6 },
      { id: 'b', label: 'B', hz: 12 },
    ]
    expect(harmonicConflicts(t)).toEqual([{ a: 'a', b: 'b', harmonic: 2 }])
  })

  it('reports no conflicts for the default target set', () => {
    expect(harmonicConflicts(DEFAULT_TARGETS)).toEqual([])
  })
})
