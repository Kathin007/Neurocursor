// Thin, failure-tolerant wrappers around the Fullscreen API (absent in jsdom, refused without a user gesture, etc.).

export async function enterFullscreen(el: Element = document.documentElement): Promise<boolean> {
  try {
    if (document.fullscreenElement) return true
    if (typeof el.requestFullscreen !== 'function') return false
    await el.requestFullscreen()
    return true
  } catch {
    return false
  }
}

export function exitFullscreen(): void {
  try {
    if (document.fullscreenElement && typeof document.exitFullscreen === 'function') void document.exitFullscreen()
  } catch {
    /* nothing to do */
  }
}
