import { createContext, useContext } from 'react'
import type { RegisterData, User } from './types'

export type AuthContextValue = {
  user: User | null
  isLoading: boolean
  login: (username: string, password: string) => Promise<void>
  register: (data: RegisterData) => Promise<void>
  logout: () => void
}

export const AuthContext = createContext<AuthContextValue | null>(null)

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth musí být uvnitř <AuthProvider>')
  return ctx
}
