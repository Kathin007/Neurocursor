import { useEffect, useState } from 'react'
import { getRefreshRate } from './display'

/** Elapsed demo time in ms; only advances while `running`. Drives DEMO_DATA animations. */
export function useDemoClock(running: boolean, intervalMs = 50): number {
  const [t, setT] = useState(0)
  useEffect(() => {
    if (!running) return
    let last = performance.now()
    const id = setInterval(() => {
      const now = performance.now()
      setT((v) => v + (now - last))
      last = now
    }, intervalMs)
    return () => clearInterval(id)
  }, [running, intervalMs])
  return t
}

/** Measured display refresh (Hz): 'pending' while measuring, null if it could not be measured. */
export function useRefreshRate(): number | null | 'pending' {
  const [hz, setHz] = useState<number | null | 'pending'>('pending')
  useEffect(() => {
    let live = true
    void getRefreshRate().then((v) => live && setHz(v))
    return () => {
      live = false
    }
  }, [])
  return hz
}
