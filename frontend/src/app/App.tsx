import { AnimatePresence, motion } from 'motion/react'
import { useState } from 'react'
import { StatusDot } from '@/design/Panel'
import type { TelemetryClient } from '@/lib/telemetry'
import { useBackend } from '@/lib/useBackend'
import { visionApi as realVisionApi, type VisionApi } from '@/lib/visionApi'
import type { CalibrationTimings } from '@/screens/calibration/calibration'
import { useVisionSession } from '@/screens/vision/useVisionSession'
import { cn } from '@/lib/utils'
import { AnalyticsScreen } from '@/screens/analytics/AnalyticsScreen'
import { CalibrationStudio } from '@/screens/calibration/CalibrationStudio'
import { NeuralControlRoom } from '@/screens/neural/NeuralControlRoom'
import { VisionControlRoom } from '@/screens/vision/VisionControlRoom'
import { WelcomeScreen } from '@/screens/welcome/WelcomeScreen'

type Screen = 'welcome' | 'calibration' | 'vision' | 'neural' | 'analytics'
type Mode = 'VISION' | 'NEURAL'

const NAV: Array<{ id: Screen; label: string }> = [
  { id: 'welcome', label: 'Start' },
  { id: 'calibration', label: 'Calibration' },
  { id: 'vision', label: 'Live' },
  { id: 'neural', label: 'Neural' },
  { id: 'analytics', label: 'Analytics' },
]

interface Props {
  /** Injectable for tests. */
  createClient?: () => TelemetryClient
  visionApi?: VisionApi
  calibrationTimings?: Partial<CalibrationTimings>
}

/** Deep link: #/vision etc. Unknown or missing hash opens the welcome screen. */
function screenFromHash(): Screen {
  const id = window.location.hash.replace(/^#\/?/, '')
  return NAV.some((n) => n.id === id) ? (id as Screen) : 'welcome'
}

export default function App({ createClient, visionApi = realVisionApi, calibrationTimings }: Props) {
  const backend = useBackend(createClient)
  const vision = useVisionSession(visionApi)
  const [screen, setScreenState] = useState<Screen>(screenFromHash)
  const [mode, setMode] = useState<Mode>('VISION')

  const setScreen = (s: Screen) => {
    setScreenState(s)
    window.history.replaceState(null, '', `#/${s}`)
  }

  const enter = (m: Mode) => {
    setMode(m)
    setScreen('calibration')
  }

  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-20 border-b border-white/8 bg-bg/70 backdrop-blur-md">
        <nav aria-label="Screens" className="mx-auto flex max-w-6xl items-center gap-1 px-6 py-3">
          <span className="mr-4 font-mono text-sm font-semibold tracking-[0.2em] text-lavender">NEUROCURSOR</span>
          {NAV.map((n) => (
            <button
              key={n.id}
              onClick={() => setScreen(n.id)}
              aria-current={screen === n.id ? 'page' : undefined}
              className={cn(
                'rounded-md px-3 py-1.5 text-sm transition-colors',
                screen === n.id ? 'bg-violet/20 text-text' : 'text-text2 hover:text-text',
              )}
            >
              {n.label}
            </button>
          ))}
          <span className="ml-auto flex items-center gap-2 font-mono text-xs text-text2" data-testid="backend-chip">
            <StatusDot state={backend.conn === 'open' ? 'ok' : backend.conn === 'connecting' ? 'warn' : 'bad'} />
            backend socket: {backend.conn}
          </span>
        </nav>
      </header>

      <AnimatePresence mode="wait">
        <motion.main
          key={screen}
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.18 }}
        >
          {screen === 'welcome' && <WelcomeScreen backend={backend} onEnter={enter} />}
          {screen === 'calibration' && (
            <CalibrationStudio mode={mode} onModeChange={setMode} backend={backend} session={vision} onGoLive={() => setScreen('vision')} timings={calibrationTimings} />
          )}
          {screen === 'vision' && <VisionControlRoom backend={backend} session={vision} onGoCalibrate={() => setScreen('calibration')} />}
          {screen === 'neural' && <NeuralControlRoom />}
          {screen === 'analytics' && <AnalyticsScreen />}
        </motion.main>
      </AnimatePresence>
    </div>
  )
}
