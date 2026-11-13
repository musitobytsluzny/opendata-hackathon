import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'
import { UNAUTHORIZED_EVENT } from '../api/client'
import { AuthContext } from './AuthContext'
import { authService } from './authService'
import { decodeJwt } from './jwt'
import { tokenStorage } from './tokenStorage'
import type { RegisterData, User } from './types'

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [isLoading, setIsLoading] = useState(() => Boolean(tokenStorage.get()))

  const login = useCallback(async (username: string, password: string) => {
    setUser(await authService.login(username, password))
    setIsLoading(false)
  }, [])

  const register = useCallback(async (data: RegisterData) => {
    setUser(await authService.register(data))
    setIsLoading(false)
  }, [])

  const logout = useCallback(() => {
    authService.logout()
    setUser(null)
  }, [])

  useEffect(() => {
    let request: AbortController | undefined
    const refresh = () => {
      request?.abort()
      request = new AbortController()
      const signal = request.signal
      const token = tokenStorage.get()
      void authService
        .restoreSession(signal)
        .then((restored) => {
          if (!signal.aborted && tokenStorage.get() === token) setUser(restored)
        })
        .catch(() => {
          if (!signal.aborted && tokenStorage.get() === token) setUser(null)
        })
        .finally(() => {
          if (!signal.aborted) setIsLoading(false)
        })
    }
    const onStorage = (event: StorageEvent) => {
      if (event.key === 'auth_token' || event.key === null) refresh()
    }
    const onUnauthorized = () => setUser(null)
    refresh()
    window.addEventListener('storage', onStorage)
    window.addEventListener(UNAUTHORIZED_EVENT, onUnauthorized)
    return () => {
      request?.abort()
      window.removeEventListener('storage', onStorage)
      window.removeEventListener(UNAUTHORIZED_EVENT, onUnauthorized)
    }
  }, [])

  useEffect(() => {
    if (!user) return
    const token = tokenStorage.get()
    const payload = token ? decodeJwt(token) : null
    if (!payload) return
    const timeout = window.setTimeout(logout, Math.max(0, payload.exp * 1000 - Date.now()))
    return () => window.clearTimeout(timeout)
  }, [user, logout])

  const value = useMemo(
    () => ({ user, isLoading, login, register, logout }),
    [user, isLoading, login, register, logout],
  )
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
