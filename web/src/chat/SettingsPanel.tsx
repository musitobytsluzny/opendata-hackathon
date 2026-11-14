import { DEFAULT_PREFERENCES, type Preferences } from '../hooks/usePreferences'
import { Icon } from '../components/Icon'

type Props = {
  preferences: Preferences
  update: <K extends keyof Preferences>(key: K, value: Preferences[K]) => void
  reset: () => void
  username?: string
  logout: () => void
}

const toggles = [
  ['dimOutside', 'Ztmavit okolní státy'],
  ['showTowns', 'Názvy měst'],
  ['showLabels', 'Hodnoty na mapě'],
  ['showLegend', 'Legenda a pokrytí dat'],
  ['autoFocus', 'Po odpovědi vycentrovat mapu'],
  ['autoScroll', 'Posouvat chat k nové odpovědi'],
  ['reducedMotion', 'Omezit animace'],
] as const

export function SettingsPanel({ preferences, update, reset, username, logout }: Props) {
  return (
    <div
      id="popover-settings"
      className="popover popover--left settings"
      role="dialog"
      aria-label="Nastavení"
    >
      <p className="popover__who">
        Přihlášen jako <strong>{username}</strong>
      </p>
      <p className="popover__heading">Mapa a konverzace</p>
      {toggles.map(([key, label]) => (
        <label className="switch" key={key}>
          <input
            type="checkbox"
            checked={preferences[key]}
            onChange={(event) => update(key, event.target.checked)}
          />
          <span className="switch__track" aria-hidden="true" />
          {label}
        </label>
      ))}
      <label className="settings__field">
        <span>
          Ztmavení okolí <output>{Math.round(preferences.dimOpacity * 100)} %</output>
        </span>
        <input
          type="range"
          min="0"
          max="0.9"
          step="0.05"
          value={preferences.dimOpacity}
          disabled={!preferences.dimOutside}
          onChange={(event) => update('dimOpacity', Number(event.target.value))}
        />
      </label>
      <label className="settings__field">
        Mapový podklad
        <select
          aria-label="Mapový podklad"
          value={preferences.basemap}
          onChange={(event) => update('basemap', event.target.value as Preferences['basemap'])}
        >
          <option value="satellite">Satelitní · rychlejší přehled</option>
          <option value="ortho">Ortofoto ČÚZK · větší detail</option>
        </select>
      </label>
      <label className="settings__field">
        Velikost textu
        <select
          aria-label="Velikost textu"
          value={preferences.textSize}
          onChange={(event) => update('textSize', event.target.value as Preferences['textSize'])}
        >
          <option value="normal">Běžná</option>
          <option value="large">Větší</option>
        </select>
      </label>
      <div className="popover__rule" />
      <button type="button" className="popover__item" onClick={reset}>
        Obnovit výchozí nastavení
      </button>
      <button type="button" className="popover__item" onClick={logout}>
        <Icon name="logout" size={18} />
        Odhlásit se
      </button>
      <span className="sr-only">Výchozí šířka chatu {DEFAULT_PREFERENCES.panelWidth} pixelů.</span>
    </div>
  )
}
