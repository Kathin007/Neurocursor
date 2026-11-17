import { useCallback, useEffect, useRef, useState } from 'react'
import { ApiError, type VisionApi, type VisionStatus } from '@/lib/visionApi'

const POLL_MS = 2000

export interface VisionSession {
  api: VisionApi
  status: VisionStatus | null
  /** True while the backend is opening the camera and loading the model (first start can take ~20 s). */
  starting: boolean
  error: string | null
  start: () => Promise<void>
  stop: () => Promise<void>
  refresh: () => Promise<void>
  pause: () => Promise<void>
  resume: () => Promise<void>
}

const message = (e: unknown) => (e instanceof ApiError ? e.message : e instanceof Error ? e.message : String(e))

/** The real backend vision session: nothing is assumed, status always comes from GET /api/vision/status. */
export function useVisionSession(api: VisionApi): VisionSession {
  const [status, setStatus] = useState<VisionStatus | null>(null)
  const [starting, setStarting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const alive = useRef(true)

  const refresh = useCallback(async () => {
    try {
      const s = await api.status()
      if (alive.current) {
        setStatus(s)
        setError((prev) => (prev?.startsWith('Backend unreachable') ? null : prev))
      }
    } catch (e) {
      if (alive.current) setError(`Backend unreachable: ${message(e)}`)
    }
  }, [api])

  useEffect(() => {
    alive.current = true
    const first = setTimeout(() => void refresh(), 0) // async, so no setState runs synchronously inside the effect
    const id = setInterval(() => void refresh(), POLL_MS)
    return () => {
      alive.current = false
      clearTimeout(first)
      clearInterval(id)
    }
  }, [refresh])

  const start = useCallback(async () => {
    setStarting(true)
    setError(null)
    try {
      const s = await api.start()
      if (alive.current) setStatus(s)
    } catch (e) {
      // 409 = already running (e.g. page reload): just pick up the real status.
      if (!(e instanceof ApiError && e.status === 409) && alive.current) setError(message(e))
      await refresh()
    } finally {
      if (alive.current) setStarting(false)
    }
  }, [api, refresh])

  const stop = useCallback(async () => {
    try {
      const s = await api.stop()
      if (alive.current) setStatus(s)
    } catch (e) {
      if (alive.current) setError(message(e))
    }
  }, [api])

  const control = useCallback(
    async (action: 'pause' | 'resume') => {
      try {
        await api[action]()
      } catch (e) {
        if (alive.current) setError(message(e))
      }
      await refresh()
    },
    [api, refresh],
  )

  const pause = useCallback(() => control('pause'), [control])
  const resume = useCallback(() => control('resume'), [control])

  return { api, status, starting, error, start, stop, refresh, pause, resume }
}
