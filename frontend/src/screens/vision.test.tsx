import { act, render, renderHook, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  calibrationResult, fakeBackend, fakeSession, fakeVisionApi, gazePayload, visionStatus,
} from '@/test-utils'
import { ApiError, visionApi } from '@/lib/visionApi'
import { CalibrationOverlay } from './calibration/CalibrationOverlay'
import { verdict } from './calibration/calibration'
import { VisionCalibration } from './calibration/VisionCalibration'
import { hitTile, TILES } from './vision/tiles'
import { useVisionTelemetry } from './vision/useVisionTelemetry'
import { VisionControlRoom } from './vision/VisionControlRoom'

const FAST = { countdownMs: 0, settleMs: 0, samples: 7, maxRetries: 2 }

afterEach(() => vi.unstubAllGlobals())

describe('tiles', () => {
  it('six tiles, all inside the unit square and not overlapping', () => {
    expect(TILES).toHaveLength(6)
    for (const t of TILES) {
      expect(t.x).toBeGreaterThanOrEqual(0)
      expect(t.x + t.w).toBeLessThanOrEqual(1)
      expect(t.y + t.h).toBeLessThanOrEqual(1)
    }
    for (const a of TILES) for (const b of TILES) {
      if (a !== b) expect(a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h).toBe(false)
    }
  })

  it('hit-tests inside, on gaps and outside', () => {
    const t = TILES[0]!
    expect(hitTile(t.x + t.w / 2, t.y + t.h / 2)?.id).toBe(t.id)
    expect(hitTile(0.01, 0.01)).toBeNull()
    const gapX = t.x + t.w + 0.01
    expect(hitTile(gapX, t.y + 0.05)).toBeNull()
  })
})

describe('visionApi', () => {
  it('turns backend errors into ApiError with the server detail and status', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 503, json: () => Promise.resolve({ detail: 'camera unavailable: x' }) }))
    const err = await visionApi.start().catch((e: unknown) => e)
    expect(err).toBeInstanceOf(ApiError)
    expect(err).toMatchObject({ status: 503, message: 'camera unavailable: x' })
  })

  it('posts calibration steps to the right endpoint with the right body', async () => {
    const f = vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve({}) })
    vi.stubGlobal('fetch', f)
    await visionApi.calibrateStart(1920, 1080)
    await visionApi.calibrateCapture(4, 25)
    const [[u1, o1], [, o2]] = f.mock.calls as [[string, RequestInit], [string, RequestInit]]
    expect(u1).toBe('/api/vision/calibrate')
    expect(JSON.parse(o1.body as string)).toEqual({ step: 'start', screen_w: 1920, screen_h: 1080 })
    expect(JSON.parse(o2.body as string)).toEqual({ step: 'capture', point_index: 4, n_samples: 25 })
  })
})

describe('verdict', () => {
  it('is based on the held-out error as a fraction of screen width and never flatters a bad result', () => {
    expect(verdict(60, 1920).label).toBe('good')
    expect(verdict(150, 1920).label).toBe('fair')
    expect(verdict(930, 1920).label).toBe('poor') // the real result measured on the user's laptop
    expect(verdict(930, 1920).text).toMatch(/inaccurate/)
  })
})

describe('useVisionTelemetry', () => {
  it('folds gaze, cursor and click events into one snapshot and counts accepted vs rejected clicks', async () => {
    const be = fakeBackend()
    const { result } = renderHook(() => useVisionTelemetry(be.subscribe))
    act(() => {
      be.emit('gaze_update', gazePayload())
      be.emit('cursor_update', { x: 0.4, y: 0.5 })
      be.emit('interaction_event', { kind: 'CLICK', trigger: 'BLINK', accepted: true, reason: 'ok', confidence: 0.8, x: 0.4, y: 0.5 })
      be.emit('interaction_event', { kind: 'CLICK', trigger: 'DWELL', accepted: false, reason: 'duplicate click lockout', confidence: 0.7, x: 0.4, y: 0.5 })
      be.emit('system_log', { message: 'ignored' })
    })
    await waitFor(() => expect(result.current.accepted).toBe(1))
    expect(result.current.rejected).toBe(1)
    expect(result.current.cursor).toEqual({ x: 0.4, y: 0.5 })
    expect(result.current.gaze?.dwell).toBe(0.25)
    expect(result.current.source).toBe('REAL_WEBCAM')
    expect(result.current.clicks.map((c) => c.trigger)).toEqual(['DWELL', 'BLINK']) // newest first
  })

  it('stops listening on unmount', () => {
    const be = fakeBackend()
    const off = vi.fn()
    const { unmount } = renderHook(() => useVisionTelemetry((fn) => { const u = be.subscribe(fn); return () => { off(); u() } }))
    unmount()
    expect(off).toHaveBeenCalled()
  })
})

