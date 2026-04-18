'use client'
import { useState, useEffect } from 'react'
import { UserManagement } from '@/components/users/UserManagement'
import { OverviewTab } from '@/components/dashboard/OverviewTab'
import { AnalyticsTab } from '@/components/dashboard/AnalyticsTab'
import { IntegrationTab } from '@/components/dashboard/IntegrationTab'
import ConnectorsPanel from '@/components/connectors/ConnectorsPanel'
import DocumentsTable from '@/components/upload/DocumentsTable'
import { ChatWidget } from '@/components/chat/ChatWidget'
import { NAVY, ORANGE, BLUE, ROLE_COLORS } from '@/lib/constants'
import { health, getWidgetSnippet } from '@/lib/api/documents'
import { SourceKey } from '@/types/connector'
import { ALL_SOURCES } from '@/lib/constants'

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8001'

const ROLE_TABS: Record<string, string[]> = {
  admin:  ['Overview', 'Upload Docs', 'Analytics', 'Connectors', 'Integration', 'Try It', 'Users'],
  user:   ['Overview', 'Try It'],
  viewer: ['Try It'],
}

const TAB_SLUGS: Record<string, string> = {
  'Overview': 'overview', 'Upload Docs': 'upload-docs', 'Analytics': 'analytics',
  'Connectors': 'connectors', 'Integration': 'integration', 'Try It': 'try-it', 'Users': 'users',
}
const SLUG_TABS: Record<string, string> = Object.fromEntries(
  Object.entries(TAB_SLUGS).map(([k, v]) => [v, k])
)

