'use client'
import { SOURCE_CONFIG } from '@/lib/constants'
import { SourceKey } from '@/types/connector'

interface SourcePillsProps {
  availableSources: SourceKey[]
  activeSource: SourceKey
  onSelect: (source: SourceKey) => void
}

const SOURCE_ICONS: Record<string, string> = {
  uploaded:   '📁',
  gdrive:     '📂',
  localfs:    '💻',
  teams:      '💬',
  sharepoint: '🔷',
  onedrive:   '☁️',
}

export function SourcePills({ availableSources, activeSource, onSelect }: SourcePillsProps) {
  return (
    <div className="flex items-center gap-1.5 flex-wrap">
      <span className="text-xs text-slate-400 font-medium mr-1">Source:</span>
      {availableSources.map((key) => {
        const cfg = SOURCE_CONFIG[key]
        if (!cfg) return null
        const active = activeSource === key
        return (
          <button
            key={key}
            onClick={() => onSelect(key)}
            className={[
              'inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold',
              'transition-all duration-150 cursor-pointer border',
              active
                ? 'shadow-sm'
                : 'bg-white border-slate-200 text-slate-500 hover:border-slate-300 hover:text-slate-700',
            ].join(' ')}
            style={active ? {
              background: cfg.bg,
              borderColor: cfg.border,
              color: cfg.color,
            } : {}}
          >
            <span>{SOURCE_ICONS[key] || '📄'}</span>
            {cfg.label}
            {active && (
              <span
                className="w-1.5 h-1.5 rounded-full"
                style={{ background: cfg.color }}
              />
            )}
          </button>
        )
      })}
    </div>
  )
}
