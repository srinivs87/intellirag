'use client'
import { AutoSyncPanel } from './AutoSyncPanel'
import { useState, useEffect, useRef } from 'react'

const _style = typeof document !== "undefined" && (() => { const s = document.createElement("style"); s.textContent = "@keyframes spin { to { transform: rotate(360deg) } }"; document.head.appendChild(s) })()
const NAVY = '#060B4E', ORANGE = '#FA9600', BLUE = '#0096D5'
const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

interface GDriveConnector {
  id: string; name: string; folder_id?: string; status: string;
  last_sync_at?: string; files_synced: number;
}
interface M365Connector {
  id: string; name: string; sources: string[]; status: string;
  last_sync_at?: string; files_synced: number;
}

function StatusDot({ status }: { status: string }) {
  const color = status === 'idle' ? '#10B981' : status === 'syncing' ? ORANGE : status === 'error' ? '#EF4444' : '#CBD5E1'
  const label = status === 'idle' ? 'Connected' : status === 'syncing' ? 'Syncing...' : status === 'error' ? 'Error' : 'Not connected'
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5, fontSize: 11, fontWeight: 600, padding: '3px 10px', borderRadius: 10, background: status === 'idle' ? '#E1F5EE' : status === 'syncing' ? '#FFF4E0' : status === 'error' ? '#FEE2E2' : '#F5F7FA', color: status === 'idle' ? '#085041' : status === 'syncing' ? '#854F0B' : status === 'error' ? '#991B1B' : '#94A3B8' }}>
      <span style={{ width: 6, height: 6, borderRadius: '50%', background: color, display: 'inline-block' }} />
      {label}
    </span>
  )
}

