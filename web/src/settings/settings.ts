import { useSyncExternalStore } from 'react'
import { PALETTES, type PaletteId } from '../map/palette'

export const DEFAULT_PREFERENCES = {
  dimOutside: true,
  dimOpacity: 0.68,
  showCadastre: false,
  cadastreOpacity: 0.72,
  showTowns: true,
  showLabels: true,
  autoFocus: true,
  autoScroll: true,
  reducedMotion: false,
  basemap: 'satellite' as 'satellite' | 'ortho' | 'dark',
  textSize: 'normal' as 'normal' | 'large',
  palette: 'blue' as PaletteId,
  theme: 'light' as 'light' | 'dark' | 'system',
  panelWidth: 330,
  panelCollapsed: false,
  showLegend: true,
}
export type Preferences = typeof DEFAULT_PREFERENCES
const KEY = 'kartogram:preferences:v1'
const options = {
  basemap: ['satellite', 'ortho', 'dark'],
  textSize: ['normal', 'large'],
  palette: Object.keys(PALETTES),
  theme: ['light', 'dark', 'system'],
}
function load(): Preferences {
  try {
    const legacy = JSON.parse(localStorage.getItem('settings') ?? '{}')
    const stored = JSON.parse(localStorage.getItem(KEY) ?? '{}')
    const merged = {
      ...('basemap' in legacy
        ? { basemap: legacy.basemap === 'orto' ? 'ortho' : legacy.basemap }
        : {}),
      ...('towns' in legacy ? { showTowns: legacy.towns } : {}),
      ...('dim' in legacy ? { dimOutside: legacy.dim } : {}),
      ...('text' in legacy ? { textSize: legacy.text } : {}),
      ...('reduceMotion' in legacy ? { reducedMotion: legacy.reduceMotion } : {}),
      ...('theme' in legacy ? { theme: legacy.theme } : {}),
      ...('palette' in legacy ? { palette: legacy.palette } : {}),
      ...stored,
    }
    const result = { ...DEFAULT_PREFERENCES }
    for (const key of Object.keys(result) as (keyof Preferences)[]) {
      if (typeof merged[key] === typeof result[key]) Object.assign(result, { [key]: merged[key] })
    }
    for (const [key, values] of Object.entries(options)) {
      if (!values.includes(merged[key]))
        Object.assign(result, { [key]: DEFAULT_PREFERENCES[key as keyof Preferences] })
    }
    result.panelWidth = Number.isFinite(result.panelWidth)
      ? Math.max(330, Math.min(1600, result.panelWidth))
      : 330
    result.dimOpacity = Number.isFinite(result.dimOpacity)
      ? Math.max(0, Math.min(0.9, result.dimOpacity))
      : 0.68
    result.cadastreOpacity = Number.isFinite(result.cadastreOpacity)
      ? Math.max(0.1, Math.min(1, result.cadastreOpacity))
      : 0.72
    return result
  } catch {
    return { ...DEFAULT_PREFERENCES }
  }
}
const darkQuery = window.matchMedia('(prefers-color-scheme: dark)')
const motionQuery = window.matchMedia('(prefers-reduced-motion: reduce)')
const listeners = new Set<() => void>()
let state = load()
let persistTimer = 0
function persist() {
  try {
    localStorage.setItem(KEY, JSON.stringify(state))
  } catch {
    /* Storage optional. */
  }
}
function apply() {
  const root = document.documentElement
  root.dataset.theme =
    state.theme === 'dark' || (state.theme === 'system' && darkQuery.matches) ? 'dark' : 'light'
  root.dataset.text = state.textSize
  root.dataset.motion = state.reducedMotion ? 'reduce' : 'full'
  const [low, mid, high] = PALETTES[state.palette]
  root.style.setProperty('--data-low', low)
  root.style.setProperty('--data-mid', mid)
  root.style.setProperty('--data-high', high)
}
function emit() {
  apply()
  listeners.forEach((listener) => listener())
}
export function setPreference<K extends keyof Preferences>(key: K, value: Preferences[K]) {
  if (state[key] === value) return
  state = { ...state, [key]: value }
  window.clearTimeout(persistTimer)
  persistTimer = window.setTimeout(persist, 200)
  emit()
}
export function resetPreferences() {
  state = { ...DEFAULT_PREFERENCES }
  persist()
  emit()
}
function subscribe(listener: () => void) {
  listeners.add(listener)
  return () => {
    listeners.delete(listener)
  }
}
export function useSettings(): Preferences {
  return useSyncExternalStore(subscribe, () => state)
}
export function reducedMotion(): boolean {
  return state.reducedMotion || motionQuery.matches
}
apply()
darkQuery.addEventListener('change', apply)
window.addEventListener('pagehide', persist)
window.addEventListener('storage', (event) => {
  if (event.key === KEY || event.key === null) {
    state = load()
    emit()
  }
})
