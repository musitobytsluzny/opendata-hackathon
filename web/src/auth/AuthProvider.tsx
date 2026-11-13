import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'
import { UNAUTHORIZED_EVENT } from '../api/client'
import { AuthContext } from './AuthContext'
import { authService } from './authService'
import type { User } from './types'

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(() => authService.getCurrentUser())

  const login = useCallback(async (username: string, password: string) => {
    setUser(await authService.login(username, password))
  }, [])

  const register = useCallback(async (username: string, email: string, password: string) => {
    setUser(await authService.register(username, email, password))
  }, [])

  const logout = useCallback(() => {
    authService.logout()
    setUser(null)
  }, [])

  useEffect(() => {
    const onUnauthorized = () => setUser(null)
    window.addEventListener(UNAUTHORIZED_EVENT, onUnauthorized)
    return () => window.removeEventListener(UNAUTHORIZED_EVENT, onUnauthorized)
  }, [])

  const value = useMemo(() => ({ user, login, register, logout }), [user, login, register, logout])

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
