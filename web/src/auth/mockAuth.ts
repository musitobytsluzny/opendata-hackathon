import { base64UrlEncode } from './jwt'
import type { LoginResponse } from './types'

const MOCK_USERS = [{ id: '1', username: 'username', password: 'password' }]

const TOKEN_TTL_SECONDS = 60 * 60

function createMockJwt(userId: string, username: string): string {
  const now = Math.floor(Date.now() / 1000)
  const header = base64UrlEncode(JSON.stringify({ alg: 'none', typ: 'JWT' }))
  const payload = base64UrlEncode(
    JSON.stringify({ sub: userId, username, iat: now, exp: now + TOKEN_TTL_SECONDS }),
  )
  return `${header}.${payload}.mock-signature`
}

export async function mockLogin(username: string, password: string): Promise<LoginResponse> {
  await new Promise((r) => setTimeout(r, 300))

  const user = MOCK_USERS.find((u) => u.username === username && u.password === password)
  if (!user) {
    throw new Error('Neplatné uživatelské jméno nebo heslo')
  }
  return { access_token: createMockJwt(user.id, user.username), token_type: 'bearer' }
}
