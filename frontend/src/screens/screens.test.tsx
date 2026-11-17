import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { AnalyticsScreen } from './analytics/AnalyticsScreen'
import { FrequencyConfig } from './calibration/FrequencyConfig'
import { NeuralControlRoom } from './neural/NeuralControlRoom'
import { DEFAULT_TARGETS } from '@/lib/ssvep'

const download = vi.hoisted(() => vi.fn())
vi.mock('@/lib/download', () => ({ downloadText: download }))

let refreshHz: number | null = 60
vi.mock('@/lib/display', async (orig) => ({
  ...(await orig<typeof import('@/lib/display')>()),
  getRefreshRate: () => Promise.resolve(refreshHz),
}))

afterEach(() => {
  download.mockReset()
  refreshHz = 60
})

describe('Neural Control Room', () => {
  it('flicker is off by default, with a photosensitivity warning', async () => {
    render(<NeuralControlRoom />)
    expect(screen.getByRole('note')).toHaveTextContent(/Photosensitivity warning/)
    const btn = await screen.findByRole('button', { name: 'Start flicker' })
    await waitFor(() => expect(btn).toBeEnabled())
  })

  it('offers channel select, intention + confidence and a labelled command history', () => {
    render(<NeuralControlRoom />)
    expect(screen.getByLabelText('Channel select')).toBeInTheDocument()
    expect(screen.getByText('Predicted intention')).toBeInTheDocument()
    const items = within(screen.getByRole('list', { name: 'Command history' })).getAllByRole('listitem')
    expect(items.length).toBeGreaterThan(0)
    for (const li of items) expect(['accepted', 'rejected']).toContain(li.getAttribute('data-outcome'))
  })

  it('does not present demo output as a device', () => {
    render(<NeuralControlRoom />)
    expect(screen.getByText(/No headset: scripted demo signal/)).toBeInTheDocument()
  })
})

describe('SSVEP frequency validation (real logic, measured refresh)', () => {
  it('warns that 8 Hz is not frame-compatible at 60 Hz and proposes alternatives', async () => {
    render(<FrequencyConfig targets={DEFAULT_TARGETS} onChange={() => {}} />)
    const up = await screen.findByTestId('freq-up')
    await waitFor(() => expect(within(up).getByRole('alert')).toHaveTextContent(/8 Hz would flicker at 7.5 Hz.*7.5, 8.57/))
    expect(within(screen.getByTestId('freq-down')).queryByRole('alert')).toBeNull()
  })

  it('says so when the refresh rate cannot be measured, rather than guessing', async () => {
    refreshHz = null
    render(<FrequencyConfig targets={DEFAULT_TARGETS} onChange={() => {}} />)
    expect(await screen.findByText(/could not be measured/)).toBeInTheDocument()
    expect(screen.queryByText(/frame-compatible/)).toBeNull()
  })
})

describe('Analytics', () => {
  it('shows badged demo metrics by default and exports a DEMO_DATA-labelled CSV', async () => {
    render(<AnalyticsScreen />)
    expect(document.querySelectorAll('[data-source="DEMO_DATA"]').length).toBeGreaterThan(0)
    await userEvent.click(screen.getByRole('button', { name: 'Export sessions CSV' }))
    expect(download).toHaveBeenCalledTimes(1)
    const [filename, csv] = download.mock.calls[0] as [string, string]
    expect(filename).toBe('neurocursor-DEMO_DATA-sessions.csv')
    expect(csv.split('\n')[0]).toContain('data_source')
    expect(csv).toContain('DEMO_DATA')
  })

  it('reports offline accuracy and online success as separate numbers', () => {
    render(<AnalyticsScreen />)
    expect(screen.getByText('Offline accuracy')).toBeInTheDocument()
    expect(screen.getByText('Online success')).toBeInTheDocument()
  })

  it('shows an empty state (no zeros, no export) when there is no data', async () => {
    render(<AnalyticsScreen />)
    await userEvent.click(screen.getByRole('switch', { name: 'Preview with demo data' }))
    expect(screen.getByText('No recorded sessions yet')).toBeInTheDocument()
    expect(screen.queryByText('Median latency')).toBeNull()
    expect(screen.queryByRole('button', { name: /Export/ })).toBeNull()
  })
})
