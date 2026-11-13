import { useAuth } from './auth/AuthContext'
import { AuthProvider } from './auth/AuthProvider'
import { RequireAuth } from './auth/RequireAuth'
import { tokenStorage } from './auth/tokenStorage'
import { LoginPage } from './pages/LoginPage'

function Home() {
  const { user, logout } = useAuth()
  return (
    <div>
      <p>Přihlášen jako: {user?.username}</p>
      <p>Token:</p>
      <pre style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-all' }}>{tokenStorage.get()}</pre>
      <button onClick={logout}>Odhlásit</button>
    </div>
  )
}

export default function App() {
  return (
    <AuthProvider>
      <RequireAuth fallback={<LoginPage />}>
        <Home />
      </RequireAuth>
    </AuthProvider>
  )
}
