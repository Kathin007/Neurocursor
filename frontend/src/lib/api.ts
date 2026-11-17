import { backendHttpBase } from './telemetry'

// Mirrors SystemStatus in backend/api/routes_system.py
export interface SystemStatus {
  app: string
  version: string
  milestone: string
  timestamp: number
  uptime_s: number
  python: string
  platform: string
  telemetry: { clients: number; dropped_events: number }
  subsystems: Record<string, string>
}

export async function fetchSystemStatus(signal?: AbortSignal): Promise<SystemStatus> {
  const res = await fetch(`${backendHttpBase()}/api/system/status`, { signal })
  if (!res.ok) throw new Error(`GET /api/system/status -> HTTP ${res.status}`)
  return (await res.json()) as SystemStatus
}
