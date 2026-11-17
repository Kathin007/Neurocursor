import { useMemo, useState } from 'react'
import { CartesianGrid, Line, LineChart, ResponsiveContainer, XAxis, YAxis, Area, AreaChart } from 'recharts'
import { Button } from '@/components/ui/button'
import { Meter, Panel, Readout, StatusDot } from '@/design/Panel'
import {
  DECISION_PERIOD_MS, DEMO_CHANNELS, DEMO_CONFIDENCE_THRESHOLD, DEMO_FS, DEMO_SIGNAL_QUALITY,
  demoDecision, demoHistory, demoWaveform, dftSpectrum,
} from '@/demo/neural'
import { useDemoClock } from '@/lib/hooks'
import { DEFAULT_TARGETS } from '@/lib/ssvep'
import { StimulusTargets } from './StimulusTargets'

const fmtClock = (ms: number) => {
  const s = Math.floor(ms / 1000)
  return `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`
}

export function NeuralControlRoom() {
  const [paused, setPaused] = useState(false)
  const [channel, setChannel] = useState(1)
  const t = useDemoClock(!paused, 100)

  const wave = useMemo(() => demoWaveform(t, channel, 2), [t, channel])
  const waveData = useMemo(() => wave.filter((_, i) => i % 4 === 0).map((v, i) => ({ s: i * 4 / DEMO_FS, v })), [wave])
  const spectrum = useMemo(() => dftSpectrum(wave.slice(-250), DEMO_FS, 30, 0.5), [wave])

  const decision = demoDecision(Math.floor(t / DECISION_PERIOD_MS))
  const history = demoHistory(t)
  const quality = DEMO_SIGNAL_QUALITY[channel] ?? 0

  return (
    <div className="mx-auto max-w-6xl px-6 py-8">
      <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-3xl font-semibold tracking-tight">Neural Control Room</h1>
          <p className="mt-1 text-sm text-text2">EEG SSVEP control. All values below are DEMO_DATA until M4.</p>
        </div>
        <div className="flex items-center gap-3">
          <Readout label="Session" value={fmtClock(t)} />
          <Button variant="secondary" onClick={() => setPaused((p) => !p)}>{paused ? 'Resume' : 'Pause'}</Button>
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-[1.5fr_1fr]">
        <div className="space-y-4">
          <Panel title={`Live waveform · ${DEMO_CHANNELS[channel]}`} source="DEMO_DATA" active={!paused}
            actions={
              <select
                aria-label="Channel select"
                value={channel}
                onChange={(e) => setChannel(Number(e.target.value))}
                className="rounded-md border border-white/12 bg-bg2 px-2 py-1 font-mono text-xs"
              >
                {DEMO_CHANNELS.map((c, i) => <option key={c} value={i}>{c}</option>)}
              </select>
            }>
            <div className="h-44">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={waveData}>
                  <CartesianGrid stroke="rgb(255 255 255 / 0.06)" vertical={false} />
                  <XAxis dataKey="s" hide />
                  <YAxis domain={[-20, 20]} width={32} tick={{ fill: '#94a3b8', fontSize: 10 }} />
                  <Line dataKey="v" stroke="#22d3ee" dot={false} strokeWidth={1.4} isAnimationActive={false} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </Panel>

          <Panel title="Spectrum · 1–30 Hz" source="DEMO_DATA">
            <div className="h-40">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={spectrum}>
                  <CartesianGrid stroke="rgb(255 255 255 / 0.06)" vertical={false} />
                  <XAxis dataKey="hz" tick={{ fill: '#94a3b8', fontSize: 10 }} ticks={[5, 10, 15, 20, 25, 30]} />
                  <YAxis hide />
                  <Area dataKey="power" stroke="#8b5cf6" fill="#8b5cf6" fillOpacity={0.3} isAnimationActive={false} />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </Panel>

          <StimulusTargets targets={DEFAULT_TARGETS} highlightId={decision.targetId} />
        </div>

        <div className="space-y-4">
          <Panel title="Device" source="DEMO_DATA">
            <ul className="space-y-2 text-sm">
              <li className="flex items-center gap-2"><StatusDot state="warn" />No headset: scripted demo signal</li>
              <li className="flex items-center gap-2"><StatusDot state="idle" />{DEMO_CHANNELS.length} channels · {DEMO_FS} Hz (demo)</li>
            </ul>
            <div className="mt-3">
              <div className="label-caps mb-1">Signal quality · {DEMO_CHANNELS[channel]}</div>
              <Meter value={quality} label="Selected channel signal quality" tone={quality < 0.5 ? 'bad' : quality < 0.75 ? 'warn' : 'ok'} />
            </div>
          </Panel>

          <Panel title="Predicted intention" source="DEMO_DATA" active={decision.accepted}>
            <div className="flex items-end justify-between">
              <Readout label="Target" value={DEFAULT_TARGETS.find((x) => x.id === decision.targetId)?.label ?? '—'} unit={`${decision.hz} Hz`} />
              <Readout label="Confidence" value={decision.confidence.toFixed(2)} tone={decision.accepted ? 'ok' : 'warn'} />
            </div>
            <div className="mt-2"><Meter value={decision.confidence} label="Classifier confidence" tone={decision.accepted ? 'ok' : 'warn'} /></div>
            <p className="mt-2 font-mono text-xs text-text2">
              threshold {DEMO_CONFIDENCE_THRESHOLD} · {decision.accepted ? 'would fire' : 'rejected: uncertain window'}
            </p>
          </Panel>

          <Panel title="Command history" source="DEMO_DATA">
            <ol className="space-y-1.5" aria-label="Command history">
              {history.map((h) => (
                <li key={h.index} data-outcome={h.accepted ? 'accepted' : 'rejected'} className="flex items-center justify-between text-sm">
                  <span className="flex items-center gap-2">
                    <StatusDot state={h.accepted ? 'ok' : 'bad'} />
                    {DEFAULT_TARGETS.find((x) => x.id === h.targetId)?.label}
                  </span>
                  <span className="font-mono text-xs text-text2">
                    {h.confidence.toFixed(2)} · {h.accepted ? 'accepted' : 'rejected'}
                  </span>
                </li>
              ))}
            </ol>
          </Panel>
        </div>
      </div>
    </div>
  )
}
