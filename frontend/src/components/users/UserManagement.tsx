'use client'
import { useState } from 'react'
import { AppUser } from '@/types/user'
import { useUsers } from '@/hooks/useUsers'
import { UserTable } from './UserTable'
import { CreateUserModal } from './CreateUserModal'
import { ConnectorAccessModal } from './ConnectorAccessModal'
import { Button } from '@/components/ui/Button'
import { NAVY } from '@/lib/constants'

interface UserManagementProps {
  currentUserId: string
}

export function UserManagement({ currentUserId }: UserManagementProps) {
  const { users, loading, error, create, updateRole, updateConnectors, disable } = useUsers()
  const [showCreate, setShowCreate] = useState(false)
  const [accessUser, setAccessUser] = useState<AppUser | null>(null)
  const [successMsg, setSuccessMsg] = useState('')

  function showSuccess(msg: string) {
    setSuccessMsg(msg)
    setTimeout(() => setSuccessMsg(''), 3000)
  }

  async function handleCreate(payload: any) {
    await create(payload)
    showSuccess('User created successfully!')
    setShowCreate(false)
  }

  async function handleRoleChange(userId: string, role: string) {
    await updateRole(userId, role)
    showSuccess('Role updated!')
  }

  async function handleConnectors(userId: string, connectors: string[]) {
    await updateConnectors(userId, connectors)
    showSuccess('Connector access updated!')
    setAccessUser(null)
  }

  async function handleDisable(userId: string) {
    if (!confirm('Disable this user? They will lose access immediately.')) return
    await disable(userId)
    showSuccess('User disabled.')
  }

  return (
    <div className="flex flex-col gap-5">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold" style={{ color: NAVY }}>User Management</h1>
          <p className="text-sm text-slate-500 mt-1">
            Create users, assign roles and manage connector access
          </p>
        </div>
        <Button onClick={() => { setShowCreate(true) }} disabled={showCreate}>
          + New User
        </Button>
      </div>

      {/* Role legend */}
      <div className="flex gap-3 text-xs">
        {[
          { role: 'Admin', desc: 'All tabs + User Management', color: '#F59E0B' },
          { role: 'User', desc: 'Overview + Try It', color: '#10B981' },
          { role: 'Viewer', desc: 'Try It only', color: '#94A3B8' },
        ].map((r) => (
          <div key={r.role} className="flex items-center gap-1.5 px-3 py-1.5 bg-white border border-slate-200 rounded-lg">
            <span className="w-2 h-2 rounded-full" style={{ background: r.color }} />
            <span className="font-semibold text-slate-700">{r.role}:</span>
            <span className="text-slate-500">{r.desc}</span>
          </div>
        ))}
      </div>

      {/* Feedback */}
      {successMsg && (
        <div className="p-3 bg-emerald-50 border border-emerald-200 rounded-lg text-sm text-emerald-700 font-medium">
          ✓ {successMsg}
        </div>
      )}
      {error && (
        <div className="p-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700">{error}</div>
      )}

      {/* Modals */}
      {showCreate && (
        <CreateUserModal onSave={handleCreate} onClose={() => setShowCreate(false)} />
      )}
      {accessUser && (
        <ConnectorAccessModal
          user={accessUser}
          onSave={handleConnectors}
          onClose={() => setAccessUser(null)}
        />
      )}

      {/* Table */}
      <UserTable
        users={users}
        currentUserId={currentUserId}
        loading={loading}
        onRoleChange={handleRoleChange}
        onAccessClick={setAccessUser}
        onDisable={handleDisable}
      />
    </div>
  )
}
