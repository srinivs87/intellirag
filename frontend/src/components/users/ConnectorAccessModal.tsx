'use client'
import { useState } from 'react'
import { AppUser, ALL_CONNECTORS } from '@/types/user'
import { Button } from '@/components/ui/Button'
import { SOURCE_CONFIG } from '@/lib/constants'
import { SourceKey } from '@/types/connector'
import { NAVY } from '@/lib/constants'

interface ConnectorAccessModalProps {
  user: AppUser
  onSave: (userId: string, connectors: string[]) => Promise<void>
  onClose: () => void
}

export function ConnectorAccessModal({ user, onSave, onClose }: ConnectorAccessModalProps) {
  const [selected, setSelected] = useState<string[]>(
    user.role === 'admin' ? ALL_CONNECTORS : ['uploaded', 'gdrive', 'localfs']
  )
  const [loading, setLoading] = useState(false)

  function toggle(connector: string) {
    setSelected((prev) =>
      prev.includes(connector) ? prev.filter((c) => c !== connector) : [...prev, connector]
    )
  }

  async function handleSave() {
    setLoading(true)
    try {
      await onSave(user.id, selected)
      onClose()
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="bg-white border border-slate-200 rounded-xl p-6 mb-4">
      <div className="mb-4">
        <h3 className="text-base font-semibold" style={{ color: NAVY }}>
          Connector Access — {user.name}
        </h3>
        <p className="text-xs text-slate-500 mt-1">Select which sources this user can search in the chat widget</p>
      </div>

      <div className="grid grid-cols-3 gap-2 mb-5">
        {ALL_CONNECTORS.map((key) => {
          const cfg = SOURCE_CONFIG[key as SourceKey]
          const active = selected.includes(key)
          return (
            <label
              key={key}
              className="flex items-center gap-2 px-3 py-2.5 rounded-lg border cursor-pointer transition-all"
              style={{
                border: `1px solid ${active ? cfg.border : '#E2E8F2'}`,
                background: active ? cfg.bg : '#F5F7FA',
              }}
            >
              <input
                type="checkbox"
                checked={active}
                onChange={() => toggle(key)}
                className="accent-emerald-600"
              />
              <span className="text-xs font-medium" style={{ color: active ? cfg.color : '#64748B' }}>
                {cfg.label}
              </span>
            </label>
          )
        })}
      </div>

      <div className="flex gap-2">
        <Button onClick={handleSave} disabled={loading}>
          {loading ? 'Saving...' : 'Save Access'}
        </Button>
        <Button variant="secondary" onClick={onClose}>Cancel</Button>
      </div>
    </div>
  )
}
