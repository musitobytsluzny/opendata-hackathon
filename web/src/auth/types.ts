export type LoginRequest = {
  username: string
  password: string
}

export type RegisterRequest = {
  username: string
  email: string
  password: string
}

export type LoginResponse = {
  token: string
}

export type User = {
  id: string
  username: string
}
