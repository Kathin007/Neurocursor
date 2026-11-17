// Targets on the live stage, in normalized screen coordinates (0-1), so hit-testing needs no DOM measurement.

export interface Tile {
  id: string
  label: string
  x: number
  y: number
  w: number
  h: number
}

const COLS = 3
const ROWS = 2
const X0 = 0.14
const Y0 = 0.24
const W = 0.21
const H = 0.22
const GAP_X = 0.045
const GAP_Y = 0.06

export const TILES: Tile[] = Array.from({ length: COLS * ROWS }, (_, i) => {
  const c = i % COLS
  const r = Math.floor(i / COLS)
  return { id: `t${i + 1}`, label: String.fromCharCode(65 + i), x: X0 + c * (W + GAP_X), y: Y0 + r * (H + GAP_Y), w: W, h: H }
})

export function hitTile(x: number, y: number, tiles: Tile[] = TILES): Tile | null {
  return tiles.find((t) => x >= t.x && x <= t.x + t.w && y >= t.y && y <= t.y + t.h) ?? null
}
