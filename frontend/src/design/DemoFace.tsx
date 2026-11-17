import { useEffect, useRef } from 'react'

interface Props {
  gaze: { x: number; y: number }
  blinking: boolean
  headPose?: { yaw: number; pitch: number; roll: number }
  className?: string
}

const EYE_RING = Array.from({ length: 12 }, (_, i) => [Math.cos((i / 12) * Math.PI * 2), 0.55 * Math.sin((i / 12) * Math.PI * 2)] as const)

/** Schematic face + landmark overlay drawn on a canvas. This is an illustration driven by DEMO_DATA, not a camera frame. */
export function DemoFace({ gaze, blinking, headPose, className }: Props) {
  const ref = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    const canvas = ref.current
    const ctx = canvas?.getContext('2d')
    if (!canvas || !ctx) return // jsdom has no 2D context
    const { width: w, height: h } = canvas
    ctx.clearRect(0, 0, w, h)
    ctx.fillStyle = 'rgb(9 11 22 / 0.9)'
    ctx.fillRect(0, 0, w, h)

    const yaw = headPose?.yaw ?? 0
    const cx = w / 2 + yaw * 2
    ctx.strokeStyle = 'rgb(167 139 250 / 0.35)'
    ctx.lineWidth = 1.5
    ctx.beginPath()
    ctx.ellipse(cx, h * 0.52, w * 0.2, h * 0.38, ((headPose?.roll ?? 0) * Math.PI) / 180, 0, Math.PI * 2)
    ctx.stroke()

    for (const side of [-1, 1]) {
      const ex = cx + side * w * 0.09
      const ey = h * 0.42
      const rx = w * 0.05
      const open = blinking ? 0.08 : 1
      ctx.fillStyle = 'rgb(34 211 238 / 0.8)'
      for (const [px, py] of EYE_RING) {
        ctx.beginPath()
        ctx.arc(ex + px * rx, ey + py * rx * open, 1.6, 0, Math.PI * 2)
        ctx.fill()
      }
      if (!blinking) {
        const ix = ex + (gaze.x - 0.5) * rx * 1.6
        const iy = ey + (gaze.y - 0.5) * rx * 0.8
        ctx.strokeStyle = '#8b5cf6'
        ctx.lineWidth = 2
        ctx.beginPath()
        ctx.arc(ix, iy, rx * 0.38, 0, Math.PI * 2)
        ctx.stroke()
        ctx.fillStyle = '#f8fafc'
        ctx.fillRect(ix - 1.5, iy - 1.5, 3, 3)
      }
    }
  }, [gaze.x, gaze.y, blinking, headPose?.yaw, headPose?.roll])

  return <canvas ref={ref} width={480} height={320} className={className} role="img" aria-label="Schematic face with landmark overlay (demo illustration)" />
}
