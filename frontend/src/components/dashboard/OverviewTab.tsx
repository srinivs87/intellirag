'use client'
import { Card } from '@/components/ui'
import { NAVY, ORANGE, BLUE } from '@/lib/constants'

interface OverviewTabProps {
  onNavigate: (tab: string) => void
}

export function OverviewTab({ onNavigate }: OverviewTabProps) {
  return (
    <div className="flex flex-col gap-5">
      <div>
        <h1 className="text-xl font-semibold" style={{ color: NAVY }}>Platform Overview</h1>
        <p className="text-sm text-slate-500 mt-1">
          IntelliRAG — on-premise AI knowledge platform. All data stays on your servers.
        </p>
      </div>

      <div className="grid grid-cols-4 gap-3">
        {[
          ['Knowledge base', 'General'],
          ['LLM', 'Groq / Llama 3.3'],
          ['Memory', '7-day sessions'],
          ['Data leakage', 'Zero', '#10B981'],
        ].map(([label, value, color]) => (
          <Card key={label as string} className="p-4">
            <div className="text-xs text-slate-400 mb-1">{label}</div>
            <div className="text-xl font-semibold" style={{ color: (color as string) || NAVY }}>{value}</div>
          </Card>
        ))}
      </div>

      <Card className="p-5">
        <div className="flex items-center gap-2 mb-4">
          <div className="w-1 h-5 rounded" style={{ background: ORANGE }} />
          <span className="font-semibold" style={{ color: NAVY }}>Quick start</span>
        </div>
        {[
          ['Upload Docs', 'Upload PDF, Word, or Excel documents to the knowledge base'],
          ['Connectors', 'Connect Google Drive, SharePoint, or Teams for automatic sync'],
          ['Try It', 'Test the AI assistant with your actual documents'],
        ].map(([t, d], i) => (
          <div key={t as string} className={`flex items-center gap-3 py-2.5 ${i < 2 ? 'border-b border-slate-100' : ''}`}>
            <div className="w-5 h-5 rounded-full text-white text-xs font-bold flex items-center justify-center" style={{ background: NAVY }}>
              {i + 1}
            </div>
            <span className="text-sm text-slate-600 flex-1">{d} —</span>
            <button
              onClick={() => onNavigate(t as string)}
              className="text-sm font-medium underline cursor-pointer"
              style={{ color: BLUE, background: 'none', border: 'none' }}
            >
              {t}
            </button>
          </div>
        ))}
      </Card>

      <div className="rounded-xl p-4 text-white text-sm" style={{ background: NAVY }}>
        ACL Digital IntelliRAG — Powered by Llama 3.3 + Groq + Qdrant. Search across Google Drive, SharePoint, Teams, and uploaded documents in one place.
        <div className="flex h-0.5 mt-3 rounded overflow-hidden">
          <div className="w-[65%]" style={{ background: ORANGE }} />
          <div className="w-[35%]" style={{ background: BLUE }} />
        </div>
      </div>
    </div>
  )
}
