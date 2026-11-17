import { motion } from 'motion/react'
import { Button } from '@/components/ui/button'
import { Panel, StatusDot } from '@/design/Panel'
import type { Backend } from '@/lib/useBackend'
import { AdaptiveBackground } from './AdaptiveBackground'
import { useReadiness, type CheckStatus } from './useReadiness'

const DOT: Record<CheckStatus, 'ok' | 'warn' | 'bad' | 'idle'> = { ok: 'ok', warn: 'warn', fail: 'bad', pending: 'idle' }

interface Props {
  backend: Backend
  onEnter: (mode: 'VISION' | 'NEURAL') => void
}

export function WelcomeScreen({ backend, onEnter }: Props) {
  const checks = useReadiness(backend)

  return (
    <div className="relative mx-auto grid min-h-[calc(100vh-4rem)] max-w-6xl items-center gap-10 px-6 py-10 lg:grid-cols-[1.15fr_1fr]">
      <AdaptiveBackground />

      <motion.div initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5 }}>
        <p className="label-caps mb-4">Neural-interface research workstation</p>
        <h1 className="bg-gradient-to-r from-text via-lavender to-cyan bg-clip-text text-6xl font-semibold tracking-tight text-transparent md:text-7xl">
          NEUROCURSOR
        </h1>
        <p className="mt-4 text-xl text-text2">Beyond Touch. Beyond Input.</p>

        <div className="mt-10 grid gap-4 sm:grid-cols-2">
          <button
            onClick={() => onEnter('VISION')}
            className="glass group p-5 text-left transition hover:glow-active focus-visible:glow-active focus-visible:outline-none"
          >
            <span className="label-caps">Mode 01</span>
            <span className="mt-1 block text-2xl font-medium">VISION</span>
            <span className="mt-2 block text-sm text-text2">Webcam gaze control. Computer vision only: this is not a BCI.</span>
          </button>
          <button
            onClick={() => onEnter('NEURAL')}
            className="glass group p-5 text-left transition hover:glow-violet focus-visible:glow-violet focus-visible:outline-none"
          >
            <span className="label-caps">Mode 02</span>
            <span className="mt-1 block text-2xl font-medium">NEURAL</span>
            <span className="mt-2 block text-sm text-text2">EEG SSVEP control. The only mode that is a brain-computer interface.</span>
          </button>
        </div>
      </motion.div>

      <motion.div initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5, delay: 0.1 }}>
        <Panel title="Hardware readiness · measured now">
          <ul className="space-y-3" aria-label="Readiness checks">
            {checks.map((c) => (
              <li key={c.id} className="flex items-start gap-3" data-status={c.status}>
                <span className="mt-1.5">
                  <StatusDot state={DOT[c.status]} />
                </span>
                <div className="min-w-0">
                  <div className="text-sm font-medium">{c.label}</div>
                  <div className="text-xs text-text2">{c.detail}</div>
                </div>
              </li>
            ))}
          </ul>
          <div className="mt-4 flex items-center gap-3 border-t border-white/8 pt-3">
            <Button size="sm" variant="secondary" onClick={backend.ping} disabled={backend.conn !== 'open'}>
              Ping backend
            </Button>
            <span className="font-mono text-xs text-text2">
              round-trip: <span data-testid="rtt">{backend.rtt}</span>
            </span>
          </div>
        </Panel>
      </motion.div>
    </div>
  )
}
