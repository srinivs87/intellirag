import { useEffect } from 'react'
import { useAuthStore } from '@/store/authStore'
import { login as apiLogin } from '@/lib/api/auth'
import { AuthUser } from '@/types/auth'
import { ALL_SOURCES } from '@/lib/constants'
import { SourceKey } from '@/types/connector'

export function useAuth() {
  const { user, token, isReady, setAuth, clearAuth, loadFromStorage } = useAuthStore()

  useEffect(() => {
    loadFromStorage()
  }, [])

  async function login(email: string, password: string) {
    const { user: u, token: t } = await apiLogin(email, password)
    setAuth(u, t)
    return u
  }

  function logout() {
    clearAuth()
  }

  function getAllowedSources(): SourceKey[] {
    if (!user) return []
    if (user.role === 'admin') return ALL_SOURCES
    return (user.connectors as SourceKey[]) ?? ['uploaded', 'gdrive', 'localfs']
  }

  return { user, token, isReady, login, logout, getAllowedSources }
}
