import { DEFAULT_PREFERENCES, type Preferences } from '../hooks/usePreferences'
import { useState } from 'react'
import { Choice } from '../components/Choice'
import { Icon } from '../components/Icon'

type Props = {
  preferences: Preferences
  update: <K extends keyof Preferences>(key: K, value: Preferences[K]) => void
  reset: () => void
  username?: string
  logout: () => void
  onClearHistory: () => void
  hasHistory: boolean
}

const toggles = [
  ['autoFocus', 'Po odpovědi vycentrovat mapu'],
  ['autoScroll', 'Posouvat chat k nové odpovědi'],
  ['reducedMotion', 'Omezit animace'],
] as const

export function SettingsPanel({
  preferences,
  update,
  reset,
  username,
  logout,
  onClearHistory,
  hasHistory,
}: Props) {
  const [confirmClear, setConfirmClear] = useState(false)
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
      <p className="popover__heading">Chování aplikace</p>
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
      <Choice
        label="Vzhled"
        value={preferences.theme}
        options={
          [
            { value: 'system', label: 'Systém' },
            { value: 'light', label: 'Světlý' },
            { value: 'dark', label: 'Tmavý' },
          ] as const
        }
        onChange={(value) => update('theme', value)}
      />
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
      {confirmClear ? (
        <div className="confirm" role="alertdialog" aria-label="Smazat historii konverzací">
          <p className="confirm__text">
            Smazat všechny konverzace a rozepsané dotazy? Tento krok nejde vrátit.
          </p>
          <div className="confirm__actions">
            <button type="button" className="confirm__btn" onClick={() => setConfirmClear(false)}>
              Zrušit
            </button>
            <button
              type="button"
              className="confirm__btn confirm__btn--danger"
              onClick={onClearHistory}
            >
              Smazat
            </button>
          </div>
        </div>
      ) : (
        <button
          type="button"
          className="popover__item"
          disabled={!hasHistory}
          onClick={() => setConfirmClear(true)}
        >
          <Icon name="trash" size={18} />
          Smazat historii konverzací
        </button>
      )}
      <button type="button" className="popover__item" onClick={logout}>
        <Icon name="logout" size={18} />
        Odhlásit se
      </button>
      <span className="sr-only">Výchozí šířka chatu {DEFAULT_PREFERENCES.panelWidth} pixelů.</span>
    </div>
  )
}
