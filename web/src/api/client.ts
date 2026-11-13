import { tokenStorage } from '../auth/tokenStorage'

export const API_URL = import.meta.env.VITE_API_URL ?? ''

export const UNAUTHORIZED_EVENT = 'auth:unauthorized'

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

export async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers)
  if (init.body && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }

  const token = tokenStorage.get()
  if (token) {
    headers.set('Authorization', `Bearer ${token}`)
  }

  const res = await fetch(`${API_URL}${path}`, { ...init, headers })

  if (res.status === 401) {
    tokenStorage.clear()
    window.dispatchEvent(new Event(UNAUTHORIZED_EVENT))
    throw new ApiError(401, 'Nepřihlášen')
  }

  if (!res.ok) {
    const text = await res.text().catch(() => '')
    throw new ApiError(res.status, text || res.statusText)
  }

  if (res.status === 204) return undefined as T
  return (await res.json()) as T
}
