import { useState, useEffect, useCallback } from 'react'
import { AppUser, CreateUserPayload } from '@/types/user'
import { listUsers, createUser, updateUserRole, updateUserConnectors, deactivateUser } from '@/lib/api/users'
import { AUTH_KEY } from '@/lib/constants'

function getToken(): string {
  try { return JSON.parse(localStorage.getItem(AUTH_KEY) || '{}').token || '' } catch { return '' }
}

export function useUsers() {
  const [users, setUsers] = useState<AppUser[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const data = await listUsers(getToken())
      setUsers(data)
    } catch (e: any) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  async function create(payload: CreateUserPayload) {
    await createUser(payload, getToken())
    await load()
  }

  async function updateRole(userId: string, role: string) {
    await updateUserRole(userId, role, getToken())
    await load()
  }

  async function updateConnectors(userId: string, connectors: string[]) {
    await updateUserConnectors(userId, connectors, getToken())
    await load()
  }

  async function disable(userId: string) {
    await deactivateUser(userId, getToken())
    await load()
  }

  return { users, loading, error, load, create, updateRole, updateConnectors, disable }
}