function SyncInfo({ connector, onSync, syncing, progress }: { 
  connector: GDriveConnector | M365Connector; 
  onSync: () => void;
  syncing?: boolean;
  progress?: { percent: number; synced: number; skipped: number; total: number } | null;
}) {
  return (
    <div style={{ marginTop: 8 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '8px 12px', background: '#F5F7FA', borderRadius: 8, fontSize: 12, color: '#64748B' }}>
        <svg width="13" height="13" fill="none" viewBox="0 0 24 24"><path d="M4 12a8 8 0 018-8V2l4 4-4 4V6a6 6 0 100 12v2a8 8 0 01-8-8z" fill="#94A3B8"/></svg>
        <span><strong style={{ color: NAVY }}>{connector.files_synced}</strong> files indexed</span>
        <span>·</span>
        <span>Last sync: {connector.last_sync_at ? new Date(connector.last_sync_at).toLocaleString() : 'Never'}</span>
        <button onClick={onSync} disabled={syncing} style={{ marginLeft: 'auto', display: 'inline-flex', alignItems: 'center', gap: 5, fontSize: 11, fontWeight: 600, color: syncing ? '#94A3B8' : BLUE, background: syncing ? '#F5F7FA' : '#E6F1FB', border: 'none', borderRadius: 6, padding: '4px 10px', cursor: syncing ? 'not-allowed' : 'pointer' }}>
          <svg width="11" height="11" fill="none" viewBox="0 0 24 24"><path d="M4 12a8 8 0 018-8V2l4 4-4 4V6a6 6 0 100 12v2a8 8 0 01-8-8z" stroke={syncing ? '#94A3B8' : BLUE} strokeWidth="2"/></svg>
          {syncing ? 'Syncing...' : 'Sync now'}
        </button>
      </div>
      {syncing && (
        <div style={{ marginTop: 8, padding: '10px 14px', background: '#F0FFF4', borderRadius: 8, border: '1px solid #6EE7B7' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: 11, color: '#065F46', marginBottom: 6 }}>
            <span style={{ fontWeight: 500 }}>
              {progress && progress.total > 0
                ? `${progress.synced} new · ${progress.skipped} unchanged of ${progress.total} files`
                : 'Connecting to Google Drive...'}
            </span>
            <span style={{ fontWeight: 700, fontSize: 13, color: '#065F46' }}>
              {progress && progress.total > 0 ? `${progress.percent}%` : ''}
            </span>
          </div>
          <div style={{ height: 8, background: '#D1FAE5', borderRadius: 99, overflow: 'hidden' }}>
            <div style={{ height: '100%', width: `${Math.max(progress?.percent ?? 5, 5)}%`, background: 'linear-gradient(90deg, #065F46, #10B981)', borderRadius: 99, transition: 'width 0.8s ease' }} />
          </div>
          {progress && progress.total > 0 && (
            <div style={{ fontSize: 10, color: '#064E3B', marginTop: 5, display: 'flex', gap: 12 }}>
              <span>✓ {progress.synced} synced</span>
              <span>⟳ {progress.skipped} unchanged</span>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// ─── Google Drive Card ───────────────────────────────────────────────────────
function GoogleDriveCard() {
  const [connector, setConnector] = useState<GDriveConnector | null>(null)
  const [loading, setLoading] = useState(true)
  const [editing, setEditing] = useState(false)
  const [saving, setSaving] = useState(false)
  const [syncing, setSyncing] = useState(false)
  const [syncProgress, setSyncProgress] = useState<{ percent: number; synced: number; skipped: number; total: number } | null>(null)
  const [msg, setMsg] = useState('')
  const [form, setForm] = useState({ name: 'My Google Drive', folder_id: '' })
  const fileRef = useRef<HTMLInputElement>(null)
  const editFileRef = useRef<HTMLInputElement>(null)

  async function load() {
    try {
      const r = await fetch(`${API_BASE}/api/connectors/gdrive/`)
      const d = await r.json()
      setConnector(d.connectors?.[0] || null)
    } catch {}
    setLoading(false)
  }

  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  function startPolling(connectorId: string) {
    if (pollRef.current) clearInterval(pollRef.current)
    setSyncing(true)
    setSyncProgress(null) // null = "Starting..." state
    pollRef.current = setInterval(async () => {
      try {
        const pr = await fetch(`${API_BASE}/api/connectors/gdrive/${connectorId}/progress`)
        if (pr.ok) {
          const p = await pr.json()
          // Only show progress if we have real data (total > 0)
          // Always update progress from what we have
          setSyncProgress({ percent: p.percent||0, synced: p.synced||0, skipped: p.skipped||0, total: p.total||0 })
          // Stop when idle
          if (p.status === 'idle') {
            setSyncProgress({ percent: 100, synced: p.synced||0, skipped: p.skipped||0, total: p.total||0 })
            setTimeout(() => stopPolling(), 2500)
            load()
          }
        }
      } catch { stopPolling() }
    }, 2000)
  }

  function stopPolling() {
    if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null }
    setTimeout(() => { setSyncing(false); setSyncProgress(null) }, 2500)
  }

  useEffect(() => { load() }, [])
  useEffect(() => {
    if (connector?.status === 'syncing' && connector?.id && !pollRef.current) startPolling(connector.id)
    else if (connector?.status !== 'syncing' && !pollRef.current) setSyncing(false)
  }, [connector?.status, connector?.id])
  useEffect(() => () => { if (pollRef.current) clearInterval(pollRef.current) }, [])

  async function connect() {
    const file = fileRef.current?.files?.[0]
    if (!file) { setMsg('Please select your JSON key file'); return }
    setSaving(true); setMsg('')
    const fd = new FormData()
    fd.append('name', form.name)
    fd.append('credentials_file', file)
    fd.append('sync_now', 'true')
    if (form.folder_id) fd.append('folder_id', form.folder_id)
    try {
      const r = await fetch(`${API_BASE}/api/connectors/gdrive/`, { method: 'POST', body: fd })
      const d = await r.json()
      if (r.ok) { setMsg('Connected! Sync started in background.'); load() }
      else setMsg('Error: ' + (d.detail || JSON.stringify(d)))
    } catch (e: any) { setMsg('Failed: ' + e.message) }
    setSaving(false)
  }

  async function update() {
    setSaving(true); setMsg('')
    const fd = new FormData()
    if (form.name && form.name !== connector?.name) fd.append('name', form.name)
    if (form.folder_id !== (connector?.folder_id || '')) fd.append('folder_id', form.folder_id)
    const file = editFileRef.current?.files?.[0]
    if (file) fd.append('credentials_file', file)
    fd.append('sync_now', 'false')
    try {
      const r = await fetch(`${API_BASE}/api/connectors/gdrive/${connector!.id}`, { method: 'PUT', body: fd })
      const d = await r.json()
      if (r.ok) { setMsg('Updated successfully.'); setEditing(false); load() }
      else setMsg('Error: ' + (d.detail || JSON.stringify(d)))
    } catch (e: any) { setMsg('Failed: ' + e.message) }
    setSaving(false)
  }

  async function sync() {
    if (syncing) return
    setMsg('')
    await fetch(`${API_BASE}/api/connectors/gdrive/${connector!.id}/sync`, { method: 'POST' })
    setTimeout(() => startPolling(connector!.id), 1000)
  }

  async function remove() {
    if (!confirm('Remove Google Drive connector? Indexed files remain searchable.')) return
    await fetch(`${API_BASE}/api/connectors/gdrive/${connector!.id}`, { method: 'DELETE' })
    setConnector(null); setMsg('')
  }

  if (loading) return <div style={{ padding: 20, fontSize: 13, color: '#94A3B8' }}>Loading...</div>

  return (
    <div style={{ background: '#fff', borderRadius: 12, border: '1px solid #E2E8F2', overflow: 'hidden' }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '16px 20px', borderBottom: connector ? '1px solid #E2E8F2' : 'none' }}>
        <div style={{ width: 40, height: 40, borderRadius: 10, background: '#E6F1FB', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <svg width="22" height="22" viewBox="0 0 87.3 78" fill="none">
            <path d="M6.6 66.85l3.85 6.65c.8 1.4 1.95 2.5 3.3 3.3L27.5 53H0c0 1.55.4 3.1 1.2 4.5l5.4 9.35z" fill="#0066DA"/>
            <path d="M43.65 25L29.9 1.2C28.55.4 27 0 25.45 0c-1.55 0-3.1.4-4.45 1.2L6.6 26.1 27.5 53l16.15-28z" fill="#00AC47"/>
            <path d="M73.55 76.8c1.35-.8 2.5-1.9 3.3-3.3l9.25-16c.8-1.4 1.2-2.95 1.2-4.5H60.2L73.55 76.8z" fill="#EA4335"/>
            <path d="M43.65 25L57.4 1.2C56.05.4 54.5 0 52.95 0H34.35c-1.55 0-3.1.4-4.45 1.2L43.65 25z" fill="#00832D"/>
            <path d="M60.2 53H27.5L13.75 76.8c1.35.8 2.9 1.2 4.45 1.2h50.9c1.55 0 3.1-.4 4.45-1.2L60.2 53z" fill="#2684FC"/>
            <path d="M73.4 26.1L59.65 1.2C58.3.4 56.75 0 55.2 0H43.65L60.2 53l26.7-22.4c-.8-1.75-2.1-3.2-3.7-4.1l-9.8-.4z" fill="#FFBA00"/>
          </svg>
        </div>
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: 15, fontWeight: 600, color: NAVY }}>Google Drive</div>
          <div style={{ fontSize: 12, color: '#64748B', marginTop: 2 }}>Sync files from My Drive or a specific folder</div>
        </div>
        {connector ? <StatusDot status={connector.status} /> : <StatusDot status="disconnected" />}
      </div>

      <div style={{ padding: '16px 20px' }}>
        {/* Connected state */}
        {connector && !editing && (
          <>
            <SyncInfo connector={connector} onSync={sync} syncing={syncing} progress={syncProgress} />
            <div style={{ display: 'flex', gap: 8, marginTop: 12 }}>
              <button onClick={() => { setEditing(true); setForm({ name: connector.name, folder_id: connector.folder_id || '' }) }}
                style={{ flex: 1, padding: '8px 0', fontSize: 12, fontWeight: 500, color: NAVY, background: '#F5F7FA', border: '1px solid #E2E8F2', borderRadius: 8, cursor: 'pointer' }}>
                Edit credentials
              </button>
              <button onClick={remove}
                style={{ padding: '8px 16px', fontSize: 12, fontWeight: 500, color: '#EF4444', background: '#FFF5F5', border: '1px solid #FED7D7', borderRadius: 8, cursor: 'pointer' }}>
                Remove
              </button>
            </div>
          </>
        )}

        {/* Edit / Connect form */}
        {(!connector || editing) && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            {editing && <div style={{ fontSize: 12, color: '#64748B', padding: '6px 10px', background: '#FFF4E0', borderRadius: 6 }}>Updating credentials — only fill in the fields you want to change.</div>}

            <div>
              <label style={{ fontSize: 12, fontWeight: 500, color: NAVY, display: 'block', marginBottom: 5 }}>Connector name</label>
              <input value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
                style={{ width: '100%', border: '1px solid #E2E8F2', borderRadius: 8, padding: '8px 12px', fontSize: 13, color: NAVY, background: '#F5F7FA', outline: 'none', boxSizing: 'border-box' }} />
            </div>

            <div>
              <label style={{ fontSize: 12, fontWeight: 500, color: NAVY, display: 'block', marginBottom: 5 }}>
                {editing ? 'New service account JSON key' : 'Service account JSON key'}
                {editing && <span style={{ fontWeight: 400, color: '#94A3B8' }}> (leave empty to keep current)</span>}
              </label>
              <div style={{ border: '1px solid #E2E8F2', borderRadius: 8, padding: '8px 12px', background: '#F5F7FA', cursor: 'pointer' }}
                onClick={() => (editing ? editFileRef : fileRef).current?.click()}>
                <input ref={editing ? editFileRef : fileRef} type="file" accept=".json" style={{ display: 'none' }} />
                <span style={{ fontSize: 12, color: '#64748B' }}>Click to select JSON key file from Google Cloud Console</span>
              </div>
            </div>

            <div>
              <label style={{ fontSize: 12, fontWeight: 500, color: NAVY, display: 'block', marginBottom: 5 }}>
                Folder ID <span style={{ fontWeight: 400, color: '#94A3B8' }}>(optional — leave blank to sync all of My Drive)</span>
              </label>
              <input value={form.folder_id} onChange={e => setForm(f => ({ ...f, folder_id: e.target.value }))}
                placeholder="Paste Google Drive folder ID from URL"
                style={{ width: '100%', border: '1px solid #E2E8F2', borderRadius: 8, padding: '8px 12px', fontSize: 13, color: NAVY, background: '#F5F7FA', outline: 'none', boxSizing: 'border-box' }} />
              <div style={{ fontSize: 11, color: '#94A3B8', marginTop: 4 }}>Find it in the URL: drive.google.com/drive/folders/<strong>THIS_PART</strong></div>
            </div>

            <div style={{ display: 'flex', gap: 8 }}>
              <button onClick={editing ? update : connect} disabled={saving}
                style={{ flex: 1, padding: '10px 0', fontSize: 13, fontWeight: 600, color: '#fff', background: saving ? '#94A3B8' : NAVY, border: 'none', borderRadius: 8, cursor: 'pointer' }}>
                {saving ? 'Saving...' : editing ? 'Save changes' : 'Connect Google Drive & Sync'}
              </button>
              {editing && (
                <button onClick={() => { setEditing(false); setMsg('') }}
                  style={{ padding: '10px 16px', fontSize: 13, color: '#64748B', background: '#F5F7FA', border: '1px solid #E2E8F2', borderRadius: 8, cursor: 'pointer' }}>
                  Cancel
                </button>
              )}
            </div>
          </div>
        )}

        {msg && <div style={{ marginTop: 10, padding: '8px 12px', borderRadius: 8, fontSize: 12, background: msg.startsWith('Error') || msg.startsWith('Failed') ? '#FFF5F5' : '#F0FFF4', color: msg.startsWith('Error') || msg.startsWith('Failed') ? '#991B1B' : '#065F46' }}>{msg}</div>}
      </div>
    </div>
  )
}

// ─── Microsoft 365 Card ──────────────────────────────────────────────────────
function Microsoft365Card() {
  const [connector, setConnector] = useState<M365Connector | null>(null)
  const [loading, setLoading] = useState(true)
  const [editing, setEditing] = useState(false)
  const [saving, setSaving] = useState(false)
  const [msg, setMsg] = useState('')
  const [form, setForm] = useState({ name: 'ACL Microsoft 365', tenant_id: '', client_id: '', client_secret: '', sources: ['teams', 'onedrive', 'sharepoint'] })
  const [showSecret, setShowSecret] = useState(false)

  async function load() {
    try {
      const r = await fetch(`${API_BASE}/api/connectors/m365/`)
      const d = await r.json()
      setConnector(d.connectors?.[0] || null)
    } catch {}
    setLoading(false)
  }

  useEffect(() => { load() }, [])
  useEffect(() => {
    if (connector?.status !== 'syncing') return
    const t = setInterval(() => {
      fetch(`${API_BASE}/api/connectors/m365/`)
        .then(r => r.json())
        .then(d => {
          const c = d.connectors?.[0]
          setConnector(c || null)
          if (c?.status !== 'syncing') { clearInterval(t); setMsg('') }
        }).catch(() => {})
    }, 4000)
    return () => clearInterval(t)
  }, [connector?.status])

  function toggleSource(s: string) {
    setForm(f => ({ ...f, sources: f.sources.includes(s) ? f.sources.filter(x => x !== s) : [...f.sources, s] }))
  }

  async function connect() {
    if (!form.tenant_id || !form.client_id || !form.client_secret) { setMsg('Please fill in all three Azure credentials'); return }
    setSaving(true); setMsg('')
    try {
      const r = await fetch(`${API_BASE}/api/connectors/m365/`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: form.name, tenant_id: form.tenant_id, client_id: form.client_id, client_secret: form.client_secret, sources: form.sources, sync_now: true })
      })
      const d = await r.json()
      if (r.ok) { setMsg('Connected! Sync started in background.'); load() }
      else setMsg('Error: ' + (d.detail || JSON.stringify(d)))
    } catch (e: any) { setMsg('Failed: ' + e.message) }
    setSaving(false)
  }

  async function update() {
    setSaving(true); setMsg('')
    const payload: any = { sources: form.sources, sync_now: false }
    if (form.name) payload.name = form.name
    if (form.tenant_id) payload.tenant_id = form.tenant_id
    if (form.client_id) payload.client_id = form.client_id
    if (form.client_secret) payload.client_secret = form.client_secret
    try {
      const r = await fetch(`${API_BASE}/api/connectors/m365/${connector!.id}`, {
        method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload)
      })
      const d = await r.json()
      if (r.ok) { setMsg('Updated successfully.'); setEditing(false); load() }
      else setMsg('Error: ' + (d.detail || JSON.stringify(d)))
    } catch (e: any) { setMsg('Failed: ' + e.message) }
    setSaving(false)
  }

  async function sync() {
    setSaving(true); setMsg('Starting sync...')
    await fetch(`${API_BASE}/api/connectors/m365/${connector!.id}/sync`, { method: 'POST' })
    setSaving(false)
    setTimeout(load, 1000)
  }

  async function remove() {
    if (!confirm('Remove Microsoft 365 connector? Indexed files remain searchable.')) return
    await fetch(`${API_BASE}/api/connectors/m365/${connector!.id}`, { method: 'DELETE' })
    setConnector(null); setMsg('')
  }

  const sourceConfig = [
    { id: 'teams', label: 'Teams channels', desc: 'Files shared in Teams channel tabs', color: '#3C3489', bg: '#EEEDFE' },
    { id: 'onedrive', label: 'OneDrive', desc: 'Personal and shared OneDrive folders', color: '#085041', bg: '#E1F5EE' },
    { id: 'sharepoint', label: 'SharePoint', desc: 'Document libraries and site files', color: '#712B13', bg: '#FAECE7' },
  ]

  if (loading) return <div style={{ padding: 20, fontSize: 13, color: '#94A3B8' }}>Loading...</div>

  return (
    <div style={{ background: '#fff', borderRadius: 12, border: '1px solid #E2E8F2', overflow: 'hidden' }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '16px 20px', borderBottom: connector ? '1px solid #E2E8F2' : 'none' }}>
        <div style={{ width: 40, height: 40, borderRadius: 10, background: '#EEEDFE', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <svg width="22" height="22" fill="none" viewBox="0 0 24 24">
            <rect x="2" y="3" width="20" height="14" rx="2" stroke="#534AB7" strokeWidth="1.5"/>
            <path d="M8 21h8M12 17v4" stroke="#534AB7" strokeWidth="1.5" strokeLinecap="round"/>
          </svg>
        </div>
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: 15, fontWeight: 600, color: NAVY }}>Microsoft 365</div>
          <div style={{ fontSize: 12, color: '#64748B', marginTop: 2 }}>Teams · OneDrive · SharePoint</div>
        </div>
        {connector ? <StatusDot status={connector.status} /> : <StatusDot status="disconnected" />}
      </div>

      <div style={{ padding: '16px 20px' }}>
        {/* Connected */}
        {connector && !editing && (
          <>
            <div style={{ display: 'flex', gap: 6, marginBottom: 8, flexWrap: 'wrap' }}>
              {(connector.sources || []).map(s => {
                const cfg = sourceConfig.find(c => c.id === s)
                return cfg ? <span key={s} style={{ fontSize: 11, padding: '3px 10px', borderRadius: 8, background: cfg.bg, color: cfg.color, fontWeight: 500 }}>{cfg.label}</span> : null
              })}
            </div>
            <SyncInfo connector={connector} onSync={sync} />
            <div style={{ marginTop: 8, padding: '7px 12px', background: '#FFF4E0', borderRadius: 8, fontSize: 11, color: '#854F0B' }}>
              Some SharePoint sites may show 403 errors — ask IT to grant admin consent in Azure Portal for full access.
            </div>
            <div style={{ display: 'flex', gap: 8, marginTop: 12 }}>
              <button onClick={() => { setEditing(true); setForm(f => ({ ...f, name: connector.name, sources: connector.sources || f.sources })) }}
                style={{ flex: 1, padding: '8px 0', fontSize: 12, fontWeight: 500, color: NAVY, background: '#F5F7FA', border: '1px solid #E2E8F2', borderRadius: 8, cursor: 'pointer' }}>
                Edit credentials / sources
              </button>
              <button onClick={remove}
                style={{ padding: '8px 16px', fontSize: 12, fontWeight: 500, color: '#EF4444', background: '#FFF5F5', border: '1px solid #FED7D7', borderRadius: 8, cursor: 'pointer' }}>
                Remove
              </button>
            </div>
          </>
        )}

        {/* Connect / Edit form */}
        {(!connector || editing) && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            {editing && <div style={{ fontSize: 12, color: '#64748B', padding: '6px 10px', background: '#FFF4E0', borderRadius: 6 }}>Updating — only fill in the fields you want to change. Leave credentials blank to keep current values.</div>}

            <div>
              <label style={{ fontSize: 12, fontWeight: 500, color: NAVY, display: 'block', marginBottom: 5 }}>Connector name</label>
              <input value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
                style={{ width: '100%', border: '1px solid #E2E8F2', borderRadius: 8, padding: '8px 12px', fontSize: 13, color: NAVY, background: '#F5F7FA', outline: 'none', boxSizing: 'border-box' }} />
            </div>

            <div style={{ background: '#F5F7FA', borderRadius: 10, padding: 14 }}>
              <div style={{ fontSize: 12, fontWeight: 600, color: NAVY, marginBottom: 10 }}>Azure AD credentials</div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                <div>
                  <label style={{ fontSize: 11, color: '#64748B', display: 'block', marginBottom: 4 }}>Directory (Tenant) ID</label>
                  <input value={form.tenant_id} onChange={e => setForm(f => ({ ...f, tenant_id: e.target.value }))}
                    placeholder={editing ? 'Leave blank to keep current' : 'xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx'}
                    style={{ width: '100%', border: '1px solid #E2E8F2', borderRadius: 8, padding: '7px 12px', fontSize: 12, color: NAVY, background: '#fff', outline: 'none', fontFamily: 'monospace', boxSizing: 'border-box' }} />
                </div>
                <div>
                  <label style={{ fontSize: 11, color: '#64748B', display: 'block', marginBottom: 4 }}>Application (Client) ID</label>
                  <input value={form.client_id} onChange={e => setForm(f => ({ ...f, client_id: e.target.value }))}
                    placeholder={editing ? 'Leave blank to keep current' : 'xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx'}
                    style={{ width: '100%', border: '1px solid #E2E8F2', borderRadius: 8, padding: '7px 12px', fontSize: 12, color: NAVY, background: '#fff', outline: 'none', fontFamily: 'monospace', boxSizing: 'border-box' }} />
                </div>
                <div>
                  <label style={{ fontSize: 11, color: '#64748B', display: 'block', marginBottom: 4 }}>Client Secret Value</label>
                  <div style={{ position: 'relative' }}>
                    <input value={form.client_secret} onChange={e => setForm(f => ({ ...f, client_secret: e.target.value }))}
                      type={showSecret ? 'text' : 'password'}
                      placeholder={editing ? 'Leave blank to keep current' : 'Your Azure AD client secret value'}
                      style={{ width: '100%', border: '1px solid #E2E8F2', borderRadius: 8, padding: '7px 36px 7px 12px', fontSize: 12, color: NAVY, background: '#fff', outline: 'none', boxSizing: 'border-box' }} />
                    <button onClick={() => setShowSecret(s => !s)} style={{ position: 'absolute', right: 10, top: '50%', transform: 'translateY(-50%)', background: 'none', border: 'none', cursor: 'pointer', fontSize: 11, color: '#94A3B8' }}>
                      {showSecret ? 'Hide' : 'Show'}
                    </button>
                  </div>
                </div>
              </div>
            </div>

            <div>
              <label style={{ fontSize: 12, fontWeight: 500, color: NAVY, display: 'block', marginBottom: 8 }}>Sources to sync</label>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                {sourceConfig.map(s => (
                  <label key={s.id} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '10px 14px', borderRadius: 8, border: `1px solid ${form.sources.includes(s.id) ? s.bg : '#E2E8F2'}`, background: form.sources.includes(s.id) ? s.bg : '#fff', cursor: 'pointer' }}>
                    <input type="checkbox" checked={form.sources.includes(s.id)} onChange={() => toggleSource(s.id)} style={{ accentColor: s.color, width: 14, height: 14 }} />
                    <div style={{ flex: 1 }}>
                      <div style={{ fontSize: 12, fontWeight: 500, color: form.sources.includes(s.id) ? s.color : NAVY }}>{s.label}</div>
                      <div style={{ fontSize: 11, color: '#94A3B8' }}>{s.desc}</div>
                    </div>
                  </label>
                ))}
              </div>
            </div>

            <div style={{ display: 'flex', gap: 8 }}>
              <button onClick={editing ? update : connect} disabled={saving}
                style={{ flex: 1, padding: '10px 0', fontSize: 13, fontWeight: 600, color: '#fff', background: saving ? '#94A3B8' : '#534AB7', border: 'none', borderRadius: 8, cursor: 'pointer' }}>
                {saving ? 'Saving...' : editing ? 'Save changes' : 'Connect Microsoft 365 & Sync'}
              </button>
              {editing && (
                <button onClick={() => { setEditing(false); setMsg('') }}
                  style={{ padding: '10px 16px', fontSize: 13, color: '#64748B', background: '#F5F7FA', border: '1px solid #E2E8F2', borderRadius: 8, cursor: 'pointer' }}>
                  Cancel
                </button>
              )}
            </div>
          </div>
        )}

        {msg && <div style={{ marginTop: 10, padding: '8px 12px', borderRadius: 8, fontSize: 12, background: msg.startsWith('Error') || msg.startsWith('Failed') ? '#FFF5F5' : '#F0FFF4', color: msg.startsWith('Error') || msg.startsWith('Failed') ? '#991B1B' : '#065F46' }}>{msg}</div>}
      </div>
    </div>
  )
}


