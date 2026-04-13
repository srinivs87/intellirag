import { create } from 'zustand'
import { AuthUser } from '@/types/auth'
import { AUTH_KEY } from '@/lib/constants'

interface AuthStore {
  user: AuthUser | null
  token: string | null
  isReady: boolean
  setAuth: (user: AuthUser, token: string) => void
  clearAuth: () => void
  loadFromStorage: () => void
}

export const useAuthStore = create<AuthStore>((set) => ({
  user: null,
  token: null,
  isReady: false,

  loadFromStorage: () => {
    try {
      const stored = localStorage.getItem(AUTH_KEY)
      if (stored) {
        const { user, token } = JSON.parse(stored)
        set({ user, token, isReady: true })
      } else {
        set({ isReady: true })
      }
    } catch {
      set({ isReady: true })
    }
  },

  setAuth: (user, token) => {
    localStorage.setItem(AUTH_KEY, JSON.stringify({ user, token }))
    set({ user, token })
  },

  clearAuth: () => {
    localStorage.removeItem(AUTH_KEY)
    set({ user: null, token: null })
  },
}))
