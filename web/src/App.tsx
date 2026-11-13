import { useEffect } from 'react'
import { useAuth } from './auth/AuthContext'
import { AuthProvider } from './auth/AuthProvider'
import { LandingPage } from './pages/LandingPage'
import { LoginPage } from './pages/LoginPage'
import { MapPage } from './pages/MapPage'
import { navigate, routes, usePath } from './router/router'

function Routes() {
  const path = usePath()
  const { user } = useAuth()

  const target =
    path === routes.map && !user ? routes.login : path === routes.login && user ? routes.map : null

  useEffect(() => {
    if (target) navigate(target, true)
  }, [target])

  if (target) return null
  if (path === routes.map) return <MapPage />
  if (path === routes.login) return <LoginPage />
  return <LandingPage />
}

export default function App() {
  return (
    <AuthProvider>
      <Routes />
    </AuthProvider>
  )
}
