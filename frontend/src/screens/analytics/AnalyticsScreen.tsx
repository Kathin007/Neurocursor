import { useMemo, useState } from 'react'
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, XAxis, YAxis } from 'recharts'
import { Button } from '@/components/ui/button'
import { LabeledSwitch } from '@/design/Controls'
import { EmptyState, Panel, Readout } from '@/design/Panel'
import { SourceBadge } from '@/design/SourceBadge'
import { buildDemoAnalytics } from '@/demo/analytics'
import { interactionRows, sessionRows, summarize, toCsv, type InteractionRecord, type SessionRecord } from '@/lib/analytics'
import { downloadText } from '@/lib/download'

const fmt = (v: number | null, digits = 0, unit = '') => (v === null ? '—' : `${v.toFixed(digits)}${unit}`)
const pct = (v: number | null) => (v === null ? '—' : `${(v * 100).toFixed(0)}%`)
const axis = { fill: '#94a3b8', fontSize: 11 }

/**
 * M2: reads the DEMO_DATA dataset only. In M5 the same `summarize` runs over recorded SQLite events.
 * With no sessions it renders an empty state, never zeros.
 */
export function AnalyticsScreen() {
  const [showDemo, setShowDemo] = useState(true)
  const demo = useMemo(() => buildDemoAnalytics(), [])
  const { sessions, interactions } = useMemo<{ sessions: SessionRecord[]; interactions: InteractionRecord[] }>(
    () => (showDemo ? demo : { sessions: [], interactions: [] }),
    [showDemo, demo],
  )
  const sum = useMemo(() => summarize(sessions, interactions), [sessions, interactions])

  const exportCsv = (kind: 'sessions' | 'interactions') => {
    const sources = new Map(sessions.map((s) => [s.id, s.source]))
    const rows = kind === 'sessions' ? sessionRows(sessions) : interactionRows(interactions, sources)
    downloadText(`neurocursor-DEMO_DATA-${kind}.csv`, toCsv(rows))
  }

  return (
    <div className="mx-auto max-w-6xl px-6 py-8">
      <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-3xl font-semibold tracking-tight">Analytics</h1>
          <p className="mt-1 text-sm text-text2">Metrics are computed only from recorded events.</p>
        </div>
        <div className="flex items-center gap-4">
          {showDemo && <SourceBadge source="DEMO_DATA" />}
          <LabeledSwitch label="Preview with demo data" checked={showDemo} onChange={setShowDemo} />
        </div>
      </div>

      {!sum ? (
        <EmptyState title="No recorded sessions yet" hint="Run a Vision or Neural session with recording enabled. Nothing is recorded by default, and no metrics are shown until real events exist." />
      ) : (
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-4 lg:grid-cols-6">
            <Panel><Readout label="Sessions" value={sum.sessions} /></Panel>
            <Panel><Readout label="Interactions" value={sum.interactions} /></Panel>
            <Panel><Readout label="Successful" value={sum.byOutcome.success} tone="ok" /></Panel>
            <Panel><Readout label="Incorrect" value={sum.byOutcome.incorrect} tone="warn" /></Panel>
            <Panel><Readout label="False activations" value={sum.byOutcome.false} tone="bad" /></Panel>
            <Panel><Readout label="Median latency" value={fmt(sum.medianLatencyMs)} unit="ms" /></Panel>
          </div>

          <div className="grid gap-4 lg:grid-cols-2">
            <Panel title="Mode comparison" source="DEMO_DATA">
              <div className="h-56">
                <ResponsiveContainer width="100%" height="100%" initialDimension={{ width: 480, height: 224 }}>
                  <BarChart
                    data={(['VISION', 'NEURAL'] as const).map((m) => ({
                      mode: m,
                      'Median latency (ms)': Math.round(sum.perMode[m].medianLatencyMs ?? 0),
                      'Target acquisition (ms)': Math.round(sum.perMode[m].medianAcquisitionMs ?? 0),
                    }))}
                  >
                    <CartesianGrid stroke="rgb(255 255 255 / 0.06)" vertical={false} />
                    <XAxis dataKey="mode" tick={axis} />
                    <YAxis tick={axis} width={40} />
                    <Legend wrapperStyle={{ fontSize: 11 }} />
                    <Bar dataKey="Median latency (ms)" fill="#22d3ee" radius={[3, 3, 0, 0]} isAnimationActive={false} />
                    <Bar dataKey="Target acquisition (ms)" fill="#8b5cf6" radius={[3, 3, 0, 0]} isAnimationActive={false} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
              <dl className="mt-2 grid grid-cols-2 gap-2 text-xs text-text2">
                <div>Vision success: <span className="font-mono text-text">{pct(sum.perMode.VISION.successRate)}</span></div>
                <div>Neural success: <span className="font-mono text-text">{pct(sum.perMode.NEURAL.successRate)}</span></div>
              </dl>
            </Panel>

            <Panel title="Per-session quality" source="DEMO_DATA">
              <div className="h-56">
                <ResponsiveContainer width="100%" height="100%" initialDimension={{ width: 480, height: 224 }}>
                  <BarChart data={sessions.map((s) => ({ id: s.id.replace('demo-', '#'), 'Calibration error (px)': s.calibrationErrorPx ?? 0, 'Cursor stability (px)': s.cursorStabilityPx }))}>
                    <CartesianGrid stroke="rgb(255 255 255 / 0.06)" vertical={false} />
                    <XAxis dataKey="id" tick={axis} />
                    <YAxis tick={axis} width={36} />
                    <Legend wrapperStyle={{ fontSize: 11 }} />
                    <Bar dataKey="Calibration error (px)" fill="#a78bfa" radius={[3, 3, 0, 0]} isAnimationActive={false} />
                    <Bar dataKey="Cursor stability (px)" fill="#22d3ee" radius={[3, 3, 0, 0]} isAnimationActive={false} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
              <p className="mt-2 text-xs text-text2">Calibration error applies to Vision sessions only (0 = not applicable).</p>
            </Panel>
          </div>

          <div className="grid gap-4 lg:grid-cols-[1fr_1.3fr]">
            <Panel title="EEG performance · reported separately" source="DEMO_DATA">
              <div className="grid grid-cols-2 gap-4">
                <Readout label="Offline accuracy" value={pct(sum.offlineEegAccuracy)} />
                <Readout label="Online success" value={pct(sum.onlineEegSuccessRate)} />
              </div>
              <p className="mt-3 text-xs text-text2">Offline = held-out validation windows. Online = live control outcomes. They measure different things and are never combined.</p>
              <div className="mt-3 text-xs text-text2">
                Median target acquisition: <span className="font-mono text-text">{fmt(sum.medianAcquisitionMs, 0, ' ms')}</span> ·
                Mean calibration error: <span className="font-mono text-text">{fmt(sum.meanCalibrationErrorPx, 1, ' px')}</span>
              </div>
            </Panel>

            <Panel title="Sessions" source="DEMO_DATA" actions={
              <>
                <Button size="xs" variant="secondary" onClick={() => exportCsv('sessions')}>Export sessions CSV</Button>
                <Button size="xs" variant="secondary" onClick={() => exportCsv('interactions')}>Export events CSV</Button>
              </>
            }>
              <table className="w-full text-left text-sm" aria-label="Sessions">
                <thead className="label-caps">
                  <tr><th className="pb-2 font-normal">ID</th><th className="font-normal">Mode</th><th className="font-normal">Date</th><th className="text-right font-normal">Duration</th></tr>
                </thead>
                <tbody className="font-mono text-xs">
                  {sessions.map((s) => (
                    <tr key={s.id} className="border-t border-white/6">
                      <td className="py-1.5">{s.id}</td>
                      <td>{s.mode}</td>
                      <td>{new Date(s.startedAt).toISOString().slice(0, 10)}</td>
                      <td className="text-right">{Math.round(s.durationS / 60)} min</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Panel>
          </div>
        </div>
      )}
    </div>
  )
}
