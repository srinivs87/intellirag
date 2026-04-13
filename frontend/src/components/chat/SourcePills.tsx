'use client'
import { SOURCE_CONFIG } from '@/lib/constants'
import { SourceKey } from '@/types/connector'

interface SourcePillsProps {
  availableSources: SourceKey[]
  activeSources: SourceKey[]
  onToggle: (source: SourceKey) => void
}

export function SourcePills({ availableSources, activeSources, onToggle }: SourcePillsProps) {
  return (
    <div className="flex gap-1.5 px-3 py-1.5 flex-wrap bg-[#0A0F5C]">
      <span className="text-xs text-white/50 self-center shrink-0">Search in:</span>
      {availableSources.map((key) => {
        const cfg = SOURCE_CONFIG[key]
        if (!cfg) return null
        const active = activeSources.includes(key)
        return (
          <button
            key={key}
            onClick={() => onToggle(key)}
            className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold transition-all duration-150"
            style={{
              border: active ? `1.5px solid ${cfg.border}` : '1.5px solid rgba(255,255,255,0.15)',
              background: active ? cfg.bg : 'transparent',
              color: active ? cfg.color : 'rgba(255,255,255,0.3)',
              opacity: active ? 1 : 0.6,
            }}
          >
            {active && <span className="text-[9px]">✓</span>}
            {cfg.label}
          </button>
        )
      })}
      <span className="text-xs text-white/40 self-center ml-1">{activeSources.length} selected</span>
    </div>
  )
}
