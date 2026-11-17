// DEMO_DATA: scripted, deterministic stand-ins for the vision engine (real engine lands in M3).
// Every value is a pure function of time `t` (ms), so nothing here is measured from a camera.

export interface DemoVision {
  gaze: { x: number; y: number } // normalized 0-1
  cursor: { x: number; y: number }
  blinking: boolean
  ear: number // eye aspect ratio
  dwell: number // 0-1 progress
  headPose: { yaw: number; pitch: number; roll: number } // degrees
}

const gazeAt = (t: number) => ({
  x: 0.5 + 0.34 * Math.sin(t / 2300),
  y: 0.5 + 0.28 * Math.sin(t / 1700 + 1),
})

export function demoVision(t: number): DemoVision {
  const gaze = gazeAt(t)
  const lag = gazeAt(t - 220) // cursor trails gaze, as a smoothed output would
  const phase = t % 4200
  const blinking = phase < 150
  const ear = blinking ? 0.08 + 0.1 * Math.abs(phase - 75) / 75 : 0.31 + 0.01 * Math.sin(t / 400)
  return {
    gaze,
    cursor: { x: (gaze.x + lag.x * 2) / 3, y: (gaze.y + lag.y * 2) / 3 },
    blinking,
    ear,
    dwell: (t % 2400) / 2400,
    headPose: { yaw: 6 * Math.sin(t / 3100), pitch: 4 * Math.sin(t / 2700 + 2), roll: 2 * Math.sin(t / 3700) },
  }
}

export const CALIBRATION_POINTS: ReadonlyArray<{ x: number; y: number }> = [
  { x: 0.1, y: 0.1 }, { x: 0.5, y: 0.1 }, { x: 0.9, y: 0.1 },
  { x: 0.1, y: 0.5 }, { x: 0.5, y: 0.5 }, { x: 0.9, y: 0.5 },
  { x: 0.1, y: 0.9 }, { x: 0.5, y: 0.9 }, { x: 0.9, y: 0.9 },
]

// Scripted per-point residuals for the DEMO_DATA calibration walkthrough (px). Not a measurement.
export const DEMO_HELD_OUT_ERRORS_PX: ReadonlyArray<number> = [41, 33, 47, 29, 22, 31, 52, 38, 44]
