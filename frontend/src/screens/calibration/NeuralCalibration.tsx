import { useEffect, useState } from 'react'
import { Button } from '@/components/ui/button'
import { Meter, Panel } from '@/design/Panel'
import { DEMO_CHANNELS, DEMO_SIGNAL_QUALITY } from '@/demo/neural'
import { DEFAULT_TARGETS, type SsvepTarget } from '@/lib/ssvep'
import { FrequencyConfig } from './FrequencyConfig'

// Scripted confusion matrix for the validation panel (rows = true, cols = predicted). Not a measurement.
const DEMO_CONFUSION = [
  [18, 1, 0, 1, 0],
  [2, 16, 1, 0, 1],
  [0, 1, 17, 2, 0],
  [1, 0, 2, 16, 1],
  [0, 1, 0, 1, 18],
]

export function NeuralCalibration() {
  const [targets, setTargets] = useState<SsvepTarget[]>(DEFAULT_TARGETS)
  const [connected, setConnected] = useState(false)
  const [baseline, setBaseline] = useState(-1) // -1 idle, 0..100

  useEffect(() => {
    if (baseline < 0 || baseline >= 100) return
    const id = setTimeout(() => setBaseline((b) => Math.min(100, b + 10)), 150)
    return () => clearTimeout(id)
  }, [baseline])

  const total = DEMO_CONFUSION.flat().reduce((a, b) => a + b, 0)
  const correct = DEMO_CONFUSION.reduce((a, row, i) => a + (row[i] ?? 0), 0)

  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <div className="space-y-4">
        <Panel title="Device" source="DEMO_DATA" active={connected}>
          <p className="text-sm">
            {connected ? 'Demo device connected (placeholder)' : 'No device connected'}
          </p>
          <p className="mt-1 text-xs text-text2">
            Real options arrive in M4: BrainFlow synthetic board (SYNTHETIC_EEG), recorded playback (RECORDED_EEG), headset (REAL_EEG).
          </p>
          <Button className="mt-3" onClick={() => setConnected((c) => !c)}>
            {connected ? 'Disconnect demo' : 'Connect demo'}
          </Button>
        </Panel>

        <Panel title="Channel detection + signal quality" source="DEMO_DATA">
          {connected ? (
            <ul className="space-y-2">
              {DEMO_CHANNELS.map((ch, i) => {
                const q = DEMO_SIGNAL_QUALITY[i] ?? 0
                return (
                  <li key={ch} className="grid grid-cols-[3rem_1fr_3rem] items-center gap-3 text-sm">
                    <span className="font-mono">{ch}</span>
                    <Meter value={q} label={`${ch} signal quality`} tone={q < 0.5 ? 'bad' : q < 0.75 ? 'warn' : 'ok'} />
                    <span className="text-right font-mono text-xs text-text2">{Math.round(q * 100)}%</span>
                  </li>
                )
              })}
            </ul>
          ) : (
            <p className="text-sm text-text2">Connect a device to detect channels.</p>
          )}
        </Panel>

        <Panel title="Baseline" source="DEMO_DATA">
          <div className="flex items-center gap-3">
            <Button variant="secondary" disabled={!connected || (baseline >= 0 && baseline < 100)} onClick={() => setBaseline(0)}>
              {baseline === 100 ? 'Re-record baseline' : 'Record baseline'}
            </Button>
            <div className="flex-1">
              <Meter value={Math.max(0, baseline) / 100} label="Baseline progress" />
            </div>
          </div>
        </Panel>
      </div>

      <div className="space-y-4">
        <FrequencyConfig targets={targets} onChange={setTargets} />

        <Panel title="Classifier validation (offline)" source="DEMO_DATA">
          <table className="w-full text-center font-mono text-xs" aria-label="Confusion matrix">
            <thead>
              <tr>
                <th />
                {targets.map((t) => (
                  <th key={t.id} className="pb-1 text-text2">{t.label}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {DEMO_CONFUSION.map((row, i) => (
                <tr key={i}>
                  <th className="pr-2 text-right text-text2">{targets[i]?.label}</th>
                  {row.map((n, j) => (
                    <td key={j} className={i === j ? 'bg-violet/25 text-text' : 'text-text2'}>{n}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
          <p className="mt-3 font-mono text-sm">
            Offline accuracy: <span className="text-warning">{((correct / total) * 100).toFixed(1)}% (DEMO)</span>
          </p>
          <p className="mt-1 text-xs text-text2">Offline validation is separate from online control performance, which is reported only from live sessions.</p>
        </Panel>
      </div>
    </div>
  )
}
