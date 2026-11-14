import { useEffect, useState } from 'react'

export const DEFAULT_PREFERENCES = {
  dimOutside: true,
  dimOpacity: 0.68,
  showTowns: true,
  showLabels: true,
  autoFocus: true,
  autoScroll: true,
  reducedMotion: false,
  basemap: 'satellite' as 'satellite' | 'ortho',
  textSize: 'normal' as 'normal' | 'large',
  panelWidth: 330,
  panelCollapsed: false,
  showLegend: true,
}
export type Preferences = typeof DEFAULT_PREFERENCES
const STORAGE_KEY = 'kartogram:preferences:v1'

function load(): Preferences {
  try {
    const parsed = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? '{}')
    const result = { ...DEFAULT_PREFERENCES }
    for (const key of Object.keys(result) as (keyof Preferences)[]) {
      if (typeof parsed[key] === typeof result[key]) Object.assign(result, { [key]: parsed[key] })
    }
    result.panelWidth = Number.isFinite(result.panelWidth)
      ? Math.max(330, Math.min(1600, result.panelWidth))
      : 330
    result.dimOpacity = Number.isFinite(result.dimOpacity)
      ? Math.max(0, Math.min(0.9, result.dimOpacity))
      : 0.68
    if (!['satellite', 'ortho'].includes(result.basemap)) result.basemap = 'satellite'
    if (!['normal', 'large'].includes(result.textSize)) result.textSize = 'normal'
    return result
  } catch {
    return { ...DEFAULT_PREFERENCES }
  }
}

export function usePreferences() {
  const [preferences, setPreferences] = useState(load)
  useEffect(() => {
    const timer = window.setTimeout(() => {
      try {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(preferences))
      } catch {
        /* Storage optional. */
      }
    }, 200)
    return () => window.clearTimeout(timer)
  }, [preferences])
  function update<K extends keyof Preferences>(key: K, value: Preferences[K]) {
    setPreferences((previous) => ({ ...previous, [key]: value }))
  }
  return { preferences, update, reset: () => setPreferences({ ...DEFAULT_PREFERENCES }) }
}
