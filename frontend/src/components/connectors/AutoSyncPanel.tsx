'use client'
import { useState, useEffect, useRef } from 'react'

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8001'

interface SyncFolder {
  id: string
  path: string
  enabled: boolean
  interval_s: number
  last_sync: string | null
}

interface SyncStatus {
  scheduler_running: boolean
  last_sync: string | null
  last_sync_result: Record<string, any> | null
  folders_count: number
  files_watched: number
  folders: SyncFolder[]
}

interface SyncEvent {
  type: string
  data?: Record<string, any>
  ts?: string
}

interface PreviewFile {
  name: string
  path: string
  size_kb: number
  ext: string
}

const INTERVAL_OPTIONS = [
  { label: '1 minute',   value: 60 },
  { label: '5 minutes',  value: 300 },
  { label: '15 minutes', value: 900 },
  { label: '30 minutes', value: 1800 },
  { label: '1 hour',     value: 3600 },
]

const EXT_ICONS: Record<string, string> = {
  '.pdf': '📄', '.docx': '📝', '.doc': '📝',
  '.xlsx': '📊', '.xls': '📊',
  '.pptx': '📑', '.ppt': '📑',
  '.txt': '📃', '.csv': '📃', '.md': '📃',
}

function formatTime(iso: string | null): string {
  if (!iso) return 'Never'
  const d = new Date(iso)
  const now = new Date()
  const diff = Math.floor((now.getTime() - d.getTime()) / 1000)
  if (diff < 60) return 'Just now'
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`
  return d.toLocaleDateString()
}

function formatInterval(seconds: number): string {
  const opt = INTERVAL_OPTIONS.find(o => o.value === seconds)
  if (opt) return opt.label
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m`
  return `${Math.floor(seconds / 3600)}h`
}