// ─── Personal OneDrive Card ──────────────────────────────────────────────────
function PersonalOneDriveCard() {
  const [status, setStatus] = useState<{connected:boolean;upn?:string;files_synced?:number}|null>(null)
  const [step, setStep] = useState<'idle'|'waiting'|'polling'|'syncing'>('idle')
  const [userCode, setUserCode] = useState('')
  const [deviceCode, setDeviceCode] = useState('')
  const [pollInterval, setPollInterval] = useState(5)
  const [msg, setMsg] = useState('')
  const [syncing, setSyncing] = useState(false)

  async function load() {
    try {
      const r = await fetch(`${API_BASE}/api/connectors/personal-od/status`)
      if (r.ok) setStatus(await r.json())
    } catch {}
  }

  useEffect(() => { load() }, [])

  async function startLogin() {
    setMsg(''); setStep('idle')
    try {
      const r = await fetch(`${API_BASE}/api/connectors/personal-od/start`, { method: 'POST' })
      const d = await r.json()
      if (!r.ok) {
        setMsg('Login failed: ' + (d.detail || JSON.stringify(d)))
        return
      }
      setUserCode(d.user_code)
      setDeviceCode(d.device_code)
      setPollInterval(d.interval || 5)
      setStep('waiting')
    } catch (e: any) { setMsg('Failed: ' + e.message) }
  }

  async function pollForToken() {
    setStep('polling'); setMsg('Waiting for you to sign in...')
    try {
      const r = await fetch(`${API_BASE}/api/connectors/personal-od/poll`, {
        method: 'POST', headers: {'Content-Type':'application/json'},
        body: JSON.stringify({ device_code: deviceCode, interval: pollInterval })
      })
      const d = await r.json()
      if (r.ok) {
        setMsg(`Signed in as ${d.upn}. Syncing your files now...`)
        setStep('syncing')
        setTimeout(() => { load(); setStep('idle') }, 5000)
      } else {
        setMsg('Login failed: ' + (d.detail || 'please try again'))
        setStep('idle')
      }
    } catch (e: any) { setMsg('Error: ' + e.message); setStep('idle') }
  }

  async function syncNow() {
    setSyncing(true); setMsg('Syncing...')
    await fetch(`${API_BASE}/api/connectors/personal-od/sync`, { method: 'POST' })
    setMsg('Sync started! Your files will appear in a few minutes.')
    setSyncing(false); setTimeout(load, 5000)
  }

  async function disconnect() {
    if (!confirm('Disconnect your personal OneDrive?')) return
    await fetch(`${API_BASE}/api/connectors/personal-od/disconnect`, { method: 'DELETE' })
    setStatus(null); setStep('idle'); setMsg('')
  }

  return (
    <div style={{ background: '#fff', borderRadius: 12, border: '1px solid #E2E8F2', overflow: 'hidden' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '16px 20px', borderBottom: status?.connected ? '1px solid #E2E8F2' : 'none' }}>
        <div style={{ width: 40, height: 40, borderRadius: 10, background: '#E1F5EE', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 20 }}>
          <svg width="22" height="22" fill="none" viewBox="0 0 24 24"><path d="M3 15a4 4 0 004 4h9a5 5 0 10-.1-9.999 5.002 5.002 0 10-9.78 2.096A4.001 4.001 0 003 15z" stroke="#085041" strokeWidth="1.5"/></svg>
        </div>
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: 15, fontWeight: 600, color: NAVY }}>My Personal OneDrive</div>
          <div style={{ fontSize: 12, color: '#64748B', marginTop: 2 }}>
            {status?.connected ? `Signed in as ${status.upn}` : 'Sign in with your Microsoft account — no admin needed'}
          </div>
        </div>
        {status?.connected ? <StatusDot status="idle" /> : <StatusDot status="disconnected" />}
      </div>

      <div style={{ padding: '16px 20px' }}>
        {status?.connected && (
          <>
            <SyncInfo connector={{ id:'personal', name:'Personal OneDrive', status:'idle', files_synced: status.files_synced||0, last_sync_at: undefined }} onSync={syncNow} />
            <div style={{ display:'flex', gap:8, marginTop:12 }}>
              <button onClick={syncNow} disabled={syncing}
                style={{ flex:1, padding:'8px 0', fontSize:12, fontWeight:500, color:'#085041', background:'#E1F5EE', border:'1px solid #9FE1CB', borderRadius:8, cursor:'pointer' }}>
                {syncing ? 'Syncing...' : 'Sync now'}
              </button>
              <button onClick={disconnect}
                style={{ padding:'8px 16px', fontSize:12, fontWeight:500, color:'#EF4444', background:'#FFF5F5', border:'1px solid #FED7D7', borderRadius:8, cursor:'pointer' }}>
                Disconnect
              </button>
            </div>
          </>
        )}

        {!status?.connected && step === 'idle' && (
          <button onClick={startLogin}
            style={{ width:'100%', padding:'10px 0', fontSize:13, fontWeight:600, color:'#fff', background:'#085041', border:'none', borderRadius:8, cursor:'pointer' }}>
            Sign in with Microsoft to connect My Files
          </button>
        )}

        {step === 'waiting' && (
          <div style={{ display:'flex', flexDirection:'column', gap:12 }}>
            <div style={{ background:'#F0FFF4', border:'1px solid #9FE1CB', borderRadius:10, padding:16 }}>
              <div style={{ fontSize:12, color:'#064E3B', marginBottom:8 }}>Step 1 — Open this URL in your browser:</div>
              <a href="https://microsoft.com/devicelogin" target="_blank" rel="noopener noreferrer"
                style={{ fontSize:13, fontWeight:600, color:'#085041' }}>https://microsoft.com/devicelogin</a>
              <div style={{ fontSize:12, color:'#064E3B', marginTop:10, marginBottom:6 }}>Step 2 — Enter this code:</div>
              <div style={{ fontSize:28, fontWeight:700, color:'#085041', letterSpacing:4, fontFamily:'monospace', textAlign:'center', padding:'10px 0' }}>
                {userCode}
              </div>
              <div style={{ fontSize:11, color:'#64748B', textAlign:'center' }}>Sign in as srinivasan.s@altencalsoftlabs.com</div>
            </div>
            <button onClick={pollForToken}
              style={{ width:'100%', padding:'10px 0', fontSize:13, fontWeight:600, color:'#fff', background:'#085041', border:'none', borderRadius:8, cursor:'pointer' }}>
              I have signed in — continue
            </button>
          </div>
        )}

        {step === 'polling' && (
          <div style={{ display:'flex', alignItems:'center', gap:10, padding:'12px 0', fontSize:12, color:'#64748B' }}>
            <div style={{ width:16, height:16, border:'2px solid #085041', borderTopColor:'transparent', borderRadius:'50%' }} />
            Verifying your login...
          </div>
        )}

        {step === 'syncing' && (
          <div style={{ display:'flex', alignItems:'center', gap:10, padding:'12px 0', fontSize:12, color:'#085041' }}>
            <div style={{ width:16, height:16, border:'2px solid #085041', borderTopColor:'transparent', borderRadius:'50%' }} />
            Syncing your OneDrive files...
          </div>
        )}

        {msg && (
          <div style={{ marginTop:10, padding:'8px 12px', borderRadius:8, fontSize:12,
            background: msg.includes('failed') || msg.includes('Error') ? '#FFF5F5' : '#F0FFF4',
            color: msg.includes('failed') || msg.includes('Error') ? '#991B1B' : '#065F46' }}>
            {msg}
          </div>
        )}
      </div>
    </div>
  )
}

