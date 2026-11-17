// Real capability probes of the browser the UI runs in. None of them opens the camera.

export interface CameraProbe {
  /** null when the browser exposes no media-device API at all. */
  count: number | null
}

export async function probeCameras(nav: Navigator = navigator): Promise<CameraProbe> {
  if (!nav.mediaDevices?.enumerateDevices) return { count: null }
  try {
    const devices = await nav.mediaDevices.enumerateDevices()
    return { count: devices.filter((d) => d.kind === 'videoinput').length }
  } catch {
    return { count: null }
  }
}

export type PermissionProbe = 'granted' | 'prompt' | 'denied' | 'unknown'

export async function probeCameraPermission(nav: Navigator = navigator): Promise<PermissionProbe> {
  try {
    const status = await nav.permissions?.query({ name: 'camera' as PermissionName })
    return status ? status.state : 'unknown'
  } catch {
    return 'unknown'
  }
}

export function probeWebGL(doc: Document = document): boolean {
  try {
    const canvas = doc.createElement('canvas')
    return Boolean(canvas.getContext('webgl2') ?? canvas.getContext('webgl'))
  } catch {
    return false
  }
}

export function prefersReducedMotion(win: Window = window): boolean {
  return Boolean(win.matchMedia?.('(prefers-reduced-motion: reduce)').matches)
}
