import '@testing-library/jest-dom/vitest'
import { cleanup } from '@testing-library/react'
import { afterEach, beforeAll } from 'vitest'

// Vitest globals are off, so RTL's auto-cleanup isn't registered; do it explicitly.
afterEach(cleanup)

// jsdom has no canvas/WebGL. Make getContext return null quietly so code takes its "unavailable" path.
beforeAll(() => {
  HTMLCanvasElement.prototype.getContext = (() => null) as unknown as HTMLCanvasElement['getContext']
})
