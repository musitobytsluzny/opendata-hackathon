import { useState, type FormEvent } from 'react'
import { ApiError } from '../api/client'
import { useAuth } from '../auth/AuthContext'
import { Icon } from '../components/Icon'
import { RegionMap } from '../map/LazyRegionMap'
import { navigate, routes } from '../router/router'
import { Link } from '../router/Link'
import './LoginPage.css'

type Mode = 'login' | 'register'

const PADDING = { top: 64, right: 64, bottom: 64, left: 64 }

export function LoginPage() {
  const { login, register } = useAuth()
  const [mode, setMode] = useState<Mode>(() =>
    new URLSearchParams(window.location.search).get('registrace') !== null ? 'register' : 'login',
  )
  const [username, setUsername] = useState('')
  const [firstname, setFirstname] = useState('')
  const [lastname, setLastname] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  const isRegister = mode === 'register'

  function switchMode(next: Mode) {
    setMode(next)
    setError(null)
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    if (!username.trim() || !password) {
      setError('Vyplňte uživatelské jméno i heslo.')
      return
    }
    if (isRegister && (!firstname.trim() || !lastname.trim())) {
      setError('Vyplňte jméno i příjmení.')
      return
    }
    if (isRegister && password.length < 8) {
      setError('Heslo musí mít aspoň 8 znaků.')
      return
    }
    setLoading(true)
    try {
      if (isRegister)
        await register({
          username: username.trim(),
          firstname: firstname.trim(),
          lastname: lastname.trim(),
          password,
        })
      else await login(username.trim(), password)
      navigate(routes.map, true)
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        setError('Neplatné uživatelské jméno nebo heslo.')
      } else {
        setError(err instanceof Error ? err.message : 'Přihlášení selhalo. Zkuste to znovu.')
      }
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="auth">
      <div className="auth__stage" aria-hidden="true">
        <RegionMap
          interactive={false}
          maskOpacity={0.72}
          padding={PADDING}
          drift
          showTowns={false}
        />
      </div>
      <div className="auth__vignette" aria-hidden="true" />

      <Link href={routes.landing} className="auth__brand">
        Ptej se kraje
      </Link>

      <div className="auth__statement">
        <h1>
          {isRegister ? (
            <>
              Celý kraj
              <br />
              na jeden dotaz.
            </>
          ) : (
            <>
              Vítejte zpátky
              <br />v kraji.
            </>
          )}
        </h1>
        <p>Otevřená data Plzeňského kraje, na která se zeptáte běžnou češtinou.</p>
      </div>

      <main className="auth__card">
        <div className="seg" role="tablist" aria-label="Přihlášení nebo registrace">
          <span className="seg__thumb" data-pos={mode} aria-hidden="true" />
          <button
            type="button"
            role="tab"
            aria-selected={!isRegister}
            className="seg__btn"
            onClick={() => switchMode('login')}
          >
            Přihlásit se
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={isRegister}
            className="seg__btn"
            onClick={() => switchMode('register')}
          >
            Vytvořit účet
          </button>
        </div>

        <form className="auth__form" onSubmit={handleSubmit} noValidate>
          <h2 className="auth__title">{isRegister ? 'Nový účet' : 'Přihlášení'}</h2>

          <label className="field">
            <span className="field__label">Uživatelské jméno</span>
            <input
              name="username"
              maxLength={50}
              autoComplete="username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              required
            />
          </label>

          <div className={isRegister ? 'reveal reveal--open' : 'reveal'} aria-hidden={!isRegister}>
            <div className="reveal__inner">
              <div className="field-row">
                <label className="field">
                  <span className="field__label">Jméno</span>
                  <input
                    name="firstname"
                    maxLength={100}
                    autoComplete="given-name"
                    value={firstname}
                    onChange={(e) => setFirstname(e.target.value)}
                    required={isRegister}
                    tabIndex={isRegister ? 0 : -1}
                  />
                </label>
                <label className="field">
                  <span className="field__label">Příjmení</span>
                  <input
                    name="lastname"
                    maxLength={100}
                    autoComplete="family-name"
                    value={lastname}
                    onChange={(e) => setLastname(e.target.value)}
                    required={isRegister}
                    tabIndex={isRegister ? 0 : -1}
                  />
                </label>
              </div>
            </div>
          </div>

          <label className="field">
            <span className="field__label">Heslo</span>
            <span className="field__wrap">
              <input
                name="password"
                type={showPassword ? 'text' : 'password'}
                autoComplete={isRegister ? 'new-password' : 'current-password'}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                minLength={isRegister ? 8 : undefined}
                required
              />
              <button
                type="button"
                className="field__eye"
                aria-label={showPassword ? 'Skrýt heslo' : 'Zobrazit heslo'}
                onClick={() => setShowPassword((s) => !s)}
              >
                <Icon name={showPassword ? 'eyeOff' : 'eye'} size={18} />
              </button>
            </span>
            {isRegister && <span className="field__hint">Aspoň 8 znaků.</span>}
          </label>

          {error && (
            <p className="auth__error" role="alert">
              {error}
            </p>
          )}

          <button type="submit" className="auth__submit" disabled={loading}>
            {loading
              ? isRegister
                ? 'Zakládám účet…'
                : 'Přihlašuji…'
              : isRegister
                ? 'Vytvořit účet'
                : 'Přihlásit se'}
            {!loading && <Icon name="arrow" size={18} />}
          </button>

          <p className="auth__switch">
            {isRegister ? 'Už účet máte? ' : 'Ještě nemáte účet? '}
            <button
              type="button"
              className="text-link"
              onClick={() => switchMode(isRegister ? 'login' : 'register')}
            >
              {isRegister ? 'Přihlaste se' : 'Vytvořte si ho'}
            </button>
          </p>
        </form>
      </main>
    </div>
  )
}
