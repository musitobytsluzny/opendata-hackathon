import { ApiError, apiFetch } from '../api/client'
import { decodeJwt, isExpired } from './jwt'
import { mockLogin, mockRegister } from './mockAuth'
import { tokenStorage } from './tokenStorage'
import type { LoginRequest, LoginResponse, RegisterData, RegisterRequest, User } from './types'

const USE_MOCK = import.meta.env.VITE_USE_MOCK_AUTH !== 'false'

export const authService = {
  async login(username: string, password: string): Promise<User> {
    const body: LoginRequest = { username, password }
    const { access_token: token } = USE_MOCK
      ? await mockLogin(username, password)
      : await apiFetch<LoginResponse>('/auth/login', {
          method: 'POST',
          body: JSON.stringify(body),
        })

    return this.acceptToken(token)
  },

  async register(data: RegisterData): Promise<User> {
    if (USE_MOCK) {
      const { access_token: token } = await mockRegister(data)
      return this.acceptToken(token)
    }
    const body: RegisterRequest = {
      username: data.username,
      password: data.password,
      profile: { firstname: data.firstname, lastname: data.lastname },
    }
    try {
      await apiFetch('/users/', { method: 'POST', body: JSON.stringify(body) })
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        throw new Error('Toto uživatelské jméno už někdo používá')
      }
      throw err
    }
    return this.login(data.username, data.password)
  },

  acceptToken(token: string): User {
    tokenStorage.set(token)
    const user = this.getCurrentUser()
    if (!user) {
      tokenStorage.clear()
      throw new Error('Server vrátil neplatný token')
    }
    return user
  },

  logout(): void {
    tokenStorage.clear()
  },

  getCurrentUser(): User | null {
    const token = tokenStorage.get()
    if (!token) return null

    const payload = decodeJwt(token)
    if (!payload || isExpired(payload)) {
      tokenStorage.clear()
      return null
    }
    return { id: payload.sub, username: payload.username }
  },
}
