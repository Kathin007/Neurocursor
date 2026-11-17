import { lazy, Suspense, useEffect, useState } from 'react'
import { prefersReducedMotion, probeWebGL } from '@/lib/browserProbes'
import { measureRefreshRate } from '@/lib/display'

const NeuralScene = lazy(() => import('./NeuralScene'))

const MIN_FPS = 45

export type BackgroundMode = 'animated' | 'static'

/** Decides up front (WebGL, reduced motion) and again at runtime (measured frame rate) whether to animate. */
export function AdaptiveBackground({ onModeChange }: { onModeChange?: (m: BackgroundMode) => void }) {
  const [mode, setMode] = useState<BackgroundMode>(() => (probeWebGL() && !prefersReducedMotion() ? 'animated' : 'static'))

  useEffect(() => onModeChange?.(mode), [mode, onModeChange])

  useEffect(() => {
    if (mode !== 'animated') return
    let live = true
    // Frame rate measured while the scene runs; below MIN_FPS we drop to the static background.
    void measureRefreshRate(90, 6000).then((fps) => {
      if (live && fps !== null && fps < MIN_FPS) setMode('static')
    })
    return () => {
      live = false
    }
  }, [mode])

  return (
    <div aria-hidden data-testid="background" data-mode={mode} className="pointer-events-none fixed inset-0 -z-10">
      {mode === 'animated' ? (
        <>
          <Suspense fallback={null}>
            <NeuralScene />
          </Suspense>
          {/* Vignette keeps text and panels readable over the network. */}
          <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_50%_45%,rgb(9_11_22/0.7),transparent_75%)]" />
        </>
      ) : (
        <div className="size-full bg-[radial-gradient(circle_at_70%_30%,rgb(139_92_246/0.22),transparent_45%),radial-gradient(circle_at_20%_80%,rgb(34_211_238/0.1),transparent_40%)]" />
      )}
    </div>
  )
}
