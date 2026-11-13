import { useSyncExternalStore } from 'react'
import { PALETTES, type PaletteId } from '../map/palette'

export type Settings = {
  basemap: 'orto' | 'dark'
  towns: boolean
  dim: boolean
  palette: PaletteId
  theme: 'system' | 'light' | 'dark'
  text: 'normal' | 'large'
  reduceMotion: boolean
}

const KEY = 'settings'

const DEFAULTS: Settings = {
  basemap: 'orto',
  towns: true,
  dim: true,
  palette: 'blue',
  theme: 'system',
  text: 'normal',
  reduceMotion: false,
}

const OPTIONS: { [K in keyof Settings]: readonly Settings[K][] } = {
  basemap: ['orto', 'dark'],
  towns: [true, false],
  dim: [true, false],
  palette: ['blue', 'cividis'],
  theme: ['system', 'light', 'dark'],
  text: ['normal', 'large'],
  reduceMotion: [true, false],
}

function load(): Settings {
  const next: Record<string, unknown> = { ...DEFAULTS }
  try {
    const stored = JSON.parse(localStorage.getItem(KEY) ?? '{}') as Record<string, unknown>
    for (const key of Object.keys(DEFAULTS) as (keyof Settings)[]) {
      if ((OPTIONS[key] as readonly unknown[]).includes(stored[key])) next[key] = stored[key]
    }
  } catch {}
  return next as Settings
}

const darkQuery = window.matchMedia('(prefers-color-scheme: dark)')
const motionQuery = window.matchMedia('(prefers-reduced-motion: reduce)')
const listeners = new Set<() => void>()
let state = load()

function apply() {
  const root = document.documentElement
  const dark = state.theme === 'dark' || (state.theme === 'system' && darkQuery.matches)
  root.dataset.theme = dark ? 'dark' : 'light'
  root.dataset.text = state.text
  root.dataset.motion = state.reduceMotion ? 'reduce' : 'full'
  const [low, , high] = PALETTES[state.palette]
  root.style.setProperty('--data-low', low)
  root.style.setProperty('--data-high', high)
}

apply()
darkQuery.addEventListener('change', apply)

export function setSetting<K extends keyof Settings>(key: K, value: Settings[K]) {
  if (state[key] === value) return
  state = { ...state, [key]: value }
  try {
    localStorage.setItem(KEY, JSON.stringify(state))
  } catch {}
  apply()
  listeners.forEach((listener) => listener())
}

function subscribe(listener: () => void) {
  listeners.add(listener)
  return () => {
    listeners.delete(listener)
  }
}

export function useSettings(): Settings {
  return useSyncExternalStore(subscribe, () => state)
}

export function reducedMotion(): boolean {
  return state.reduceMotion || motionQuery.matches
}
