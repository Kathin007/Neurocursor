import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { fakeVisionApi, makeFactory, stubFetchOk } from '@/test-utils'
import App from './App'

vi.mock('@/lib/display', async (orig) => ({
  ...(await orig<typeof import('@/lib/display')>()),
  getRefreshRate: () => Promise.resolve(60),
}))

afterEach(() => vi.unstubAllGlobals())

const go = (name: RegExp) => userEvent.click(within(screen.getByRole('navigation', { name: 'Screens' })).getByRole('button', { name }))

describe('App shell + Welcome', () => {
  it('shows branding, tagline and both mode entries', () => {
    stubFetchOk()
    render(<App createClient={makeFactory().create} visionApi={fakeVisionApi()} />)
    expect(screen.getByText('Beyond Touch. Beyond Input.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /VISION/ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /NEURAL/ })).toBeInTheDocument()
  })

  it('never reports a connection that does not exist', async () => {
    stubFetchOk()
    render(<App createClient={makeFactory().create} visionApi={fakeVisionApi()} />)
    expect(screen.getByTestId('backend-chip')).toHaveTextContent('connecting')
    const list = screen.getByRole('list', { name: 'Readiness checks' })
    const ws = within(list).getByText('Telemetry WebSocket').closest('li')!
    expect(ws).toHaveAttribute('data-status', 'pending')
    // EEG is never "ok": no headset logic exists yet.
    const eeg = within(list).getByText('EEG device').closest('li')!
    expect(eeg).toHaveAttribute('data-status', 'warn')
    await waitFor(() => expect(within(list).getByText(/uptime/)).toBeInTheDocument())
  })

  it('marks the backend check failed when REST is unreachable', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('refused')))
    render(<App createClient={makeFactory().create} visionApi={fakeVisionApi()} />)
    const li = (await screen.findByText(/Unreachable: .*refused/)).closest('li')!
    expect(li).toHaveAttribute('data-status', 'fail')
  })

  it('reflects the real socket state and measures a ping round-trip', async () => {
    stubFetchOk()
    const { sock, create } = makeFactory()
    render(<App createClient={create} visionApi={fakeVisionApi()} />)
    sock.onopen?.()
    await waitFor(() => expect(screen.getByTestId('backend-chip')).toHaveTextContent('open'))
    await userEvent.click(screen.getByRole('button', { name: /ping backend/i }))
    const { id } = JSON.parse(sock.sent[0]!) as { id: number }
    sock.onmessage?.({ data: JSON.stringify({ type: 'system_log', timestamp: 1, source: null, payload: { message: 'pong', ping_id: id } }) })
    await waitFor(() => expect(screen.getByTestId('rtt')).toHaveTextContent(/ms$/))
  })

  it('measured display refresh appears in the readiness list', async () => {
    stubFetchOk()
    render(<App createClient={makeFactory().create} visionApi={fakeVisionApi()} />)
    expect(await screen.findByText(/60 Hz measured/)).toBeInTheDocument()
  })

  it('falls back to the static background without WebGL (jsdom)', () => {
    stubFetchOk()
    render(<App createClient={makeFactory().create} visionApi={fakeVisionApi()} />)
    expect(screen.getByTestId('background')).toHaveAttribute('data-mode', 'static')
  })

  it('entering NEURAL opens Calibration on the Neural tab, VISION on the Vision tab', async () => {
    stubFetchOk()
    render(<App createClient={makeFactory().create} visionApi={fakeVisionApi()} />)
    await userEvent.click(screen.getByRole('button', { name: /NEURAL/ }))
    expect(await screen.findByRole('tab', { name: 'Neural', selected: true })).toBeInTheDocument()
    await go(/Start/)
    await userEvent.click(await screen.findByRole('button', { name: /VISION/ }))
    expect(await screen.findByRole('tab', { name: 'Vision', selected: true })).toBeInTheDocument()
  })
})

describe('every demo-driven screen is badged DEMO_DATA, and the real ones carry none', () => {
  it.each([/Neural/, /Analytics/])('%s (still demo)', async (name) => {
    stubFetchOk()
    render(<App createClient={makeFactory().create} visionApi={fakeVisionApi()} />)
    await go(name)
    await waitFor(() => expect(document.querySelectorAll('[data-source="DEMO_DATA"]').length).toBeGreaterThan(0))
  })
})

describe('the vision screens are real, not demo', () => {
  it('Calibration (Vision tab) and Live show no DEMO_DATA badge; the Neural tab still does', async () => {
    stubFetchOk()
    render(<App createClient={makeFactory().create} visionApi={fakeVisionApi()} />)
    await go(/Calibration/)
    expect(await screen.findByRole('button', { name: 'Start camera' })).toBeInTheDocument()
    expect(document.querySelectorAll('[data-source="DEMO_DATA"]')).toHaveLength(0)
    await userEvent.click(screen.getByRole('tab', { name: 'Neural' }))
    await waitFor(() => expect(document.querySelectorAll('[data-source="DEMO_DATA"]').length).toBeGreaterThan(0))
    await go(/Live/)
    expect(await screen.findByRole('heading', { name: 'Live test' })).toBeInTheDocument()
    expect(document.querySelectorAll('[data-source="DEMO_DATA"]')).toHaveLength(0)
  })

  it('Start camera on the Calibration screen calls the real start endpoint of the (injected) api', async () => {
    stubFetchOk()
    const api = fakeVisionApi()
    render(<App createClient={makeFactory().create} visionApi={api} />)
    await go(/Calibration/)
    await userEvent.click(await screen.findByRole('button', { name: 'Start camera' }))
    expect(api.start).toHaveBeenCalledTimes(1)
    expect(await screen.findByRole('img', { name: /camera preview/i })).toBeInTheDocument()
  })

  it('the shared session carries over: after starting on Calibration, Live already shows the running camera', async () => {
    stubFetchOk()
    const api = fakeVisionApi()
    render(<App createClient={makeFactory().create} visionApi={api} />)
    await go(/Calibration/)
    await userEvent.click(await screen.findByRole('button', { name: 'Start camera' }))
    await screen.findByRole('img', { name: /camera preview/i })
    await go(/Live/)
    expect(await screen.findByRole('img', { name: /camera preview/i })).toBeInTheDocument()
    expect(api.start).toHaveBeenCalledTimes(1)
  })
})
