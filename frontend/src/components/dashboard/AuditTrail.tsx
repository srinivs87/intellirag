'use client'
import { useState, useEffect, useCallback } from 'react'
import { NAVY } from '@/lib/constants'

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8001'

interface AuditEntry {
  id: string
  question: string
  answer: string
  confidence: number
  total_ms: number
  session_id: string | null
  user_id: string | null
  user_role: string | null
  sources: any[]
  created_at: string
  feedback: string | null
  tenant_slug: string
}

interface AuditData {
  entries: AuditEntry[]
  total: number
  page: number
  per_page: number
  total_pages: number
}

function formatTime(iso: string): string {
  if (!iso) return '—'
  const d = new Date(iso)
  return d.toLocaleString('en-US', {
    month: 'short', day: 'numeric',
    hour: '2-digit', minute: '2-digit',
  })
}

function confidenceColor(c: number): string {
  if (c >= 0.8) return '#10B981'
  if (c >= 0.5) return '#F59E0B'
  return '#EF4444'
}

function confidenceLabel(c: number): string {
  if (c >= 0.8) return 'High'
  if (c >= 0.5) return 'Med'
  return 'Low'
}

const ROLE_STYLES: Record<string, { bg: string; color: string }> = {
  admin:  { bg: '#FEF3C7', color: '#92400E' },
  user:   { bg: '#EFF6FF', color: '#1E40AF' },
  viewer: { bg: '#F0FDF4', color: '#065F46' },
}

function UserBadge({ userId, userRole }: { userId: string | null; userRole: string | null }) {
  const role = userRole || 'user'
  const style = ROLE_STYLES[role] || ROLE_STYLES.user
  const name = userId
    ? userId.split('@')[0].split('.')[0]  // first name from email
    : 'Anonymous'

  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-xs text-slate-600 font-medium truncate max-w-24">
        {name.charAt(0).toUpperCase() + name.slice(1)}
      </span>
      <span
        className="text-xs px-1.5 py-0.5 rounded-full font-medium inline-block w-fit capitalize"
        style={{ background: style.bg, color: style.color }}
      >
        {role}
      </span>
    </div>
  )
}

