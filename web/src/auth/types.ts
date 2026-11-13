export type LoginRequest = {
  username: string
  password: string
}

export type RegisterData = {
  username: string
  firstname: string
  lastname: string
  password: string
}

export type RegisterRequest = {
  username: string
  password: string
  profile: { firstname: string; lastname: string }
}

export type LoginResponse = {
  access_token: string
  token_type: string
}

export type User = {
  id: string
  username: string
}
