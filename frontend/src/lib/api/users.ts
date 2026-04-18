import { API_BASE } from './client'
import { AppUser, CreateUserPayload } from '@/types/user'

function authHeaders(token: string) {
  return { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` }
}

export async function listUsers(token: string): Promise<AppUser[]> {
  const res = await fetch(`${API_BASE}/api/auth/users`, { headers: authHeaders(token) })
  if (!res.ok) throw new Error('Failed to fetch users')
  return res.json()
}

export async function createUser(payload: CreateUserPayload, token: string): Promise<void> {
  const res = await fetch(`${API_BASE}/api/auth/register`, {
    method: 'POST',
    headers: authHeaders(token),
    body: JSON.stringify(payload),
  })
  const data = await res.json()
  if (!res.ok) throw new Error(data.detail || 'Failed to create user')
}

export async function updateUserRole(userId: string, role: string, token: string): Promise<void> {
  await fetch(`${API_BASE}/api/auth/users/${userId}/role`, {
    method: 'PATCH',
    headers: authHeaders(token),
    body: JSON.stringify({ role }),
  })
}

export async function updateUserConnectors(userId: string, connectors: string[], token: string): Promise<void> {
  await fetch(`${API_BASE}/api/auth/users/${userId}/connectors`, {
    method: 'PATCH',
    headers: authHeaders(token),
    body: JSON.stringify({ connectors }),
  })
}

export async function deactivateUser(userId: string, token: string): Promise<void> {
  await fetch(`${API_BASE}/api/auth/users/${userId}`, {
    method: 'DELETE',
    headers: authHeaders(token),
  })
}
