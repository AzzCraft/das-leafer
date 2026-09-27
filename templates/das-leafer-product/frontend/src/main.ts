import './style.css'

import { Leafer, Rect } from 'leafer-ui'

type HfviState = {
  x: number
  y: number
  zoom: number
  selected: string
}

type HfviEvent =
  | { type: 'pan'; dx: number; dy: number }
  | { type: 'zoom'; delta: number }
  | { type: 'select'; target: string }

type HfviTape = {
  schemaVersion: '1.0.0'
  tapeId: 'baseline'
  initial: HfviState
  events: HfviEvent[]
}

const INITIAL_STATE: HfviState = { x: 0, y: 0, zoom: 100, selected: 'none' }
const MIN_ZOOM = 1
const MAX_ZOOM = 400

// This starter's real frontend is deliberately small, but its HFVI test mode
// uses the same state transition and render path as the rendered application.
// `?hfviTape=baseline` is a verification-only input: it accepts one checked-in
// tape ID and never evaluates caller supplied script, selectors, or paths.
const state: HfviState = { ...INITIAL_STATE }

const leafer = new Leafer({ view: window })

const rect = new Rect({
  x: 100,
  y: 100,
  width: 200,
  height: 200,
  fill: '#32cd79',
  cornerRadius: [50, 80, 0, 80],
  draggable: true,
})

leafer.add(rect)

function assertFiniteInteger(value: unknown, field: string): number {
  if (typeof value !== 'number' || !Number.isSafeInteger(value)) {
    throw new Error(`HFVI ${field} must be a safe integer`)
  }
  return value
}

function renderState(): void {
  const scale = state.zoom / 100
  rect.x = 100 + state.x * 20
  rect.y = 100 + state.y * 20
  rect.scaleX = scale
  rect.scaleY = scale
  rect.fill = state.selected === 'river' ? '#0b5fff' : '#32cd79'
  document.documentElement.dataset.hfviState = JSON.stringify(state)
}

function applyHfviEvent(event: HfviEvent): void {
  if (!event || typeof event !== 'object' || typeof event.type !== 'string') {
    throw new Error('HFVI event must be an object with a type')
  }
  if (event.type === 'pan') {
    state.x += assertFiniteInteger(event.dx, 'pan.dx')
    state.y += assertFiniteInteger(event.dy, 'pan.dy')
  } else if (event.type === 'zoom') {
    state.zoom += assertFiniteInteger(event.delta, 'zoom.delta')
    if (state.zoom < MIN_ZOOM || state.zoom > MAX_ZOOM) {
      throw new Error(`HFVI zoom must remain between ${MIN_ZOOM} and ${MAX_ZOOM}`)
    }
  } else if (event.type === 'select') {
    if (typeof event.target !== 'string' || event.target.length === 0 || event.target.length > 120) {
      throw new Error('HFVI selection target must be a bounded non-empty string')
    }
    state.selected = event.target
  } else {
    throw new Error(`Unsupported HFVI event type: ${event.type}`)
  }
  renderState()
}

function validateTape(value: unknown): HfviTape {
  if (!value || typeof value !== 'object') {
    throw new Error('HFVI tape must be an object')
  }
  const tape = value as Partial<HfviTape>
  if (tape.schemaVersion !== '1.0.0' || tape.tapeId !== 'baseline' || !tape.initial || !Array.isArray(tape.events)) {
    throw new Error('Unsupported HFVI tape identity or shape')
  }
  assertFiniteInteger(tape.initial.x, 'initial.x')
  assertFiniteInteger(tape.initial.y, 'initial.y')
  const zoom = assertFiniteInteger(tape.initial.zoom, 'initial.zoom')
  if (zoom < MIN_ZOOM || zoom > MAX_ZOOM || typeof tape.initial.selected !== 'string' || !tape.initial.selected) {
    throw new Error('HFVI initial state is invalid')
  }
  return tape as HfviTape
}

async function replayRequestedHfviTape(): Promise<void> {
  const tapeId = new URLSearchParams(window.location.search).get('hfviTape')
  if (tapeId === null) {
    return
  }
  if (tapeId !== 'baseline') {
    throw new Error('Only the checked-in baseline HFVI tape may be replayed')
  }
  const response = await fetch('/hfvi/tapes/baseline.json', { cache: 'no-store', credentials: 'same-origin' })
  if (!response.ok) {
    throw new Error(`Unable to load HFVI tape: ${response.status}`)
  }
  const tape = validateTape(await response.json())
  state.x = tape.initial.x
  state.y = tape.initial.y
  state.zoom = tape.initial.zoom
  state.selected = tape.initial.selected
  renderState()
  for (const event of tape.events) {
    applyHfviEvent(event)
  }
  document.documentElement.dataset.hfviReplay = tape.tapeId
}

renderState()

declare global {
  interface Window {
    __dasHfvi?: {
      applyEvent: (event: HfviEvent) => void
      getState: () => HfviState
    }
  }
}

window.__dasHfvi = {
  applyEvent: applyHfviEvent,
  getState: () => ({ ...state }),
}

void replayRequestedHfviTape().catch((error: unknown) => {
  document.documentElement.dataset.hfviError = error instanceof Error ? error.message : 'unknown HFVI replay error'
  throw error
})
