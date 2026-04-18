export type UserRole = 'admin' | 'user' | 'viewer'

export interface AppUser {
  id: string
  email: string
  name: string
  role: UserRole
  is_active: boolean
  created_at: string
  last_login?: string
}

export interface CreateUserPayload {
  name: string
  email: string
  password: string
  role: UserRole
}

export const ROLE_TAB_MAP: Record<UserRole, string[]> = {
  admin:  ['Overview', 'Upload Docs', 'Analytics', 'Connectors', 'Integration', 'Try It', 'Users'],
  user:   ['Overview', 'Try It'],
  viewer: ['Try It'],
}

export const ALL_CONNECTORS = ['uploaded', 'gdrive', 'localfs', 'teams', 'sharepoint', 'onedrive']

export const ROLE_COLORS: Record<UserRole, string> = {
  admin:  '#F59E0B',
  user:   '#10B981',
  viewer: '#94A3B8',
}