// ─── Local Files Card ────────────────────────────────────────────────────────
function LocalFilesCard() {
  const [os, setOs] = useState<'mac' | 'windows' | null>(null)
  const [folders, setFolders] = useState<string[]>([])
  const [customPath, setCustomPath] = useState('')
  const [syncing, setSyncing] = useState(false)
  const [progress, setProgress] = useState(0)
  const [progressMsg, setProgressMsg] = useState('')
  const [synced, setSynced] = useState(0)
  const [total, setTotal] = useState(0)
  const [done, setDone] = useState(false)
  const [msg, setMsg] = useState('')
  const [vectorCount, setVectorCount] = useState<number | null>(null)

  const macHome = '/Users/' + (window.location.hostname === 'localhost' ? 'srinivasan.s' : 'user')
  const macFolders = [
    { id: macHome + '/Desktop', label: 'Desktop', icon: '🖥️' },
    { id: macHome + '/Documents', label: 'Documents', icon: '📁' },
    { id: macHome + '/Downloads', label: 'Downloads', icon: '⬇️' },
  ]
  const winFolders = [
    { id: '%USERPROFILE%\\Desktop', label: 'Desktop', icon: '🖥️' },
    { id: '%USERPROFILE%\\Documents', label: 'Documents', icon: '📁' },
    { id: '%USERPROFILE%\\Downloads', label: 'Downloads', icon: '⬇️' },
    { id: 'C:\\', label: 'C Drive', icon: '💾' },
    { id: 'D:\\', label: 'D Drive', icon: '💾' },
  ]
  const availableFolders = os === 'mac' ? macFolders : os === 'windows' ? winFolders : []

  useEffect(() => {
    const ua = navigator.userAgent
    if (ua.includes('Mac')) setOs('mac')
    else if (ua.includes('Win')) setOs('windows')
  }, [])

  const [syncedFolders, setSyncedFolders] = useState<Record<string, number>>({})

  useEffect(() => {
    fetch(`${API_BASE}/api/connectors/localfs/status`)
      .then(r => r.json())
      .then(d => {
        setVectorCount(d.files_indexed || 0)
        if (d.folders) setSyncedFolders(d.folders)
      })
      .catch(() => {})
  }, [done])

  function toggleFolder(id: string) {
    setFolders(prev => prev.includes(id) ? prev.filter(f => f !== id) : [...prev, id])
  }
  function addCustomPath() {
    const p = customPath.trim()
    if (!p || folders.includes(p)) return
    setFolders(prev => [...prev, p])
    setCustomPath('')
  }

  async function startSync() {
    if (folders.length === 0) { setMsg('Please select at least one folder'); return }
    setSyncing(true); setDone(false); setProgress(0); setSynced(0); setTotal(0); setMsg('')
    try {
      setProgressMsg('Scanning folders...')
      const scanResp = await fetch(`${API_BASE}/api/ingest/localfs-scan`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ folders, os }),
      })
      if (!scanResp.ok) {
        const err = await scanResp.json()
        setMsg('Scan failed: ' + (err.detail || 'Unknown error'))
        setSyncing(false); return
      }
      const { files } = await scanResp.json()
      setTotal(files.length)
      if (files.length === 0) {
        setMsg('No supported files found in selected folders.')
        setSyncing(false); return
      }
      setProgressMsg(`Found ${files.length} files. Uploading...`)
      let uploaded = 0
      for (let idx = 0; idx < files.length; idx++) {
        const filePath = files[idx]
        try {
          const controller = new AbortController()
          const timer = setTimeout(() => controller.abort(), 60000)
          const uploadResp = await fetch(`${API_BASE}/api/ingest/localfs-sync-file`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ file_path: filePath, os }),
            signal: controller.signal,
          })
          clearTimeout(timer)
          if (uploadResp.ok) uploaded++
        } catch {
          console.warn(`Skipped: ${filePath}`)
        }
        setSynced(uploaded)
        setProgress(Math.round(((idx + 1) / files.length) * 100))
        setProgressMsg(`Uploading: ${filePath.split(/[\\/]/).pop()}`)
      }
      setProgress(100); setProgressMsg('Sync complete!'); setDone(true); setSyncing(false)
      setMsg(`✓ ${uploaded} of ${files.length} files indexed successfully.`)
    } catch (e: any) {
      setMsg('Error: ' + e.message); setSyncing(false)
    }
  }

  return (
    <div style={{ background: '#fff', borderRadius: 12, border: '1px solid #E2E8F2', overflow: 'hidden' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '16px 20px', borderBottom: '1px solid #E2E8F2' }}>
        <div style={{ width: 40, height: 40, borderRadius: 10, background: '#ECFDF5', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 20 }}>💻</div>
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: 15, fontWeight: 600, color: NAVY }}>Local Files</div>
          <div style={{ fontSize: 12, color: '#64748B', marginTop: 2 }}>Sync files from your Desktop, Documents or custom folders</div>
        </div>
        {vectorCount !== null && vectorCount > 0 ? <StatusDot status="idle" /> : <StatusDot status="disconnected" />}
      </div>
      <div style={{ padding: '16px 20px', display: 'flex', flexDirection: 'column', gap: 14 }}>
        {vectorCount !== null && vectorCount > 0 && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '8px 12px', background: '#F5F7FA', borderRadius: 8, fontSize: 12, color: '#64748B' }}>
            <span><strong style={{ color: NAVY }}>{vectorCount}</strong> files indexed from local folders</span>
          </div>
        )}
        <div>
          <label style={{ fontSize: 12, fontWeight: 600, color: NAVY, display: 'block', marginBottom: 8 }}>Select your operating system</label>
          <div style={{ display: 'flex', gap: 10 }}>
            {[{ id: 'mac', label: '🍎  macOS', desc: 'Mac, MacBook' }, { id: 'windows', label: '🪟  Windows', desc: 'Windows 10/11' }].map(o => (
              <button key={o.id} onClick={() => { setOs(o.id as 'mac' | 'windows'); setFolders([]) }}
                style={{ flex: 1, padding: '10px 0', borderRadius: 10, border: `2px solid ${os === o.id ? '#065F46' : '#E2E8F2'}`, background: os === o.id ? '#ECFDF5' : '#F5F7FA', cursor: 'pointer', color: os === o.id ? '#065F46' : '#64748B', fontWeight: os === o.id ? 600 : 400, fontSize: 13 }}>
                {o.label}
                <div style={{ fontSize: 10, color: '#94A3B8', marginTop: 2 }}>{o.desc}</div>
              </button>
            ))}
          </div>
        </div>
        {os && (
          <div>
            <label style={{ fontSize: 12, fontWeight: 600, color: NAVY, display: 'block', marginBottom: 8 }}>Select folders to sync</label>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              {availableFolders.map(f => {
                const alreadySynced = (vectorCount ?? 0) > 0 && syncedFolders[f.id] !== undefined
                return (
                  <label key={f.id} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '10px 14px', borderRadius: 8, cursor: 'pointer', border: `1px solid ${folders.includes(f.id) ? '#6EE7B7' : '#E2E8F2'}`, background: folders.includes(f.id) ? '#ECFDF5' : '#F5F7FA' }}>
                    <input type="checkbox" checked={folders.includes(f.id)} onChange={() => toggleFolder(f.id)} style={{ accentColor: '#065F46', width: 14, height: 14 }} />
                    <span style={{ fontSize: 16 }}>{f.icon}</span>
                    <div style={{ flex: 1 }}>
                      <div style={{ fontSize: 13, fontWeight: 500, color: folders.includes(f.id) ? '#065F46' : NAVY }}>{f.label}</div>
                      <div style={{ fontSize: 11, color: '#94A3B8', fontFamily: 'monospace' }}>{f.id}</div>
                    </div>
                    {alreadySynced && (
                      <span style={{ fontSize: 10, padding: '2px 8px', borderRadius: 8, background: '#ECFDF5', color: '#065F46', fontWeight: 600, border: '1px solid #6EE7B7', whiteSpace: 'nowrap' }}>
                        ✓ Synced
                      </span>
                    )}
                  </label>
                )
              })}
            </div>
            <div style={{ marginTop: 8 }}>
              <label style={{ fontSize: 11, color: '#64748B', display: 'block', marginBottom: 4 }}>+ Add custom folder path</label>
              <div style={{ display: 'flex', gap: 6 }}>
                <input value={customPath} onChange={e => setCustomPath(e.target.value)} onKeyDown={e => e.key === 'Enter' && addCustomPath()}
                  placeholder={os === 'mac' ? '/Users/you/Projects' : 'C:\\Users\\You\\Projects'}
                  style={{ flex: 1, border: '1px solid #E2E8F2', borderRadius: 8, padding: '7px 12px', fontSize: 12, color: NAVY, background: '#F5F7FA', outline: 'none', fontFamily: 'monospace' }} />
                <button onClick={addCustomPath} style={{ padding: '7px 14px', background: NAVY, color: '#fff', border: 'none', borderRadius: 8, fontSize: 12, fontWeight: 600, cursor: 'pointer' }}>Add</button>
              </div>
              {folders.filter(f => !availableFolders.find(af => af.id === f)).map(cp => (
                <div key={cp} style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 6, padding: '6px 10px', background: '#ECFDF5', borderRadius: 6, border: '1px solid #6EE7B7' }}>
                  <span style={{ fontSize: 12, color: '#065F46', fontFamily: 'monospace', flex: 1 }}>{cp}</span>
                  <button onClick={() => setFolders(prev => prev.filter(f => f !== cp))} style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#EF4444', fontSize: 14 }}>×</button>
                </div>
              ))}
            </div>
          </div>
        )}
        {os && folders.length > 0 && !syncing && !done && (
          <button onClick={startSync} style={{ padding: '11px 0', fontSize: 13, fontWeight: 600, color: '#fff', background: '#065F46', border: 'none', borderRadius: 8, cursor: 'pointer' }}>
            Sync {folders.length} folder{folders.length > 1 ? 's' : ''} to IntelliRAG
          </button>
        )}
        {syncing && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, color: '#64748B' }}>
              <span style={{ color: NAVY, fontWeight: 500 }}>{progressMsg}</span>
              <span>{synced} / {total} files</span>
            </div>
            <div style={{ height: 8, background: '#E2E8F2', borderRadius: 99, overflow: 'hidden' }}>
              <div style={{ height: '100%', borderRadius: 99, background: 'linear-gradient(90deg, #065F46, #10B981)', width: `${progress}%`, transition: 'width 0.3s ease' }} />
            </div>
            <div style={{ textAlign: 'right', fontSize: 11, color: '#065F46', fontWeight: 600 }}>{progress}%</div>
          </div>
        )}
        {done && !syncing && (
          <button onClick={() => { setDone(false); setFolders([]); setProgress(0) }} style={{ padding: '11px 0', fontSize: 13, fontWeight: 600, color: '#065F46', background: '#ECFDF5', border: '1px solid #6EE7B7', borderRadius: 8, cursor: 'pointer' }}>
            ✓ Sync another folder
          </button>
        )}
        <div style={{ fontSize: 11, color: '#94A3B8' }}>Supported: PDF, DOCX, XLSX, PPTX, TXT · Subfolders included · Image-only PDFs skipped</div>
        {msg && (
          <div style={{ padding: '8px 12px', borderRadius: 8, fontSize: 12, background: msg.startsWith('✓') ? '#F0FFF4' : '#FFF5F5', color: msg.startsWith('✓') ? '#065F46' : '#991B1B' }}>{msg}</div>
        )}
      </div>
    </div>
  )
}