describe('CalibrationOverlay (the "click Calibrate" flow)', () => {
  it('runs the whole 9-point flow against the backend in order, then shows the real measured result', async () => {
    const api = fakeVisionApi({ calibrateFinish: vi.fn().mockResolvedValue(calibrationResult(40, [1024, 768])) })
    render(<CalibrationOverlay api={api} onClose={() => {}} timings={FAST} />)

    expect(await screen.findByTestId('held-out-error')).toHaveTextContent('40 px')
    expect(api.calibrateStart).toHaveBeenCalledWith(window.innerWidth, window.innerHeight)
    expect(api.calibrateCapture.mock.calls.map((c) => c[0])).toEqual([0, 1, 2, 3, 4, 5, 6, 7, 8])
    expect(api.calibrateCapture.mock.calls.every((c) => c[1] === 7)).toBe(true)
    expect(api.calibrateFinish).toHaveBeenCalledTimes(1)
    expect(screen.getByTestId('verdict')).toHaveAttribute('data-verdict', 'good')
    for (let i = 0; i < 9; i++) expect(screen.getByTestId(`cal-dot-${i}`)).toHaveAttribute('data-state', 'done')
    expect(api.calibrateCancel).not.toHaveBeenCalled() // a finished run must not be cancelled on close
  })

  it('shows a poor result as poor, with advice, instead of hiding it', async () => {
    const api = fakeVisionApi({ calibrateFinish: vi.fn().mockResolvedValue(calibrationResult(930)) })
    render(<CalibrationOverlay api={api} onClose={() => {}} timings={FAST} />)
    expect(await screen.findByTestId('held-out-error')).toHaveTextContent('930 px')
    expect(screen.getByTestId('verdict')).toHaveAttribute('data-verdict', 'poor')
    expect(screen.getByTestId('verdict')).toHaveTextContent(/Recalibrate/)
  })

  it('saves the profile on request and says so', async () => {
    const api = fakeVisionApi()
    render(<CalibrationOverlay api={api} onClose={() => {}} timings={FAST} />)
    await userEvent.click(await screen.findByRole('button', { name: 'Save profile' }))
    expect(api.calibrateSave).toHaveBeenCalledTimes(1)
    expect(await screen.findByText(/Saved as profile 3/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Saved' })).toBeDisabled()
  })

  it('Recalibrate restarts the run from the beginning', async () => {
    const api = fakeVisionApi()
    render(<CalibrationOverlay api={api} onClose={() => {}} timings={FAST} />)
    await userEvent.click(await screen.findByRole('button', { name: 'Recalibrate' }))
    await waitFor(() => expect(api.calibrateStart).toHaveBeenCalledTimes(2))
    await waitFor(() => expect(api.calibrateFinish).toHaveBeenCalledTimes(2))
    expect(api.calibrateCapture).toHaveBeenCalledTimes(18)
  })

  it('retries a point when the face was not seen (408) and then carries on', async () => {
    let failedOnce = false
    const api = fakeVisionApi({
      calibrateCapture: vi.fn().mockImplementation((i: number) => {
        if (i === 3 && !failedOnce) {
          failedOnce = true
          return Promise.reject(new ApiError(408, 'only 2/7 usable samples'))
        }
        return Promise.resolve({ point_index: i, samples: 7 })
      }),
    })
    render(<CalibrationOverlay api={api} onClose={() => {}} timings={FAST} />)
    expect(await screen.findByTestId('held-out-error')).toBeInTheDocument()
    expect(api.calibrateCapture.mock.calls.filter((c) => c[0] === 3)).toHaveLength(2)
  })

  it('stops with a clear error after the retries are used up, and offers Try again', async () => {
    const api = fakeVisionApi({ calibrateCapture: vi.fn().mockRejectedValue(new ApiError(408, 'only 0/7 usable samples')) })
    render(<CalibrationOverlay api={api} onClose={() => {}} timings={{ ...FAST, maxRetries: 1 }} />)
    expect(await screen.findByRole('alert')).toHaveTextContent('only 0/7 usable samples')
    expect(api.calibrateCapture).toHaveBeenCalledTimes(2) // first try + one retry
    expect(api.calibrateFinish).not.toHaveBeenCalled()
    expect(screen.getByRole('button', { name: 'Try again' })).toBeInTheDocument()
  })

  it('Esc closes the overlay and cancels an unfinished calibration on the backend', async () => {
    const api = fakeVisionApi({ calibrateCapture: vi.fn().mockReturnValue(new Promise(() => {})) }) // hangs mid-run
    const onClose = vi.fn()
    const { unmount } = render(<CalibrationOverlay api={api} onClose={onClose} timings={FAST} />)
    await waitFor(() => expect(api.calibrateCapture).toHaveBeenCalled())
    await userEvent.keyboard('{Escape}')
    expect(onClose).toHaveBeenCalled()
    unmount()
    expect(api.calibrateCancel).toHaveBeenCalled()
  })

  it('shows which dot is active and what to do', async () => {
    let release!: () => void
    const api = fakeVisionApi({ calibrateCapture: vi.fn().mockImplementation(() => new Promise<{ point_index: number; samples: number }>((r) => { release = () => r({ point_index: 0, samples: 7 }) })) })
    render(<CalibrationOverlay api={api} onClose={() => {}} timings={FAST} />)
    expect(await screen.findByText(/Dot 1 of 9/)).toBeInTheDocument()
    expect(screen.getByTestId('cal-active-dot')).toBeInTheDocument()
    expect(screen.getByTestId('cal-dot-0')).toHaveAttribute('data-state', 'capture')
    release()
  })
})

describe('VisionCalibration screen', () => {
  it('cannot calibrate until the camera is running and a face is found, and Start camera calls the backend', async () => {
    const be = fakeBackend()
    const session = fakeSession(visionStatus())
    const { rerender } = render(<VisionCalibration backend={be} session={session} onGoLive={() => {}} timings={FAST} />)
    expect(screen.getByRole('button', { name: 'Calibrate' })).toBeDisabled()
    await userEvent.click(screen.getByRole('button', { name: 'Start camera' }))
    expect(session.start).toHaveBeenCalled()
    expect(screen.queryByRole('img', { name: /camera preview/i })).toBeNull() // no preview until the camera is really running

    rerender(<VisionCalibration backend={be} session={fakeSession(visionStatus({ state: 'RUNNING', face: false }))} onGoLive={() => {}} />)
    expect(screen.getByRole('button', { name: 'Calibrate' })).toBeDisabled()
    expect(screen.getByText(/No face detected yet/)).toBeInTheDocument()

    rerender(<VisionCalibration backend={be} session={fakeSession(visionStatus({ state: 'RUNNING', face: true }))} onGoLive={() => {}} timings={FAST} />)
    expect(screen.getByRole('button', { name: 'Calibrate' })).toBeEnabled()
    expect(screen.getByRole('img', { name: /camera preview/i })).toHaveAttribute('src', '/api/vision/preview.mjpg')
  })

  it('clicking Calibrate opens the full-screen calibration dialog', async () => {
    const session = fakeSession(visionStatus({ state: 'RUNNING', face: true }))
    render(<VisionCalibration backend={fakeBackend()} session={session} onGoLive={() => {}} timings={FAST} />)
    await userEvent.click(screen.getByRole('button', { name: 'Calibrate' }))
    expect(await screen.findByRole('dialog', { name: 'Calibration' })).toBeInTheDocument()
    await waitFor(() => expect(session.api.calibrateStart).toHaveBeenCalled())
  })

  it('"Go to live test" is only available once calibrated, and a saved profile is shown from real status', async () => {
    const go = vi.fn()
    const { rerender } = render(<VisionCalibration backend={fakeBackend()} session={fakeSession(visionStatus({ state: 'RUNNING', face: true }))} onGoLive={go} />)
    expect(screen.getByRole('button', { name: 'Go to live test' })).toBeDisabled()
    rerender(<VisionCalibration backend={fakeBackend()} session={fakeSession(visionStatus({ state: 'RUNNING', face: true, calibrated: true }))} onGoLive={go} />)
    await userEvent.click(screen.getByRole('button', { name: 'Go to live test' }))
    expect(go).toHaveBeenCalled()
    expect(screen.getByTestId('profile-line')).toHaveTextContent(/profile 3 · REAL_WEBCAM · held-out error 88 px/)
  })
})

describe('Live screen and stage', () => {
  const setup = (status = visionStatus({ state: 'RUNNING', face: true, calibrated: true })) => {
    const be = fakeBackend()
    const session = fakeSession(status)
    render(<VisionControlRoom backend={be} session={session} onGoCalibrate={() => {}} />)
    return { be, session }
  }

  it('Open live stage is disabled until the camera runs and the user is calibrated', async () => {
    const onCal = vi.fn()
    const be = fakeBackend()
    const { rerender } = render(<VisionControlRoom backend={be} session={fakeSession(visionStatus())} onGoCalibrate={onCal} />)
    expect(screen.getByRole('button', { name: 'Open live stage' })).toBeDisabled()
    rerender(<VisionControlRoom backend={be} session={fakeSession(visionStatus({ state: 'RUNNING', face: true }))} onGoCalibrate={onCal} />)
    expect(screen.getByRole('button', { name: 'Open live stage' })).toBeDisabled()
    await userEvent.click(screen.getByRole('button', { name: 'Calibrate now' }))
    expect(onCal).toHaveBeenCalled()
  })

  it('the stage shows the simulated cursor where the backend says it is, and the raw gaze separately', async () => {
    const { be } = setup()
    await userEvent.click(screen.getByRole('button', { name: 'Open live stage' }))
    const stage = await screen.findByRole('dialog', { name: 'Live test' })
    act(() => {
      be.emit('gaze_update', gazePayload({ gaze: { x: 0.2, y: 0.3 }, dwell: 0.5 }))
      be.emit('cursor_update', { x: 0.25, y: 0.35 })
    })
    const cursor = await within(stage).findByTestId('sim-cursor')
    expect(cursor).toHaveStyle({ left: '25%', top: '35%' })
    expect(within(stage).getByTestId('gaze-marker')).toHaveStyle({ left: '20%', top: '30%' })
    expect(within(stage).getByText(/SIMULATED cursor: your real mouse is not touched/)).toBeInTheDocument()
  })

  it('an accepted click presses the tile under the cursor and only that tile', async () => {
    const { be } = setup()
    await userEvent.click(screen.getByRole('button', { name: 'Open live stage' }))
    const stage = await screen.findByRole('dialog', { name: 'Live test' })
    const t = TILES[1]!
    act(() => be.emit('interaction_event', { kind: 'CLICK', trigger: 'BLINK', accepted: true, reason: 'ok', confidence: 0.8, x: t.x + t.w / 2, y: t.y + t.h / 2 }))
    await waitFor(() => expect(within(stage).getByTestId(`count-${t.id}`)).toHaveTextContent('pressed 1'))
    expect(within(stage).getByTestId(`tile-${t.id}`)).toHaveAttribute('data-pressed', 'true')
    for (const other of TILES.filter((x) => x.id !== t.id)) expect(within(stage).getByTestId(`count-${other.id}`)).toHaveTextContent('pressed 0')
    expect(within(stage).getByTestId('click-ripple')).toHaveAttribute('data-accepted', 'true')
  })

  it('rejected clicks and clicks outside every tile press nothing, and rejections are explained', async () => {
    const { be } = setup()
    await userEvent.click(screen.getByRole('button', { name: 'Open live stage' }))
    const stage = await screen.findByRole('dialog', { name: 'Live test' })
    const t = TILES[0]!
    act(() => {
      be.emit('interaction_event', { kind: 'CLICK', trigger: 'BLINK', accepted: false, reason: 'confidence below threshold', confidence: 0.4, x: t.x + 0.05, y: t.y + 0.05 })
    })
    await waitFor(() => expect(within(stage).getByText(/BLINK rejected: confidence below threshold/)).toBeInTheDocument())
    act(() => be.emit('interaction_event', { kind: 'CLICK', trigger: 'DWELL', accepted: true, reason: 'ok', confidence: 0.9, x: 0.02, y: 0.02 }))
    await waitFor(() => expect(within(stage).getByText(/clicks accepted 1 · rejected 1/)).toBeInTheDocument())
    for (const x of TILES) expect(within(stage).getByTestId(`count-${x.id}`)).toHaveTextContent('pressed 0')
  })

  it('closed eyes are visible on the stage and a long closure is not counted as a click', async () => {
    const { be } = setup()
    await userEvent.click(screen.getByRole('button', { name: 'Open live stage' }))
    const stage = await screen.findByRole('dialog', { name: 'Live test' })
    act(() => {
      be.emit('cursor_update', { x: 0.5, y: 0.5 })
      be.emit('gaze_update', gazePayload({ eyes_closed: true, ear: 0.08 }))
    })
    await waitFor(() => expect(within(stage).getByTestId('eye-state')).toHaveTextContent('eyes CLOSED'))
    expect(within(stage).getByTestId('sim-cursor')).toHaveAttribute('data-closed', 'true')
    expect(within(stage).getByText(/clicks accepted 0/)).toBeInTheDocument()
  })

  it('Pause/Resume on the stage call the backend, and Esc closes the stage', async () => {
    const { session } = setup()
    await userEvent.click(screen.getByRole('button', { name: 'Open live stage' }))
    const stage = await screen.findByRole('dialog', { name: 'Live test' })
    await userEvent.click(within(stage).getByRole('button', { name: 'Pause' }))
    expect(session.pause).toHaveBeenCalled()
    await userEvent.keyboard('{Escape}')
    await waitFor(() => expect(screen.queryByRole('dialog', { name: 'Live test' })).toBeNull())
  })

  it('warns on the stage when the backend is paused, and shows Resume', async () => {
    setup(visionStatus({ state: 'RUNNING', face: true, calibrated: true, control: 'PAUSED' }))
    await userEvent.click(screen.getByRole('button', { name: 'Open live stage' }))
    const stage = await screen.findByRole('dialog', { name: 'Live test' })
    expect(within(stage).getByRole('status')).toHaveTextContent(/paused: the cursor is frozen/)
    expect(within(stage).getByRole('button', { name: 'Resume' })).toBeInTheDocument()
  })

  it('tuning controls are sent to the running engine over the WebSocket (debounced), not kept local', async () => {
    const { be } = setup()
    await userEvent.click(screen.getByRole('switch', { name: 'Blink click' }))
    await waitFor(() => expect(be.send).toHaveBeenCalledWith({ type: 'set_vision_config', config: { blink_click_enabled: false } }))
    await userEvent.click(screen.getByRole('switch', { name: 'Dwell click' }))
    await waitFor(() => expect(be.send).toHaveBeenCalledWith({ type: 'set_vision_config', config: { dwell_enabled: false } }))
  })

  it('has no DEMO_DATA anywhere: everything on this screen is real or absent', () => {
    setup()
    expect(document.querySelectorAll('[data-source="DEMO_DATA"]')).toHaveLength(0)
    expect(document.querySelector('[data-source="REAL_WEBCAM"]')).not.toBeNull()
  })

  it('labels the data with the source the backend actually reports, not a hardcoded one', () => {
    setup({ ...visionStatus({ state: 'RUNNING', face: true, calibrated: true }), source: 'DEMO_DATA' })
    expect(document.querySelector('[data-source="DEMO_DATA"]')).not.toBeNull()
    expect(document.querySelector('[data-source="REAL_WEBCAM"]')).toBeNull()
  })
})

describe('overlays', () => {
  it('lock page scrolling while open and restore it afterwards', async () => {
    document.body.style.overflow = 'auto'
    const { unmount } = render(<CalibrationOverlay api={fakeVisionApi()} onClose={() => {}} timings={FAST} />)
    expect(document.body.style.overflow).toBe('hidden')
    unmount()
    expect(document.body.style.overflow).toBe('auto')
  })
})
