'use client'
import { NAVY, ORANGE, BLUE, ROLE_COLORS } from '@/lib/constants'
import { AuthUser } from '@/types/auth'

interface HeaderProps {
  user: AuthUser | null
  health: string
  onLogout: () => void
}

export function Header({ user, health, onLogout }: HeaderProps) {
  return (
    <header style={{ background: NAVY }}>
      <div className="flex items-center gap-4 px-6 py-2.5">
        <img src="/acl-logo.png" alt="ACL Digital" className="h-9 w-auto" />
        <div className="w-px h-7 bg-white/20 mx-2" />
        <span className="text-white font-semibold text-lg">IntelliRAG</span>

        {user && (
          <span
            className="text-xs font-bold text-white px-2.5 py-0.5 rounded-full"
            style={{ background: ROLE_COLORS[user.role] || '#94A3B8' }}
          >
            {user.role.charAt(0).toUpperCase() + user.role.slice(1)}
          </span>
        )}

        <div className="ml-auto flex items-center gap-4 text-sm text-white/60">
          <div className="flex items-center gap-2">
            <div className={`w-2 h-2 rounded-full ${health === 'ok' ? 'bg-emerald-400' : 'bg-red-400'}`} />
            <span>API: {health}</span>
          </div>

          {user && (
            <div className="flex items-center gap-3 pl-4 border-l border-white/15">
              <span className="text-white/80 text-sm">{user.name}</span>
              <button
                onClick={onLogout}
                className="text-xs px-3 py-1.5 rounded-md bg-white/10 border border-white/20 text-white/60 hover:bg-white/20 transition-all"
              >
                Sign out
              </button>
            </div>
          )}
        </div>
      </div>

      {/* Brand stripe */}
      <div className="flex h-0.5">
        <div className="w-[65%]" style={{ background: ORANGE }} />
        <div className="w-[35%]" style={{ background: BLUE }} />
      </div>
    </header>
  )
}
