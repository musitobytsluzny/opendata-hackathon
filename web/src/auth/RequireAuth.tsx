import type { ReactNode } from 'react'
import { useAuth } from './AuthContext'

export function RequireAuth({ children, fallback }: { children: ReactNode; fallback: ReactNode }) {
  const { user } = useAuth()
  return user ? children : fallback
}
