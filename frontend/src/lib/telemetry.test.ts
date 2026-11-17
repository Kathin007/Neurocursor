import { describe, expect, it, vi } from 'vitest'
import { TelemetryClient, telemetryUrl } from './telemetry'

class FakeSocket {
  sent: string[] = []
  onopen: (() => void) | null = null
  onclose: (() => void) | null = null
  onmessage: ((m: { data: string }) => void) | null = null
  send(data: string) {
    this.sent.push(data)
  }
  close() {
    this.onclose?.()
  }
  serverSend(obj: unknown) {
    this.onmessage?.({ data: JSON.stringify(obj) })
  }
}

function setup() {
  const sock = new FakeSocket()
  let t = 100
  const client = new TelemetryClient('ws://x/ws/telemetry', () => sock as unknown as WebSocket, () => t)
  client.connect()
  sock.onopen?.()
  return { sock, client, advance: (ms: number) => (t += ms) }
}

describe('telemetryUrl', () => {
  it('derives ws/wss from the page protocol', () => {
    expect(telemetryUrl({ protocol: 'http:', host: 'localhost:5173' })).toBe('ws://localhost:5173/ws/telemetry')
    expect(telemetryUrl({ protocol: 'https:', host: 'a.b' })).toBe('wss://a.b/ws/telemetry')
  })
})

describe('TelemetryClient', () => {
  it('reports state transitions', () => {
    const sock = new FakeSocket()
    const client = new TelemetryClient('ws://x', () => sock as unknown as WebSocket)
    const states: string[] = []
    client.onState((s) => states.push(s))
    client.connect()
    sock.onopen?.()
    sock.close()
    expect(states).toEqual(['connecting', 'open', 'closed'])
  })

  it('ping resolves with the measured round-trip when the matching pong arrives', async () => {
    const { sock, client, advance } = setup()
    const p = client.ping()
    const sent = JSON.parse(sock.sent[0]!) as { type: string; id: number }
    expect(sent.type).toBe('ping')
    advance(12)
    sock.serverSend({
      type: 'system_log', timestamp: 1, source: null,
      payload: { message: 'pong', ping_id: sent.id },
    })
    await expect(p).resolves.toBe(12)
  })

  it('ignores a pong for an unknown id and forwards events to listeners', () => {
    const { sock, client } = setup()
    const seen = vi.fn()
    client.onEvent(seen)
    sock.serverSend({ type: 'system_log', timestamp: 1, source: null, payload: { message: 'pong', ping_id: 999 } })
    expect(seen).toHaveBeenCalledTimes(1)
  })

  it('ping rejects when not connected', async () => {
    const client = new TelemetryClient('ws://x', () => new FakeSocket() as unknown as WebSocket)
    await expect(client.ping()).rejects.toThrow('not connected')
  })

  it('ping rejects on timeout', async () => {
    vi.useFakeTimers()
    try {
      const { client } = setup()
      const p = client.ping()
      const assertion = expect(p).rejects.toThrow('timed out')
      await vi.advanceTimersByTimeAsync(3100)
      await assertion
    } finally {
      vi.useRealTimers()
    }
  })

  it('survives malformed server messages', () => {
    const { sock, client } = setup()
    const seen = vi.fn()
    client.onEvent(seen)
    sock.onmessage?.({ data: 'not json' })
    expect(seen).not.toHaveBeenCalled()
  })
})
