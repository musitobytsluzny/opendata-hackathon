export type LoginRequest = {
  username: string
  password: string
}

export type LoginResponse = {
  access_token: string
  token_type: string
}

export type User = {
  id: string
  username: string
}