// ─── Main ConnectorsPanel ────────────────────────────────────────────────────
export default function ConnectorsPanel() {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      <div>
        <h1 style={{ fontSize: 20, fontWeight: 600, color: NAVY, margin: 0 }}>Connectors</h1>
        <p style={{ fontSize: 13, color: '#64748B', marginTop: 4 }}>Connect external sources. Files sync automatically and become searchable in the widget. You can update credentials or trigger a manual sync at any time.</p>
      </div>

      {/* How it works banner */}
      <div style={{ background: '#F0F4FF', border: '1px solid #C7D2FE', borderRadius: 10, padding: '12px 16px', fontSize: 12, color: '#3730A3', lineHeight: 1.6 }}>
        <strong>How it works:</strong> Connected sources are automatically indexed into IntelliRAG. When a user asks a question in the widget and selects a source pill (Google Drive, Teams, SharePoint, OneDrive), only that source is searched. Use <strong>Sync now</strong> to pull the latest files after any changes.
      </div>

      <GoogleDriveCard />
      <Microsoft365Card />
      <PersonalOneDriveCard />
      <LocalFilesCard />

      {/* Auto-Sync */}
      <div style={{ background: '#fff', borderRadius: 12, border: '1px solid #E2E8F2', overflow: 'hidden' }}>
        <div style={{ padding: '16px 20px', borderBottom: '1px solid #F1F5F9', display: 'flex', alignItems: 'center', gap: 12 }}>
          <div style={{ width: 40, height: 40, borderRadius: 10, background: '#ECFDF5', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 20 }}>🔄</div>
          <div>
            <div style={{ fontSize: 14, fontWeight: 600, color: NAVY }}>Auto-Sync</div>
            <div style={{ fontSize: 12, color: '#64748B' }}>Watch folders and automatically index new or changed files</div>
          </div>
        </div>
        <div style={{ padding: 20 }}>
          <AutoSyncPanel />
        </div>
      </div>

      {/* Confluence coming soon */}
      <div style={{ background: '#fff', borderRadius: 12, border: '1px dashed #E2E8F2', padding: 20, opacity: 0.6, display: 'flex', alignItems: 'center', gap: 12 }}>
        <div style={{ width: 40, height: 40, borderRadius: 10, background: '#F5F7FA', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 18, fontWeight: 700, color: '#94A3B8' }}>C</div>
        <div>
          <div style={{ fontSize: 14, fontWeight: 600, color: '#94A3B8' }}>Confluence</div>
          <div style={{ fontSize: 12, color: '#CBD5E1' }}>Coming in Phase 4</div>
        </div>
        <span style={{ marginLeft: 'auto', fontSize: 10, padding: '3px 10px', borderRadius: 10, background: '#F5F7FA', color: '#CBD5E1', fontWeight: 600 }}>Coming soon</span>
      </div>
    </div>
  )
}
