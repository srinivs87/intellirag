'use client'
import { AppUser, ROLE_COLORS, UserRole } from '@/types/user'
import { Badge } from '@/components/ui'
import { Button } from '@/components/ui/Button'
import { NAVY } from '@/lib/constants'

interface UserTableProps {
  users: AppUser[]
  currentUserId: string
  loading: boolean
  onRoleChange: (userId: string, role: string) => void
  onAccessClick: (user: AppUser) => void
  onDisable: (userId: string) => void
}

export function UserTable({
  users, currentUserId, loading, onRoleChange, onAccessClick, onDisable,
}: UserTableProps) {
  if (loading) {
    return <div className="text-center py-16 text-slate-400 text-sm">Loading users...</div>
  }

  return (
    <div className="bg-white rounded-xl border border-slate-200 overflow-hidden">
      <table className="w-full border-collapse">
        <thead>
          <tr className="bg-slate-50 border-b border-slate-200">
            {['Name', 'Email', 'Role', 'Status', 'Last Login', 'Actions'].map((h) => (
              <th key={h} className="px-4 py-3 text-left text-xs font-bold text-slate-500 uppercase tracking-wide">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {users.length === 0 && (
            <tr>
              <td colSpan={6} className="text-center py-12 text-slate-400 text-sm">No users found</td>
            </tr>
          )}
          {users.map((user) => (
            <tr key={user.id} className="border-b border-slate-100 last:border-0 hover:bg-slate-50">
              <td className="px-4 py-3 text-sm font-medium" style={{ color: NAVY }}>{user.name}</td>
              <td className="px-4 py-3 text-sm text-slate-500">{user.email}</td>
              <td className="px-4 py-3">
                {user.id === currentUserId ? (
                  <span
                    className="text-xs font-bold text-white px-2 py-0.5 rounded capitalize"
                    style={{ background: ROLE_COLORS[user.role as UserRole] }}
                  >
                    {user.role}
                  </span>
                ) : (
                  <select
                    value={user.role}
                    onChange={(e) => onRoleChange(user.id, e.target.value)}
                    className="border border-slate-200 rounded-md px-2 py-1 text-xs text-slate-700 bg-slate-50 cursor-pointer"
                  >
                    <option value="admin">Admin</option>
                    <option value="user">User</option>
                    <option value="viewer">Viewer</option>
                  </select>
                )}
              </td>
              <td className="px-4 py-3">
                <Badge variant={user.is_active ? 'success' : 'error'}>
                  {user.is_active ? 'Active' : 'Inactive'}
                </Badge>
              </td>
              <td className="px-4 py-3 text-xs text-slate-400">
                {user.last_login ? new Date(user.last_login).toLocaleDateString() : 'Never'}
              </td>
              <td className="px-4 py-3">
                <div className="flex gap-2">
                  <Button size="sm" variant="secondary" onClick={() => onAccessClick(user)}>
                    Access
                  </Button>
                  {user.id !== currentUserId && (
                    <Button size="sm" variant="danger" onClick={() => onDisable(user.id)}>
                      Disable
                    </Button>
                  )}
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
