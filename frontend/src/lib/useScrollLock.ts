import { useEffect } from 'react'

/** Hides the page scrollbar behind a full-viewport overlay for as long as it is mounted. */
export function useScrollLock(): void {
  useEffect(() => {
    const previous = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      document.body.style.overflow = previous
    }
  }, [])
}
