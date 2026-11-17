import { describe, expect, it } from 'vitest'
import { probeCameraPermission, probeCameras, probeWebGL } from './browserProbes'

const nav = (o: unknown) => o as Navigator

describe('browser probes', () => {
  it('counts only videoinput devices', async () => {
    const n = nav({
      mediaDevices: { enumerateDevices: async () => [{ kind: 'videoinput' }, { kind: 'audioinput' }, { kind: 'videoinput' }] },
    })
    expect(await probeCameras(n)).toEqual({ count: 2 })
  })

  it('reports null when the media API is missing or throws', async () => {
    expect(await probeCameras(nav({}))).toEqual({ count: null })
    const n = nav({ mediaDevices: { enumerateDevices: async () => { throw new Error('x') } } })
    expect(await probeCameras(n)).toEqual({ count: null })
  })

  it('reads camera permission state without prompting', async () => {
    expect(await probeCameraPermission(nav({ permissions: { query: async () => ({ state: 'denied' }) } }))).toBe('denied')
    expect(await probeCameraPermission(nav({}))).toBe('unknown')
  })

  it('probeWebGL is false when no context is available (jsdom)', () => {
    expect(probeWebGL()).toBe(false)
  })
})