export function AuditTrail() {
  const [data, setData] = useState<AuditData | null>(null)
  const [loading, setLoading] = useState(true)
  const [page, setPage] = useState(1)
  const [search, setSearch] = useState('')
  const [expanded, setExpanded] = useState<string | null>(null)
  const [exporting, setExporting] = useState(false)

  const loadAudit = useCallback(async () => {
    setLoading(true)
    try {
      const params = new URLSearchParams({
        page: String(page),
        per_page: '20',
        ...(search ? { search } : {}),
      })
      const res = await fetch(`${API_BASE}/api/audit?${params}`)
      if (res.ok) {
        const json = await res.json()
        setData(json)
      }
    } catch { /* silent */ }
    setLoading(false)
  }, [page, search])

  useEffect(() => { loadAudit() }, [loadAudit])

  async function handleExport() {
    setExporting(true)
    try {
      const res = await fetch(`${API_BASE}/api/audit/export`)
      if (res.ok) {
        const blob = await res.blob()
        const url = URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        a.download = `intellirag-audit-${new Date().toISOString().slice(0, 10)}.csv`
        a.click()
        URL.revokeObjectURL(url)
      }
    } catch { /* silent */ }
    setExporting(false)
  }

  function toggleExpand(id: string) {
    setExpanded(prev => prev === id ? null : id)
  }

  const entries = data?.entries || []
  const totalPages = data?.total_pages || 1

  return (
    <div className="flex flex-col gap-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-base font-semibold" style={{ color: NAVY }}>Audit Trail</h2>
          <p className="text-xs text-slate-500 mt-0.5">
            Complete log of all queries — who asked what, when, and confidence level
          </p>
        </div>
        <button
          onClick={handleExport}
          disabled={exporting}
          className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium border border-slate-200 bg-white text-slate-600 hover:bg-slate-50 transition-colors cursor-pointer disabled:opacity-50"
        >
          <svg width="14" height="14" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
            <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4M7 10l5 5 5-5M12 15V3" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
          {exporting ? 'Exporting...' : 'Export CSV'}
        </button>
      </div>

      {/* Search */}
      <div className="relative">
        <svg className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" width="14" height="14" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
          <circle cx="11" cy="11" r="8" /><path d="M21 21l-4.35-4.35" strokeLinecap="round" />
        </svg>
        <input
          type="text"
          value={search}
          onChange={(e) => { setSearch(e.target.value); setPage(1) }}
          placeholder="Search questions..."
          className="w-full pl-9 pr-4 py-2.5 text-sm border border-slate-200 rounded-lg outline-none focus:border-blue-400 focus:ring-2 focus:ring-blue-100 text-slate-700 bg-white"
        />
      </div>

      {/* Stats bar */}
      {data && (
        <div className="flex items-center gap-4 text-xs text-slate-500 bg-slate-50 rounded-lg px-4 py-2.5 border border-slate-200">
          <span><strong className="text-slate-700">{data.total}</strong> total queries</span>
          <span className="text-slate-300">|</span>
          <span>Page <strong className="text-slate-700">{page}</strong> of <strong className="text-slate-700">{totalPages}</strong></span>
        </div>
      )}

      {/* Table */}
      <div className="bg-white rounded-xl border border-slate-200 overflow-hidden">
        {/* Header — 12 cols: Question(4) Time(2) User(2) Confidence(2) Response(1) Src(1) */}
        <div className="grid grid-cols-12 gap-3 px-4 py-3 bg-slate-50 border-b border-slate-200 text-xs font-semibold text-slate-500 uppercase tracking-wide">
          <div className="col-span-4">Question</div>
          <div className="col-span-2">Time</div>
          <div className="col-span-2">User</div>
          <div className="col-span-2">Confidence</div>
          <div className="col-span-1">Response</div>
          <div className="col-span-1">Src</div>
        </div>

        {loading && (
          <div className="py-16 text-center text-sm text-slate-400">Loading audit log...</div>
        )}

        {!loading && entries.length === 0 && (
          <div className="py-16 text-center text-sm text-slate-400">
            No queries yet — ask questions in Try It first.
          </div>
        )}

        {!loading && entries.map((entry) => (
          <div key={entry.id} className="border-b border-slate-100 last:border-0">
            {/* Row */}
            <button
              onClick={() => toggleExpand(entry.id)}
              className="w-full grid grid-cols-12 gap-3 px-4 py-3 hover:bg-slate-50 transition-colors text-left cursor-pointer border-none bg-transparent"
            >
              <div className="col-span-4 text-sm text-slate-700 truncate self-center">
                {entry.question.length > 55 ? entry.question.slice(0, 55) + '…' : entry.question}
              </div>
              <div className="col-span-2 text-xs text-slate-400 self-center">
                {formatTime(entry.created_at)}
              </div>
              <div className="col-span-2 self-center">
                <UserBadge userId={entry.user_id} userRole={entry.user_role} />
              </div>
              <div className="col-span-2 self-center">
                <div className="flex items-center gap-1.5">
                  <div className="w-1.5 h-1.5 rounded-full shrink-0" style={{ background: confidenceColor(entry.confidence) }} />
                  <span className="text-xs" style={{ color: confidenceColor(entry.confidence) }}>
                    {Math.round(entry.confidence * 100)}% {confidenceLabel(entry.confidence)}
                  </span>
                </div>
              </div>
              <div className="col-span-1 text-xs text-slate-400 self-center">
                {entry.total_ms}ms
              </div>
              <div className="col-span-1 self-center">
                <span className="text-xs bg-slate-100 text-slate-500 px-1.5 py-0.5 rounded">
                  {entry.sources?.length || 0}
                </span>
              </div>
            </button>

            {/* Expanded detail */}
            {expanded === entry.id && (
              <div className="px-4 pb-4 bg-slate-50 border-t border-slate-100">
                <div className="grid grid-cols-2 gap-4 mt-3">
                  <div>
                    <p className="text-xs font-semibold text-slate-500 mb-1.5">Full Question</p>
                    <p className="text-sm text-slate-700 bg-white rounded-lg border border-slate-200 px-3 py-2.5 leading-relaxed">
                      {entry.question}
                    </p>
                  </div>
                  <div>
                    <p className="text-xs font-semibold text-slate-500 mb-1.5">Answer Preview</p>
                    <p className="text-sm text-slate-600 bg-white rounded-lg border border-slate-200 px-3 py-2.5 leading-relaxed line-clamp-4">
                      {entry.answer.slice(0, 300)}{entry.answer.length > 300 ? '…' : ''}
                    </p>
                  </div>
                </div>
                {entry.sources && entry.sources.length > 0 && (
                  <div className="mt-3">
                    <p className="text-xs font-semibold text-slate-500 mb-1.5">Sources Used</p>
                    <div className="flex flex-wrap gap-1.5">
                      {entry.sources.map((s: any, i: number) => (
                        <span key={i} className="text-xs bg-blue-50 text-blue-700 border border-blue-200 px-2 py-0.5 rounded-full">
                          {s.filename || s}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
                <div className="mt-3 flex gap-4 text-xs text-slate-400">
                  {entry.session_id && <span>Session: {entry.session_id.slice(0, 8)}…</span>}
                  {entry.tenant_slug && <span>Tenant: {entry.tenant_slug}</span>}
                  {entry.feedback && (
                    <span>{entry.feedback === 'thumbs_up' ? '👍 Helpful' : '👎 Not helpful'}</span>
                  )}
                </div>
              </div>
            )}
          </div>
        ))}
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-center gap-2">
          <button
            onClick={() => setPage(p => Math.max(1, p - 1))}
            disabled={page === 1}
            className="px-3 py-1.5 text-sm border border-slate-200 rounded-lg disabled:opacity-40 cursor-pointer hover:bg-slate-50 bg-white text-slate-600"
          >
            ← Previous
          </button>
          <span className="text-sm text-slate-500">{page} / {totalPages}</span>
          <button
            onClick={() => setPage(p => Math.min(totalPages, p + 1))}
            disabled={page === totalPages}
            className="px-3 py-1.5 text-sm border border-slate-200 rounded-lg disabled:opacity-40 cursor-pointer hover:bg-slate-50 bg-white text-slate-600"
          >
            Next →
          </button>
        </div>
      )}
    </div>
  )
}
