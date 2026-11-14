import { lazy, Suspense, useEffect } from 'react'
import { useAuth } from './auth/AuthContext'
import { AuthProvider } from './auth/AuthProvider'
import { Loader } from './components/Loader'
import { navigate, routes, usePath } from './router/router'

const pages = {
  landing: () => import('./pages/LandingPage'),
  login: () => import('./pages/LoginPage'),
  map: () => import('./pages/MapPage'),
}
const LandingPage = lazy(() => pages.landing().then((m) => ({ default: m.LandingPage })))
const LoginPage = lazy(() => pages.login().then((m) => ({ default: m.LoginPage })))
const MapPage = lazy(() => pages.map().then((m) => ({ default: m.MapPage })))

import('./map/RegionMap').catch(() => {})

function warmRoutes() {
  for (const load of Object.values(pages)) load().catch(() => {})
}

function Routes() {
  const path = usePath()
  const { user, isLoading } = useAuth()

  const target =
    !isLoading && path === routes.map && !user
      ? routes.login
      : path === routes.login && user
        ? routes.map
        : null

  useEffect(() => {
    if (target) navigate(target, true)
  }, [target])

  if (isLoading || target) return <Loader label="Ověřuji přihlášení…" />
  if (path === routes.map) return <MapPage key={user?.id} />
  if (path === routes.login) return <LoginPage />
  return <LandingPage />
}

export default function App() {
  useEffect(() => {
    const idle = window.requestIdleCallback
    if (idle) {
      const id = idle(warmRoutes, { timeout: 4000 })
      return () => window.cancelIdleCallback(id)
    }
    const id = window.setTimeout(warmRoutes, 2000)
    return () => window.clearTimeout(id)
  }, [])

  return (
    <AuthProvider>
      <Suspense fallback={<Loader />}>
        <Routes />
      </Suspense>
    </AuthProvider>
  )
}
