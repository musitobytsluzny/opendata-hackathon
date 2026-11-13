import { lazy, Suspense, useEffect } from 'react'
import { useAuth } from './auth/AuthContext'
import { AuthProvider } from './auth/AuthProvider'
const LandingPage = lazy(() =>
  import('./pages/LandingPage').then((m) => ({ default: m.LandingPage })),
)
const LoginPage = lazy(() => import('./pages/LoginPage').then((m) => ({ default: m.LoginPage })))
const MapPage = lazy(() => import('./pages/MapPage').then((m) => ({ default: m.MapPage })))
import { navigate, routes, usePath } from './router/router'

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

  if (isLoading || target)
    return (
      <div className="app-loading" role="status">
        Ověřuji přihlášení…
      </div>
    )
  if (path === routes.map) return <MapPage key={user?.id} />
  if (path === routes.login) return <LoginPage />
  return <LandingPage />
}

export default function App() {
  return (
    <AuthProvider>
      <Suspense
        fallback={
          <div className="app-loading" role="status">
            Načítám…
          </div>
        }
      >
        <Routes />
      </Suspense>
    </AuthProvider>
  )
}
