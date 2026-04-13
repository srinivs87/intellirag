'use client'
import { NAVY, ORANGE } from '@/lib/constants'

const TABS = ['Overview', 'Upload Docs', 'Analytics', 'Connectors', 'Integration', 'Try It']

interface TabNavProps {
  activeTab: string
  onTabChange: (tab: string) => void
}

export function TabNav({ activeTab, onTabChange }: TabNavProps) {
  return (
    <div className="bg-white border-b border-[#E2E8F2] px-6 flex gap-1">
      {TABS.map((tab) => (
        <button
          key={tab}
          onClick={() => onTabChange(tab)}
          className="px-4 py-3 text-sm font-medium transition-colors duration-150"
          style={{
            color: activeTab === tab ? NAVY : '#64748B',
            borderBottom: `2px solid ${activeTab === tab ? ORANGE : 'transparent'}`,
          }}
        >
          {tab}
        </button>
      ))}
    </div>
  )
}
