import { resetPreferences, setPreference, useSettings } from '../settings/settings'
export { DEFAULT_PREFERENCES, type Preferences } from '../settings/settings'

export function usePreferences() {
  return { preferences: useSettings(), update: setPreference, reset: resetPreferences }
}