export default function HomePage() {
  const [user, setUser] = useState<any>(null)
  const [token, setToken] = useState<string>('')
  const [tab, setTab] = useState('Overview')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [ready, setReady] = useState(false)
  const [healthStatus, setHealthStatus] = useState('checking...')
  const [analytics, setAnalytics] = useState<any>(null)
  const [analyticsLoading, setAnalyticsLoading] = useState(false)
  const [copied, setCopied] = useState(false)

  useEffect(() => {
    try {
      const stored = localStorage.getItem('intellirag_auth')
      if (stored) {
        const { user: u, token: t } = JSON.parse(stored)
        setUser(u); setToken(t)
      }
    } catch {}
    setReady(true)
  }, [])

  useEffect(() => {
    const hash = window.location.hash.replace('#', '').toLowerCase()
    if (SLUG_TABS[hash]) setTab(SLUG_TABS[hash])
  }, [])

  useEffect(() => {
    health().then((h) => setHealthStatus(h.status)).catch(() => setHealthStatus('unreachable'))
  }, [])

  useEffect(() => { if (tab === 'Analytics') loadAnalytics() }, [tab])

  function switchTab(t: string) {
    setTab(t)
    window.history.replaceState(null, '', '#' + (TAB_SLUGS[t] || t.toLowerCase()))
  }

  async function handleLogin(e: any) {
    e.preventDefault()
    setLoading(true); setError('')
    try {
      const res = await fetch(`${API_BASE}/api/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password }),
      })
      const data = await res.json()
      if (!res.ok) { setError(data.detail || 'Login failed'); return }
      localStorage.setItem('intellirag_auth', JSON.stringify({ user: data.user, token: data.token }))
      setUser(data.user); setToken(data.token)
    } catch { setError('Connection error') }
    finally { setLoading(false) }
  }

  function handleLogout() {
    localStorage.removeItem('intellirag_auth')
    setUser(null); setToken('')
    window.history.replaceState(null, '', '#overview')
  }

  async function loadAnalytics() {
    setAnalyticsLoading(true)
    try {
      const res = await fetch(`${API_BASE}/api/analytics/general`)
      if (res.ok) setAnalytics(await res.json())
    } catch {}
    setAnalyticsLoading(false)
  }

  async function copySnippet() {
    const snippet = await getWidgetSnippet('general')
    navigator.clipboard.writeText(snippet)
    setCopied(true); setTimeout(() => setCopied(false), 2000)
  }

  if (!ready) return null

  if (!user) {
    return (
      <div className="min-h-screen bg-slate-50 flex items-center justify-center font-sans">
        <div className="bg-white rounded-2xl border border-slate-200 p-10 w-full max-w-md shadow-lg">
          <div className="text-center mb-8">
            <img src="/acl-logo.png" alt="ACL Digital" className="h-10 mx-auto mb-3" />
            <h1 className="text-xl font-bold text-[#060B4E]">Sign in to IntelliRAG</h1>
            <p className="text-sm text-slate-500 mt-1.5">Access your AI knowledge assistant</p>
          </div>
          <form onSubmit={handleLogin} className="flex flex-col gap-4">
            <input type="email" placeholder="Email" value={email} onChange={e => setEmail(e.target.value)}
              className="border border-slate-200 rounded-lg px-3 py-2.5 text-sm text-[#060B4E] bg-slate-50 outline-none focus:ring-2 focus:ring-[#060B4E]/20" />
            <input type="password" placeholder="Password" value={password} onChange={e => setPassword(e.target.value)}
              className="border border-slate-200 rounded-lg px-3 py-2.5 text-sm text-[#060B4E] bg-slate-50 outline-none focus:ring-2 focus:ring-[#060B4E]/20" />
            {error && <div className="p-3 bg-red-50 border border-red-200 rounded-lg text-xs text-red-700">{error}</div>}
            <button type="submit" disabled={loading}
              className="bg-[#060B4E] text-white rounded-lg py-2.5 text-sm font-semibold hover:bg-[#0a1065] disabled:opacity-50 transition-all">
              {loading ? 'Signing in...' : 'Sign In'}
            </button>
          </form>
          <p className="text-center text-xs text-slate-400 mt-5">All data stays on-premise · ACL Digital IntelliRAG</p>
        </div>
      </div>
    )
  }

  const TABS = ROLE_TABS[user.role] || ['Try It']
  const allowedSources: SourceKey[] = user.role === 'admin'
    ? ALL_SOURCES as SourceKey[]
    : (user.connectors || ['uploaded', 'gdrive', 'localfs']) as SourceKey[]

  return (
    <div className="min-h-screen bg-slate-50 flex flex-col font-sans">

      {/* Header */}
      <header className="shrink-0" style={{ background: NAVY }}>
        <div className="flex items-center gap-4 px-6 py-2.5">
          <img src="/acl-logo.png" alt="ACL Digital" className="h-9 w-auto" />
          <div className="w-px h-7 bg-white/20" />
          <span className="text-white font-semibold text-lg">IntelliRAG</span>
          <span className="text-xs font-bold text-white px-2.5 py-0.5 rounded-full capitalize"
            style={{ background: ROLE_COLORS[user.role as keyof typeof ROLE_COLORS] || '#94A3B8' }}>
            {user.role}
          </span>
          <div className="ml-auto flex items-center gap-4 text-sm">
            <div className="flex items-center gap-2">
              <div className={`w-2 h-2 rounded-full ${healthStatus === 'ok' ? 'bg-emerald-400' : 'bg-red-400'}`} />
              <span className="text-white/60">API: {healthStatus}</span>
            </div>
            <span className="text-white/80">{user.name}</span>
            <button onClick={handleLogout}
              className="text-xs px-3 py-1.5 rounded-md bg-white/10 border border-white/20 text-white/60 hover:bg-white/20 transition-all cursor-pointer">
              Sign out
            </button>
          </div>
        </div>
        <div className="flex h-0.5">
          <div className="w-[65%]" style={{ background: ORANGE }} />
          <div className="w-[35%]" style={{ background: BLUE }} />
        </div>
      </header>

      {/* Tab nav */}
      <nav className="bg-white border-b border-slate-200 px-6 flex gap-1 shrink-0">
        {TABS.map((t) => (
          <button key={t} onClick={() => switchTab(t)}
            className="px-4 py-3 text-sm font-medium transition-colors duration-150 whitespace-nowrap cursor-pointer border-none bg-transparent"
            style={{
              color: tab === t ? NAVY : '#64748B',
              borderBottom: `2px solid ${tab === t ? ORANGE : 'transparent'}`,
            }}>
            {t}
          </button>
        ))}
      </nav>

      {/* Try It — full height, no container */}
      {tab === 'Try It' && (
        <div style={{ display: 'flex', flexDirection: 'column', height: 'calc(100vh - 110px)', padding: '20px 24px', gap: 12 }}>
          <div style={{ flexShrink: 0 }}>
            <h1 style={{ fontSize: 20, fontWeight: 600, color: '#060B4E', margin: 0 }}>Try It Live</h1>
            <p style={{ fontSize: 13, color: '#64748B', marginTop: 4 }}>Select sources and ask anything about your documents.</p>
          </div>
          <div style={{ flex: 1, minHeight: 0, overflow: 'hidden' }}>
            <ChatWidget tenant="general" user={user} allowedSources={allowedSources} />
          </div>
        </div>
      )}

      {/* All other tabs — contained */}
      {tab !== 'Try It' && (
        <main className="flex-1 max-w-5xl w-full mx-auto px-6 py-8">
          {tab === 'Overview'    && <OverviewTab onNavigate={switchTab} />}
          {tab === 'Analytics'   && <AnalyticsTab analytics={analytics} loading={analyticsLoading} onRefresh={loadAnalytics} />}
          {tab === 'Integration' && <IntegrationTab apiBase={API_BASE} copied={copied} onCopy={copySnippet} />}
          {tab === 'Connectors'  && <ConnectorsPanel />}
          {tab === 'Users'       && <UserManagement currentUserId={user.id} />}
          {tab === 'Upload Docs' && (
            <div className="flex flex-col gap-4">
              <div>
                <h1 className="text-xl font-semibold text-[#060B4E]">Upload Documents</h1>
                <p className="text-sm text-slate-500 mt-1">Upload files to the knowledge base.</p>
              </div>
              <DocumentsTable />
            </div>
          )}
        </main>
      )}

      {tab !== 'Try It' && (
        <footer className="text-center text-xs text-slate-400 py-5 shrink-0">
          2026 ACL Digital. IntelliRAG v2.0 — All data stays on-premise.
        </footer>
      )}
    </div>
  )
}
