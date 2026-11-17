// Mirrors backend/api/schemas.py. Camera video never travels on this channel.

export type DataSource =
  | 'REAL_WEBCAM'
  | 'REAL_EEG'
  | 'SYNTHETIC_EEG'
  | 'RECORDED_EEG'
  | 'DEMO_DATA'

export type EventType =
  | 'gaze_update'
  | 'eeg_update'
  | 'cursor_update'
  | 'classification_update'
  | 'device_status'
  | 'interaction_event'
  | 'system_log'

export interface TelemetryEvent {
  type: EventType
  timestamp: number // ms since Unix epoch
  source: DataSource | null
  payload: Record<string, unknown>
}

export type ConnectionState = 'connecting' | 'open' | 'closed'

const PING_TIMEOUT_MS = 3000

/** Same-origin by default (Vite proxy); set VITE_BACKEND_URL for Tauri / non-proxied use. */
export function backendHttpBase(): string {
  return (import.meta.env.VITE_BACKEND_URL as string | undefined) ?? ''
}

export function telemetryUrl(loc: Pick<Location, 'protocol' | 'host'> = window.location): string {
  const base = backendHttpBase()
  if (base) return base.replace(/^http/, 'ws') + '/ws/telemetry'
  return `${loc.protocol === 'https:' ? 'wss' : 'ws'}://${loc.host}/ws/telemetry`
}

interface PendingPing {
  sentAt: number
  resolve: (rttMs: number) => void
  timer: ReturnType<typeof setTimeout>
}

export class TelemetryClient {
  private ws: WebSocket | null = null
  private nextPingId = 1
  private pending = new Map<number, PendingPing>()
  private eventListeners = new Set<(e: TelemetryEvent) => void>()
  private stateListeners = new Set<(s: ConnectionState) => void>()
  state: ConnectionState = 'closed'
  private readonly url: string
  private readonly createSocket: (url: string) => WebSocket
  private readonly now: () => number

  constructor(
    url: string,
    createSocket: (url: string) => WebSocket = (u) => new WebSocket(u),
    now: () => number = () => performance.now(),
  ) {
    this.url = url
    this.createSocket = createSocket
    this.now = now
  }

  onEvent(fn: (e: TelemetryEvent) => void): () => void {
    this.eventListeners.add(fn)
    return () => this.eventListeners.delete(fn)
  }

  onState(fn: (s: ConnectionState) => void): () => void {
    this.stateListeners.add(fn)
    return () => this.stateListeners.delete(fn)
  }

  connect(): void {
    if (this.ws) return
    this.setState('connecting')
    const ws = this.createSocket(this.url)
    this.ws = ws
    ws.onopen = () => this.setState('open')
    ws.onclose = () => {
      this.ws = null
      for (const p of this.pending.values()) clearTimeout(p.timer)
      this.pending.clear()
      this.setState('closed')
    }
    ws.onmessage = (msg: MessageEvent<string>) => this.handleMessage(msg.data)
  }

  close(): void {
    this.ws?.close()
  }

  /** Send a client->server message. Returns false (and sends nothing) if the socket is not open. */
  send(message: Record<string, unknown>): boolean {
    if (!this.ws || this.state !== 'open') return false
    this.ws.send(JSON.stringify(message))
    return true
  }

  /** Round-trip check: resolves with RTT in ms once the server's pong arrives. */
  ping(): Promise<number> {
    const ws = this.ws
    if (!ws || this.state !== 'open') return Promise.reject(new Error('telemetry not connected'))
    const id = this.nextPingId++
    return new Promise<number>((resolve, reject) => {
      const timer = setTimeout(() => {
        this.pending.delete(id)
        reject(new Error('ping timed out'))
      }, PING_TIMEOUT_MS)
      this.pending.set(id, { sentAt: this.now(), resolve, timer })
      ws.send(JSON.stringify({ type: 'ping', id }))
    })
  }

  private setState(s: ConnectionState): void {
    this.state = s
    this.stateListeners.forEach((fn) => fn(s))
  }

  private handleMessage(raw: string): void {
    let event: TelemetryEvent
    try {
      event = JSON.parse(raw) as TelemetryEvent
    } catch {
      return
    }
    if (event.type === 'system_log' && event.payload.message === 'pong') {
      const id = event.payload.ping_id
      const p = typeof id === 'number' ? this.pending.get(id) : undefined
      if (p) {
        clearTimeout(p.timer)
        this.pending.delete(id as number)
        p.resolve(this.now() - p.sentAt)
      }
    }
    this.eventListeners.forEach((fn) => fn(event))
  }
}
