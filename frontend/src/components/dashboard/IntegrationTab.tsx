'use client'
import { Card } from '@/components/ui'
import { NAVY, ORANGE, BLUE } from '@/lib/constants'

interface IntegrationTabProps {
  apiBase: string
  copied: boolean
  onCopy: () => void
}

export function IntegrationTab({ apiBase, copied, onCopy }: IntegrationTabProps) {
  const integrations = [
    {
      num: '1', title: 'Script tag — any HTML app', color: ORANGE, effort: '5 min',
      code: `<script\n  src="${apiBase}/widget.js"\n  data-tenant="general"\n></script>`,
      showCopy: true,
    },
    {
      num: '2', title: 'React component', color: BLUE, effort: '30 min',
      code: '<ChatWidget tenant="general" user={user} allowedSources={sources} />',
    },
    {
      num: '3', title: 'REST API', color: NAVY, effort: '1-2 hrs',
      code: 'POST /api/query/\n{ "tenant": "general", "question": "...", "sources": ["gdrive"] }',
    },
  ]

  return (
    <div className="flex flex-col gap-4">
      <div>
        <h1 className="text-xl font-semibold" style={{ color: NAVY }}>Integration Guide</h1>
        <p className="text-sm text-slate-500 mt-1">Embed IntelliRAG in any application — three ways</p>
      </div>

      {integrations.map((m) => (
        <Card key={m.num} className="p-5">
          <div className="flex items-center gap-3 mb-4">
            <div
              className="w-7 h-7 rounded-full text-white text-xs font-bold flex items-center justify-center"
              style={{ background: m.color }}
            >
              {m.num}
            </div>
            <span className="font-semibold flex-1" style={{ color: NAVY }}>{m.title}</span>
            <span className="text-xs font-semibold px-2.5 py-0.5 rounded-full bg-emerald-100 text-emerald-800">
              {m.effort}
            </span>
          </div>
          <pre
            className="rounded-lg px-4 py-3 text-xs font-mono overflow-auto leading-relaxed"
            style={{ background: '#0A0F5C', color: '#7DD3FC' }}
          >
            {m.code}
          </pre>
          {m.showCopy && (
            <button
              onClick={onCopy}
              className="mt-2.5 text-sm font-semibold cursor-pointer"
              style={{ color: ORANGE, background: 'none', border: 'none' }}
            >
              {copied ? '✓ Copied!' : 'Copy snippet'}
            </button>
          )}
        </Card>
      ))}
    </div>
  )
}
