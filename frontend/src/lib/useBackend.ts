import { useCallback, useEffect, useRef, useState } from 'react'
import { fetchSystemStatus, type SystemStatus } from './api'
import { TelemetryClient, telemetryUrl, type ConnectionState, type TelemetryEvent } from './telemetry'

export type RestState = { kind: 'loading' } | { kind: 'ok'; status: SystemStatus } | { kind: 'error'; message: string }

type Listener = (e: TelemetryEvent) => void

export interface Backend {
  rest: RestState
  conn: ConnectionState
  rtt: string
  ping: () => void
  /** Subscribe to every telemetry event; returns the unsubscribe function. Safe to call before the socket exists. */
  subscribe: (fn: Listener) => () => void
  /** Send a client->server WebSocket message; false if the socket is not open. */
  send: (message: Record<string, unknown>) => boolean
}

// Module-level so the effect dependency is stable across renders.
const defaultCreateClient = () => new TelemetryClient(telemetryUrl())

/** Real backend connectivity: REST status + /ws/telemetry state + measured ping RTT + an event fan-out. */
export function useBackend(createClient: () => TelemetryClient = defaultCreateClient): Backend {
  const [rest, setRest] = useState<RestState>({ kind: 'loading' })
  const [conn, setConn] = useState<ConnectionState>('closed')
  const [rtt, setRtt] = useState('not measured')
  const client = useRef<TelemetryClient | null>(null)
  // Owned by the hook, not the client: children subscribe in effects that run before the client is created.
  // Events are deliberately NOT kept in React state here; at ~60 events/s that would re-render the whole app.
  const listeners = useRef(new Set<Listener>())

  useEffect(() => {
    const abort = new AbortController()
    fetchSystemStatus(abort.signal)
      .then((status) => setRest({ kind: 'ok', status }))
      .catch((e: unknown) => {
        if (!abort.signal.aborted) setRest({ kind: 'error', message: String(e) })
      })
    const c = createClient()
    client.current = c
    const offState = c.onState(setConn)
    const offEvent = c.onEvent((e) => listeners.current.forEach((fn) => fn(e)))
    c.connect()
    return () => {
      abort.abort()
      offState()
      offEvent()
      c.close()
      client.current = null
    }
  }, [createClient])

  const ping = useCallback(() => {
    client.current
      ?.ping()
      .then((ms) => setRtt(`${ms.toFixed(1)} ms`))
      .catch((e: unknown) => setRtt(`failed: ${e instanceof Error ? e.message : String(e)}`))
  }, [])

  const subscribe = useCallback((fn: Listener) => {
    listeners.current.add(fn)
    return () => {
      listeners.current.delete(fn)
    }
  }, [])
  const send = useCallback((message: Record<string, unknown>) => client.current?.send(message) ?? false, [])

  return { rest, conn, rtt, ping, subscribe, send }
}
