export type UserRole = 'admin' | 'user' | 'viewer'

export interface AuthUser {
  id: string
  email: string
  name: string
  role: UserRole
  connectors: string[]
}

export interface AuthState {
  user: AuthUser | null
  token: string | null
}
