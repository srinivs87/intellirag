'use client'
import { useState, useEffect } from 'react'
import { useAuth } from '@/hooks/useAuth'
import { Header } from '@/components/layout/Header'
import { TabNav } from '@/components/layout/TabNav'
import { LoginForm } from '@/components/auth/LoginForm'
import { ChatWidget } from '@/components/chat/ChatWidget'
import { UserManagement } from '@/components/users/UserManagement'
import { OverviewTab } from '@/components/dashboard/OverviewTab'
import { AnalyticsTab } from '@/components/dashboard/AnalyticsTab'
import { IntegrationTab } from '@/components/dashboard/IntegrationTab'
import ConnectorsPanel from '@/components/connectors/ConnectorsPanel'
import DocumentsTable from '@/components/upload/DocumentsTable'
import { NAVY } from '@/lib/constants'
import { health, getWidgetSnippet } from '@/lib/api/documents'

const ROLE_TAB_MAP: Record<string, string[]> = {
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
  const { user, isReady, login, logout, getAllowedSources } = useAuth()
  const [tab, setTab] = useState('Overview')
  const [healthStatus, setHealthStatus] = useState('checking...')
  const [loginLoading, setLoginLoading] = useState(false)
  const [analytics, setAnalytics] = useState<any>(null)
  const [analyticsLoading, setAnalyticsLoading] = useState(false)
  const [copied, setCopied] = useState(false)
  const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8001'

  const TABS = user ? (ROLE_TAB_MAP[user.role as string] ?? ['Try It']) : []

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

  async function copySnippet() {
    const snippet = await getWidgetSnippet('general')
    navigator.clipboard.writeText(snippet)
    setCopied(true); setTimeout(() => setCopied(false), 2000)
  }

  if (!isReady) return null

  if (!user) {
    return (
      <div className="min-h-screen bg-slate-50 flex items-center justify-center">
        <div className="bg-white rounded-2xl border border-slate-200 p-10 w-full max-w-md shadow-lg">
          <div className="text-center mb-8">
            <img src="/acl-logo.png" alt="ACL Digital" className="h-10 mx-auto mb-3" />
            <h1 className="text-xl font-bold" style={{ color: NAVY }}>Sign in to IntelliRAG</h1>
            <p className="text-sm text-slate-500 mt-1.5">Access your AI knowledge assistant</p>
          </div>
          <LoginForm onLogin={handleLogin} loading={loginLoading} />
          <p className="text-center text-xs text-slate-400 mt-5">
            All data stays on-premise · ACL Digital IntelliRAG
          </p>
        </div>
      </div>
    )
  }

  const allowedSources = getAllowedSources()
  const isTryIt = tab === 'Try It'

  return (
    /*
      Key layout fix:
      - h-screen + overflow-hidden on root → page never grows beyond viewport
      - flex-col with flex-1 on content area → Try It fills remaining space
      - overflow-hidden on non-Try It tabs so footer stays fixed
    */
    <div className="h-screen overflow-hidden flex flex-col bg-slate-50">
      <Header user={user} health={healthStatus} onLogout={logout} />
      <TabNav activeTab={tab} onTabChange={switchTab} tabs={TABS} />

      {/* Try It — takes all remaining viewport height, no scroll on page */}
      {isTryIt && (
        <div className="flex-1 min-h-0 p-3">
          <ChatWidget
            tenant="general"
            user={user}
            allowedSources={allowedSources}
          />
        </div>
      )}

      {/* All other tabs — scrollable within viewport */}
      {!isTryIt && (
        <div className="flex-1 overflow-y-auto">
          <main className="max-w-5xl mx-auto px-6 py-8">
            {tab === 'Overview'    && <OverviewTab onNavigate={switchTab} />}
            {tab === 'Analytics'   && <AnalyticsTab analytics={analytics} loading={analyticsLoading} onRefresh={loadAnalytics} />}
            {tab === 'Integration' && <IntegrationTab apiBase={API_BASE} copied={copied} onCopy={copySnippet} />}
            {tab === 'Connectors'  && <ConnectorsPanel />}
            {tab === 'Users'       && <UserManagement currentUserId={user.id} />}
            {tab === 'Upload Docs' && (
              <div className="flex flex-col gap-4">
                <div>
                  <h1 className="text-xl font-semibold" style={{ color: NAVY }}>Upload Documents</h1>
                  <p className="text-sm text-slate-500 mt-1">Upload files to the knowledge base.</p>
                </div>
                <DocumentsTable />
              </div>
            )}
          </main>
          <footer className="text-center text-xs text-slate-400 py-4">
            2026 ACL Digital · IntelliRAG v2.0 · All data stays on-premise
          </footer>
        </div>
      )}
    </div>
  )
}