export function AutoSyncPanel() {
  const [status, setStatus] = useState<SyncStatus | null>(null)
  const [loading, setLoading] = useState(true)
  const [syncing, setSyncing] = useState(false)
  const [folderPath, setFolderPath] = useState('')
  const [interval, setInterval_] = useState(300)
  const [adding, setAdding] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)
  const [events, setEvents] = useState<SyncEvent[]>([])
  const [preview, setPreview] = useState<{ files: PreviewFile[]; total: number } | null>(null)
  const [previewing, setPreviewing] = useState(false)
  const eventsRef = useRef<HTMLDivElement>(null)

  // Load status
  async function loadStatus() {
    try {
      const res = await fetch(`${API_BASE}/api/autosync/status`)
      if (res.ok) setStatus(await res.json())
    } catch { /* silent */ }
    setLoading(false)
  }

  useEffect(() => {
    loadStatus()
    const interval = window.setInterval(loadStatus, 15000)
    return () => window.clearInterval(interval)
  }, [])

  // SSE stream for real-time events
  useEffect(() => {
    const es = new EventSource(`${API_BASE}/api/autosync/stream`)
    es.onmessage = (e) => {
      try {
        const event: SyncEvent = JSON.parse(e.data)
        if (event.type === 'heartbeat') return
        setEvents(prev => [event, ...prev].slice(0, 20))
        if (event.type === 'sync_completed') {
          loadStatus()
          setSyncing(false)
        }
        if (event.type === 'sync_started') setSyncing(true)
      } catch { /* ignore */ }
    }
    return () => es.close()
  }, [])

  // Auto-scroll events
  useEffect(() => {
    eventsRef.current?.scrollTo({ top: 0, behavior: 'smooth' })
  }, [events])

  async function handleAddFolder() {
    if (!folderPath.trim()) return
    setAdding(true)
    setError(null)
    setSuccess(null)
    try {
      const res = await fetch(`${API_BASE}/api/autosync/folders`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ folder_path: folderPath.trim(), interval_s: interval }),
      })
      const data = await res.json()
      if (!res.ok) {
        setError(data.detail || 'Failed to add folder')
      } else {
        setSuccess(`✓ Folder added — ${data.files_found} files ready to sync`)
        setFolderPath('')
        setPreview(null)
        await loadStatus()
      }
    } catch {
      setError('Failed to connect to server')
    }
    setAdding(false)
  }

  async function handleRemoveFolder(id: string, path: string) {
    if (!confirm(`Remove "${path}" from auto-sync?\n\nExisting indexed files will remain in the knowledge base.`)) return
    try {
      await fetch(`${API_BASE}/api/autosync/folders/${id}`, { method: 'DELETE' })
      await loadStatus()
    } catch { /* silent */ }
  }

  async function handleRunNow() {
    setSyncing(true)
    setError(null)
    try {
      const res = await fetch(`${API_BASE}/api/autosync/run-now`, { method: 'POST' })
      const data = await res.json()
      if (!res.ok) {
        setError(data.detail || 'Sync failed')
        setSyncing(false)
      } else {
        const r = data.result
        setSuccess(`✓ Sync complete — ${r.added} added · ${r.updated} updated · ${r.removed} removed · ${r.skipped} unchanged`)
        await loadStatus()
        setSyncing(false)
      }
    } catch {
      setError('Sync failed — check server connection')
      setSyncing(false)
    }
  }

  async function handlePreview() {
    if (!folderPath.trim()) return
    setPreviewing(true)
    setPreview(null)
    try {
      const res = await fetch(`${API_BASE}/api/autosync/preview?path=${encodeURIComponent(folderPath.trim())}`)
      if (res.ok) setPreview(await res.json())
      else setError('Could not preview folder')
    } catch {
      setError('Preview failed')
    }
    setPreviewing(false)
  }

  const lastResult = status?.last_sync_result

  return (
    <div className="flex flex-col gap-6">

      {/* ── Status bar ── */}
      <div className="bg-white rounded-xl border border-slate-200 p-5">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h2 className="text-base font-semibold text-slate-800">Auto-Sync</h2>
            <p className="text-xs text-slate-500 mt-0.5">
              Automatically keeps the knowledge base in sync with your file system
            </p>
          </div>
          <div className="flex items-center gap-3">
            {/* Scheduler indicator */}
            <div className="flex items-center gap-1.5">
              <div className={`w-2 h-2 rounded-full ${status?.scheduler_running ? 'bg-emerald-500 animate-pulse' : 'bg-slate-300'}`} />
              <span className="text-xs text-slate-500">
                {status?.scheduler_running ? 'Scheduler running' : 'Scheduler stopped'}
              </span>
            </div>
            {/* Sync now button */}
            <button
              onClick={handleRunNow}
              disabled={syncing || (status?.folders_count === 0)}
              className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium text-white transition-all disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer border-none"
              style={{ background: syncing ? '#94A3B8' : '#060B4E' }}
            >
              {syncing ? (
                <>
                  <svg className="animate-spin" width="14" height="14" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="white" strokeWidth="4" />
                    <path className="opacity-75" fill="white" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                  </svg>
                  Syncing...
                </>
              ) : (
                <>
                  <svg width="14" height="14" fill="none" viewBox="0 0 24 24" stroke="white" strokeWidth="2">
                    <path d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" strokeLinecap="round" strokeLinejoin="round"/>
                  </svg>
                  Sync Now
                </>
              )}
            </button>
          </div>
        </div>

        {/* Stats row */}
        <div className="grid grid-cols-4 gap-3">
          {[
            { label: 'Folders Watched', value: status?.folders_count ?? '—' },
            { label: 'Files Monitored', value: status?.files_watched ?? '—' },
            { label: 'Last Sync', value: formatTime(status?.last_sync ?? null) },
            { label: 'Last Result', value: lastResult ? `+${lastResult.added} ~${lastResult.updated} -${lastResult.removed}` : '—' },
          ].map(({ label, value }) => (
            <div key={label} className="bg-slate-50 rounded-lg p-3 text-center">
              <p className="text-lg font-bold text-slate-800">{value}</p>
              <p className="text-xs text-slate-500 mt-0.5">{label}</p>
            </div>
          ))}
        </div>

        {/* Feedback */}
        {error && (
          <div className="mt-3 bg-red-50 border border-red-200 rounded-lg px-4 py-2.5 text-xs text-red-700">
            {error}
          </div>
        )}
        {success && (
          <div className="mt-3 bg-emerald-50 border border-emerald-200 rounded-lg px-4 py-2.5 text-xs text-emerald-700">
            {success}
          </div>
        )}
      </div>

      {/* ── Add folder ── */}
      <div className="bg-white rounded-xl border border-slate-200 p-5">
        <h3 className="text-sm font-semibold text-slate-800 mb-3">Add Folder to Watch</h3>
        <div className="flex gap-2 mb-2">
          <input
            type="text"
            value={folderPath}
            onChange={(e) => {
              setFolderPath(e.target.value)
              setPreview(null)
              setError(null)
              setSuccess(null)
            }}
            placeholder="/Users/srinivasan.s/Documents/Finance"
            className="flex-1 border border-slate-200 rounded-lg px-3 py-2 text-sm outline-none focus:border-blue-400 focus:ring-2 focus:ring-blue-100 text-slate-700"
          />
          <select
            value={interval}
            onChange={(e) => setInterval_(Number(e.target.value))}
            className="border border-slate-200 rounded-lg px-3 py-2 text-sm text-slate-600 outline-none focus:border-blue-400 cursor-pointer bg-white"
          >
            {INTERVAL_OPTIONS.map(opt => (
              <option key={opt.value} value={opt.value}>{opt.label}</option>
            ))}
          </select>
          <button
            onClick={handlePreview}
            disabled={!folderPath.trim() || previewing}
            className="px-3 py-2 rounded-lg text-sm border border-slate-200 text-slate-600 hover:bg-slate-50 disabled:opacity-40 cursor-pointer transition-colors bg-white"
          >
            Preview
          </button>
          <button
            onClick={handleAddFolder}
            disabled={!folderPath.trim() || adding}
            className="px-4 py-2 rounded-lg text-sm font-medium text-white border-none cursor-pointer disabled:opacity-50 transition-colors"
            style={{ background: '#F97316' }}
          >
            {adding ? 'Adding...' : 'Add Folder'}
          </button>
        </div>
        <p className="text-xs text-slate-400">
          Enter the full path to a folder on this machine. All supported files (PDF, DOCX, XLSX, PPTX…) will be indexed automatically.
        </p>

        {/* Folder preview */}
        {preview && (
          <div className="mt-3 border border-slate-200 rounded-lg overflow-hidden">
            <div className="bg-slate-50 px-3 py-2 flex items-center justify-between border-b border-slate-200">
              <span className="text-xs font-medium text-slate-600">
                Preview — {preview.total} files found
                {preview.total > 50 ? ' (showing first 50)' : ''}
              </span>
            </div>
            <div className="max-h-48 overflow-y-auto">
              {preview.files.map((file, i) => (
                <div key={i} className="flex items-center gap-2 px-3 py-1.5 border-b border-slate-100 last:border-0 hover:bg-slate-50">
                  <span className="text-sm shrink-0">{EXT_ICONS[file.ext] || '📎'}</span>
                  <span className="text-xs text-slate-700 flex-1 truncate">{file.name}</span>
                  <span className="text-xs text-slate-400 shrink-0">{file.size_kb}KB</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* ── Watched folders ── */}
      {status && status.folders.length > 0 && (
        <div className="bg-white rounded-xl border border-slate-200 overflow-hidden">
          <div className="px-5 py-3 border-b border-slate-100 bg-slate-50">
            <h3 className="text-sm font-semibold text-slate-800">Watched Folders</h3>
          </div>
          <div className="divide-y divide-slate-100">
            {status.folders.map((folder) => (
              <div key={folder.id} className="flex items-center gap-3 px-5 py-3">
                <div className="w-2 h-2 rounded-full bg-emerald-500 shrink-0" />
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-slate-800 truncate">{folder.path}</p>
                  <p className="text-xs text-slate-400 mt-0.5">
                    Every {formatInterval(folder.interval_s)} · Last sync: {formatTime(folder.last_sync)}
                  </p>
                </div>
                <button
                  onClick={() => handleRemoveFolder(folder.id, folder.path)}
                  className="text-xs text-slate-400 hover:text-red-500 transition-colors cursor-pointer border-none bg-transparent px-2 py-1"
                >
                  Remove
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ── Live event log ── */}
      {events.length > 0 && (
        <div className="bg-white rounded-xl border border-slate-200 overflow-hidden">
          <div className="px-5 py-3 border-b border-slate-100 bg-slate-50 flex items-center justify-between">
            <h3 className="text-sm font-semibold text-slate-800">Live Sync Events</h3>
            <button
              onClick={() => setEvents([])}
              className="text-xs text-slate-400 hover:text-slate-600 cursor-pointer border-none bg-transparent"
            >
              Clear
            </button>
          </div>
          <div ref={eventsRef} className="max-h-48 overflow-y-auto divide-y divide-slate-100">
            {events.map((event, i) => (
              <div key={i} className="flex items-start gap-3 px-5 py-2.5">
                <span className="text-lg shrink-0">
                  {event.type === 'file_synced' && (event.data?.action === 'added' ? '✅' : '🔄')}
                  {event.type === 'file_removed' && '🗑️'}
                  {event.type === 'sync_started' && '🔄'}
                  {event.type === 'sync_completed' && '✅'}
                  {event.type === 'connected' && '🔌'}
                </span>
                <div className="flex-1 min-w-0">
                  <p className="text-xs text-slate-700">
                    {event.type === 'file_synced' && `${event.data?.action === 'added' ? 'New file indexed' : 'File updated'}: ${event.data?.filename}`}
                    {event.type === 'file_removed' && `Removed from index: ${event.data?.filename}`}
                    {event.type === 'sync_started' && `Sync started — scanning ${event.data?.folders} folder(s)`}
                    {event.type === 'sync_completed' && `Sync complete — +${event.data?.added} updated ${event.data?.updated} removed ${event.data?.removed}`}
                    {event.type === 'connected' && 'Connected to sync stream'}
                  </p>
                  {event.ts && (
                    <p className="text-xs text-slate-400 mt-0.5">{new Date(event.ts).toLocaleTimeString()}</p>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Empty state */}
      {!loading && status?.folders_count === 0 && (
        <div className="bg-slate-50 rounded-xl border border-dashed border-slate-300 p-10 text-center">
          <div className="text-4xl mb-3">📁</div>
          <h3 className="text-sm font-semibold text-slate-700 mb-1">No folders configured</h3>
          <p className="text-xs text-slate-500">
            Add a folder path above to start automatic syncing.
            <br />Files will be indexed every time they change.
          </p>
        </div>
      )}
    </div>
  )
}
