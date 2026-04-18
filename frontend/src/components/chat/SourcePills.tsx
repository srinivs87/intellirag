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
    <div className="flex gap-1.5 flex-wrap items-center">
      <span className="text-xs text-white/40 shrink-0">Search in:</span>
      {availableSources.map((key) => {
        const cfg = SOURCE_CONFIG[key]
        if (!cfg) return null
        const active = activeSources.includes(key)
        return (
          <button
            key={key}
            onClick={() => onToggle(key)}
            className={`
              inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold
              transition-all duration-150 border cursor-pointer
              ${active
                ? 'bg-white/15 border-white/30 text-white'
                : 'bg-transparent border-white/10 text-white/30 hover:border-white/20 hover:text-white/50'
              }
            `}
          >
            {active && <span className="text-emerald-400 text-[9px]">✓</span>}
            {cfg.label}
          </button>
        )
      })}
      <span className="text-xs text-white/30 ml-1">{activeSources.length} selected</span>
    </div>
  )
}
