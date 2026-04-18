'use client'
import { useState, FormEvent } from 'react'
import { CreateUserPayload, UserRole } from '@/types/user'
import { Input } from '@/components/ui'
import { Button } from '@/components/ui/Button'
import { NAVY } from '@/lib/constants'

interface CreateUserModalProps {
  onSave: (payload: CreateUserPayload) => Promise<void>
  onClose: () => void
}

const INITIAL_FORM: CreateUserPayload = { name: '', email: '', password: '', role: 'user' }

export function CreateUserModal({ onSave, onClose }: CreateUserModalProps) {
  const [form, setForm] = useState<CreateUserPayload>(INITIAL_FORM)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    if (!form.name || !form.email || !form.password) {
      setError('All fields are required')
      return
    }
    if (form.password.length < 6) {
      setError('Password must be at least 6 characters')
      return
    }
    setLoading(true)
    setError('')
    try {
      await onSave(form)
      onClose()
    } catch (err: any) {
      setError(err.message || 'Failed to create user')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="bg-white border border-slate-200 rounded-xl p-6 mb-4">
      <h3 className="text-base font-semibold mb-4" style={{ color: NAVY }}>Create New User</h3>
      <form onSubmit={handleSubmit} className="flex flex-col gap-3">
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="block text-xs font-semibold mb-1" style={{ color: NAVY }}>Full Name</label>
            <Input placeholder="John Smith" value={form.name} onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))} />
          </div>
          <div>
            <label className="block text-xs font-semibold mb-1" style={{ color: NAVY }}>Email</label>
            <Input type="email" placeholder="john@company.com" value={form.email} onChange={(e) => setForm((f) => ({ ...f, email: e.target.value }))} />
          </div>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="block text-xs font-semibold mb-1" style={{ color: NAVY }}>Password</label>
            <Input type="password" placeholder="Min 6 characters" value={form.password} onChange={(e) => setForm((f) => ({ ...f, password: e.target.value }))} />
          </div>
          <div>
            <label className="block text-xs font-semibold mb-1" style={{ color: NAVY }}>Role</label>
            <select
              value={form.role}
              onChange={(e) => setForm((f) => ({ ...f, role: e.target.value as UserRole }))}
              className="w-full border border-slate-200 rounded-lg px-3 py-2.5 text-sm bg-slate-50 outline-none text-slate-700"
            >
              <option value="user">User — Overview + Try It</option>
              <option value="viewer">Viewer — Try It only</option>
              <option value="admin">Admin — Full access</option>
            </select>
          </div>
        </div>

        {error && (
          <div className="p-2.5 bg-red-50 border border-red-200 rounded-lg text-xs text-red-700">{error}</div>
        )}

        <div className="flex gap-2 mt-1">
          <Button type="submit" disabled={loading}>{loading ? 'Creating...' : 'Create User'}</Button>
          <Button type="button" variant="secondary" onClick={onClose}>Cancel</Button>
        </div>
      </form>
    </div>
  )
}
