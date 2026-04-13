'use client'
import { useState, useEffect, useRef } from 'react'
import { useAuth } from '@/hooks/useAuth'
import { Header } from '@/components/layout/Header'
import { TabNav } from '@/components/layout/TabNav'
import { LoginForm } from '@/components/auth/LoginForm'
import { ChatWidget } from '@/components/chat/ChatWidget'
import ConnectorsPanel from '@/components/connectors/ConnectorsPanel'
import DocumentsTable from '@/components/upload/DocumentsTable'
import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui'
import { NAVY, ORANGE, BLUE } from '@/lib/constants'
import { health, uploadDocument, getWidgetSnippet } from '@/lib/api/documents'
import { SourceKey } from '@/types/connector'

const TAB_SLUGS: Record<string, string> = {
  'Overview': 'overview', 'Upload Docs': 'upload-docs', 'Analytics': 'analytics',
  'Connectors': 'connectors', 'Integration': 'integration', 'Try It': 'try-it',
}
const SLUG_TABS: Record<string, string> = Object.fromEntries(Object.entries(TAB_SLUGS).map(([k, v]) => [v, k]))

export default function HomePage() {
  const { user, isReady, login, logout, getAllowedSources } = useAuth()
  const [tab, setTab] = useState('Overview')
  const [healthStatus, setHealthStatus] = useState('checking...')
  const [loginLoading, setLoginLoading] = useState(false)
  const [uploadFiles, setUploadFiles] = useState<File[]>([])
  const [uploading, setUploading] = useState(false)
  const [uploadResults, setUploadResults] = useState<any[]>([])
  const [analytics, setAnalytics] = useState<any>(null)
  const [analyticsLoading, setAnalyticsLoading] = useState(false)
  const [copied, setCopied] = useState(false)
  const fileRef = useRef<HTMLInputElement>(null)
  const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

  // Hash routing
  useEffect(() => {
    const hash = window.location.hash.replace('#', '').toLowerCase()
    if (SLUG_TABS[hash]) setTab(SLUG_TABS[hash])
  }, [])

  useEffect(() => {
    health().then((h) => setHealthStatus(h.status)).catch(() => setHealthStatus('unreachable'))
  }, [])

  useEffect(() => {
    if (tab === 'Analytics') loadAnalytics()
  }, [tab])

  function switchTab(t: string) {
    setTab(t)
    window.history.replaceState(null, '', '#' + (TAB_SLUGS[t] || t.toLowerCase()))
  }

  async function handleLogin(email: string, password: string) {
    setLoginLoading(true)
    try { await login(email, password) }
    finally { setLoginLoading(false) }
  }

  async function loadAnalytics() {
    setAnalyticsLoading(true)
    try {
      const res = await fetch(`${API_BASE}/api/analytics/general`)
      if (res.ok) setAnalytics(await res.json())
    } catch {}
    setAnalyticsLoading(false)
  }

  async function handleUpload() {
    if (!uploadFiles.length) return
    setUploading(true); setUploadResults([])
    const results = []
    for (const file of uploadFiles) {
      try {
        const r = await uploadDocument(file, 'general')
        results.push({ filename: file.name, status: 'success', chunks: r.chunks_created })
      } catch (e: any) {
        results.push({ filename: file.name, status: 'error', error: e.message })
      }
    }
    setUploadResults(results); setUploading(false); setUploadFiles([])
  }

  async function copySnippet() {
    const snippet = await getWidgetSnippet('general')
    navigator.clipboard.writeText(snippet)
    setCopied(true); setTimeout(() => setCopied(false), 2000)
  }

  // ── Not ready yet ───────────────────────────────────────────────────────────
  if (!isReady) return null

  // ── Login screen ────────────────────────────────────────────────────────────
  if (!user) {
    return (
      <div className="min-h-screen bg-slate-50 flex items-center justify-center font-[Inter,system-ui,sans-serif]">
        <div className="bg-white rounded-2xl border border-slate-200 p-10 w-full max-w-md shadow-lg">
          <div className="text-center mb-8">
            <img src="/acl-logo.png" alt="ACL Digital" className="h-10 mx-auto mb-3" />
            <h1 className="text-xl font-bold text-[#060B4E]">Sign in to IntelliRAG</h1>
            <p className="text-sm text-slate-500 mt-1.5">Access your AI knowledge assistant</p>
          </div>
          <LoginForm onLogin={handleLogin} loading={loginLoading} />
          <p className="text-center text-xs text-slate-400 mt-5">All data stays on-premise · ACL Digital IntelliRAG</p>
        </div>
      </div>
    )
  }

  const allowedSources = getAllowedSources()

  // ── Dashboard ────────────────────────────────────────────────────────────────
  return (
    <div className="min-h-screen bg-slate-50 font-[Inter,system-ui,sans-serif]">
      <Header user={user} health={healthStatus} onLogout={logout} />
      <TabNav activeTab={tab} onTabChange={switchTab} />

      <main className="max-w-5xl mx-auto px-6 py-8">

        {/* ── OVERVIEW ──────────────────────────────────────────────────────── */}
        {tab === 'Overview' && (
          <div className="flex flex-col gap-5">
            <div>
              <h1 className="text-xl font-semibold text-[#060B4E]">Platform Overview</h1>
              <p className="text-sm text-slate-500 mt-1">IntelliRAG — on-premise AI knowledge platform. All data stays on your servers.</p>
            </div>
            <div className="grid grid-cols-4 gap-3">
              {[['Knowledge base', 'General'], ['LLM', 'Groq / Llama 3.3'], ['Memory', '7-day sessions'], ['Data leakage', 'Zero', '#10B981']].map(([label, value, color]) => (
                <Card key={label} className="p-4">
                  <div className="text-xs text-slate-400 mb-1">{label}</div>
                  <div className="text-xl font-semibold" style={{ color: color || NAVY }}>{value}</div>
                </Card>
              ))}
            </div>
            <Card className="p-5">
              <div className="flex items-center gap-2 mb-4">
                <div className="w-1 h-5 rounded" style={{ background: ORANGE }} />
                <span className="font-semibold text-[#060B4E]">Quick start</span>
              </div>
              {[['Upload Docs', 'Upload PDF, Word, or Excel documents to the knowledge base'],
                ['Connectors', 'Connect Google Drive, SharePoint, or Teams for automatic sync'],
                ['Try It', 'Test the AI assistant with your actual documents']].map(([t, d], i) => (
                <div key={t} className={`flex items-center gap-3 py-2.5 ${i < 2 ? 'border-b border-slate-100' : ''}`}>
                  <div className="w-5 h-5 rounded-full bg-[#060B4E] text-white text-xs font-bold flex items-center justify-center">{i + 1}</div>
                  <span className="text-sm text-slate-600 flex-1">{d} —</span>
                  <button onClick={() => switchTab(t)} className="text-sm font-medium underline" style={{ color: BLUE, background: 'none', border: 'none', cursor: 'pointer' }}>{t}</button>
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
        )}

        {/* ── UPLOAD DOCS ───────────────────────────────────────────────────── */}
        {tab === 'Upload Docs' && (
          <div className="flex flex-col gap-4">
            <div>
              <h1 className="text-xl font-semibold text-[#060B4E]">Upload Documents</h1>
              <p className="text-sm text-slate-500 mt-1">Upload files to the knowledge base. Searchable via the <strong>Uploaded Docs</strong> pill in the chat widget.</p>
            </div>
            <DocumentsTable />
          </div>
        )}

        {/* ── ANALYTICS ─────────────────────────────────────────────────────── */}
        {tab === 'Analytics' && (
          <div className="flex flex-col gap-5">
            <div className="flex items-center justify-between">
              <div>
                <h1 className="text-xl font-semibold text-[#060B4E]">Analytics Dashboard</h1>
                <p className="text-sm text-slate-500 mt-1">Query insights and user feedback</p>
              </div>
              <Button onClick={loadAnalytics} size="sm">Refresh</Button>
            </div>
            {analyticsLoading && <p className="text-center text-slate-400 py-16 text-sm">Loading...</p>}
            {!analyticsLoading && !analytics && (
              <p className="text-center text-slate-400 py-16 text-sm">No data yet — ask some questions in Try It first.</p>
            )}
            {!analyticsLoading && analytics && (
              <>
                <div className="grid grid-cols-4 gap-3">
                  {[['Total queries', analytics.totals?.all_time], ['Today', analytics.totals?.today],
                    ['This week', analytics.totals?.this_week],
                    ['Avg confidence', Math.round((analytics.averages?.confidence || 0) * 100) + '%', (analytics.averages?.confidence || 0) > 0.6 ? '#10B981' : '#F59E0B']].map(([label, value, color]) => (
                    <Card key={label as string} className="p-4">
                      <div className="text-xs text-slate-400 mb-1">{label}</div>
                      <div className="text-xl font-semibold" style={{ color: (color as string) || NAVY }}>{value ?? 0}</div>
                    </Card>
                  ))}
                </div>
                {analytics.recent_queries?.length > 0 && (
                  <Card className="p-5">
                    <h3 className="text-sm font-semibold text-[#060B4E] mb-3">Recent Queries</h3>
                    {analytics.recent_queries.map((q: any) => (
                      <div key={q.id} className="flex items-center gap-3 py-2 border-b border-slate-100 last:border-0">
                        <div className={`w-2 h-2 rounded-full shrink-0 ${q.confidence > 0.6 ? 'bg-emerald-500' : q.confidence > 0.4 ? 'bg-amber-500' : 'bg-red-500'}`} />
                        <span className="text-sm text-slate-600 flex-1">{q.question.length > 70 ? q.question.slice(0, 70) + '...' : q.question}</span>
                        <span className="text-xs text-slate-400">{Math.round(q.confidence * 100)}%</span>
                      </div>
                    ))}
                  </Card>
                )}
              </>
            )}
          </div>
        )}

        {/* ── CONNECTORS ────────────────────────────────────────────────────── */}
        {tab === 'Connectors' && <ConnectorsPanel />}

        {/* ── INTEGRATION ───────────────────────────────────────────────────── */}
        {tab === 'Integration' && (
          <div className="flex flex-col gap-4">
            <div>
              <h1 className="text-xl font-semibold text-[#060B4E]">Integration Guide</h1>
              <p className="text-sm text-slate-500 mt-1">Embed IntelliRAG in any application</p>
            </div>
            {[{ num: '1', title: 'Script tag — any HTML app', color: ORANGE, effort: '5 min',
                code: `<script\n  src="${API_BASE}/widget.js"\n  data-tenant="general"\n></script>` },
              { num: '2', title: 'React component', color: BLUE, effort: '30 min',
                code: '<ChatWidget tenant="general" user={user} allowedSources={sources} />' },
              { num: '3', title: 'REST API', color: NAVY, effort: '1-2 hrs',
                code: 'POST /api/query/\n{ "tenant": "general", "question": "...", "sources": ["gdrive"] }' }
            ].map((m) => (
              <Card key={m.num} className="p-5">
                <div className="flex items-center gap-3 mb-4">
                  <div className="w-7 h-7 rounded-full text-white text-xs font-bold flex items-center justify-center" style={{ background: m.color }}>{m.num}</div>
                  <span className="font-semibold text-[#060B4E] flex-1">{m.title}</span>
                  <span className="text-xs font-semibold px-2.5 py-0.5 rounded-full bg-emerald-100 text-emerald-800">{m.effort}</span>
                </div>
                <pre className="rounded-lg px-4 py-3 text-xs font-mono overflow-auto leading-relaxed" style={{ background: '#0A0F5C', color: '#7DD3FC' }}>{m.code}</pre>
                {m.num === '1' && (
                  <button onClick={copySnippet} className="mt-2.5 text-sm font-semibold cursor-pointer" style={{ color: ORANGE, background: 'none', border: 'none' }}>
                    {copied ? 'Copied!' : 'Copy snippet'}
                  </button>
                )}
              </Card>
            ))}
          </div>
        )}

        {/* ── TRY IT ────────────────────────────────────────────────────────── */}
        {tab === 'Try It' && (
          <div className="flex flex-col gap-4">
            <div>
              <h1 className="text-xl font-semibold text-[#060B4E]">Try It Live</h1>
              <p className="text-sm text-slate-500 mt-1">Test the AI assistant. Use the source pills inside the widget to choose where to search.</p>
            </div>
            <div className="bg-amber-50 border border-amber-200 rounded-xl p-3 text-xs text-amber-800">
              <strong>How source selection works:</strong> The pills inside the chat widget control where the AI searches. Select one or multiple — answers show which file and source they came from.
            </div>
            <div style={{ height: 'calc(100vh - 240px)', minHeight: 600 }}>
              <ChatWidget
                tenant="general"
                user={user}
                allowedSources={allowedSources}
                fullScreen
                onLogout={logout}
              />
            </div>
          </div>
        )}
      </main>

      <footer className="text-center text-xs text-slate-400 py-6">
        2026 ACL Digital. IntelliRAG v2.0 — All data stays on-premise.
      </footer>
    </div>
  )
}
