'use client'
import { useState, useEffect, useRef } from 'react'

const NAVY = '#060B4E', ORANGE = '#FA9600'
const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'
const PAGE_SIZE = 10

interface Doc {
  document_id: string
  filename: string
  chunk_count: number
  uploaded_by: string
  collection?: string
  web_url?: string
  file_path?: string
}

function FileIcon({ filename }: { filename: string }) {
  const ext = filename.split('.').pop()?.toLowerCase() || ''
  const map: Record<string, [string, string]> = {
    pdf: ['#EF4444','PDF'], docx: ['#2563EB','DOC'], doc: ['#2563EB','DOC'],
    xlsx: ['#16A34A','XLS'], xls: ['#16A34A','XLS'],
    pptx: ['#EA580C','PPT'], ppt: ['#EA580C','PPT'],
    txt: ['#64748B','TXT'], md: ['#6366F1','MD'],
  }
  const [bg, label] = map[ext] || ['#94A3B8', ext.slice(0,3).toUpperCase() || 'DOC']
  return (
    <div style={{ width: 30, height: 34, borderRadius: 4, background: bg, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 7, fontWeight: 700, color: '#fff', flexShrink: 0, letterSpacing: '.03em' }}>{label}</div>
  )
}

function SourceBadge({ uploadedBy, collection }: { uploadedBy: string; collection?: string }) {
  const src = uploadedBy?.includes('gdrive') ? { label: 'Google Drive', bg: '#E6F1FB', color: '#0C447C' }
    : uploadedBy?.includes('sharepoint') || collection?.includes('sharepoint') ? { label: 'SharePoint', bg: '#FAECE7', color: '#712B13' }
    : uploadedBy?.includes('teams') || collection?.includes('teams') ? { label: 'Teams', bg: '#EEEDFE', color: '#3C3489' }
    : uploadedBy?.includes('onedrive') || collection?.includes('onedrive') ? { label: 'OneDrive', bg: '#E1F5EE', color: '#085041' }
    : { label: 'Uploaded', bg: '#F1F5F9', color: '#475569' }
  return <span style={{ fontSize: 10, padding: '2px 8px', borderRadius: 6, background: src.bg, color: src.color, fontWeight: 500, whiteSpace: 'nowrap' }}>{src.label}</span>
}

export default function DocumentsTable() {
  const [allDocs, setAllDocs] = useState<Doc[]>([])
  const [loading, setLoading] = useState(true)
  const [uploading, setUploading] = useState(false)
  const [deletingId, setDeletingId] = useState<string | null>(null)
  const [uploadResults, setUploadResults] = useState<any[]>([])
  const [dragOver, setDragOver] = useState(false)
  const [syncNeeded, setSyncNeeded] = useState(false)
  const [syncing, setSyncing] = useState(false)
  const [syncStatus, setSyncStatus] = useState('')
  const [search, setSearch] = useState('')
  const [sortBy, setSortBy] = useState<'name' | 'chunks' | 'source'>('name')
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('asc')
  const [filterSource, setFilterSource] = useState('all')
  const [page, setPage] = useState(1)
  const fileRef = useRef<HTMLInputElement>(null)

  async function load() {
    setLoading(true)
    try {
      const collections = ['uploaded', 'general', 'gdrive', 'sharepoint', 'teams', 'onedrive', 'hr']
      const allResults: Doc[] = []
      await Promise.all(collections.map(async (col) => {
        try {
          const r = await fetch(`${API_BASE}/api/ingest/documents?tenant=${col}`)
          if (!r.ok) return
          const d = await r.json()
          allResults.push(...(d.documents || []).map((doc: Doc) => ({ ...doc, collection: doc.collection || col })))
        } catch {}
      }))
      const seen = new Set<string>()
      setAllDocs(allResults.filter(d => { if (seen.has(d.document_id)) return false; seen.add(d.document_id); return true }))
    } catch {}
    setLoading(false)
  }

  useEffect(() => { load() }, [])

  async function uploadFiles(files: File[]) {
    if (!files.length) return
    setUploading(true); setUploadResults([])
    const results = []
    for (const file of files) {
      const fd = new FormData()
      fd.append('file', file); fd.append('tenant', 'uploaded'); fd.append('uploaded_by', 'admin-ui')
      try {
        const r = await fetch(`${API_BASE}/api/ingest/upload`, { method: 'POST', body: fd })
        const d = await r.json()
        if (r.ok) results.push({ filename: file.name, status: 'success', chunks: d.chunks_created })
        else results.push({ filename: file.name, status: 'error', error: d.detail || 'Upload failed' })
      } catch (e: any) { results.push({ filename: file.name, status: 'error', error: e.message }) }
    }
    setUploadResults(results); setUploading(false); load()
  }

  async function deleteDoc(doc: Doc) {
    if (!confirm(`Delete "${doc.filename}"?\nThis removes it from the knowledge base.`)) return
    setDeletingId(doc.document_id)
    await fetch(`${API_BASE}/api/ingest/documents/${doc.document_id}?tenant=${doc.collection || 'uploaded'}`, { method: 'DELETE' })
    setAllDocs(prev => prev.filter(d => d.document_id !== doc.document_id))
    setDeletingId(null)
  }

  async function openFile(doc: Doc) {
    const ub = doc.uploaded_by || ''
    const col = doc.collection || ''
    const isM365 = ub.includes('m365') || ub.includes('sharepoint') || ub.includes('teams') || ub.includes('onedrive') || ['sharepoint','teams','onedrive'].includes(col)
    const isGdrive = ub.includes('gdrive') || col === 'gdrive'
    const isUploaded = !isM365 && !isGdrive

    // Case 1: has web_url stored → open directly, no API call needed
    if (doc.web_url) {
      window.open(doc.web_url, '_blank')
      return
    }

    // Case 2: uploaded file → serve from MinIO
    if (isUploaded) {
      window.open(`${API_BASE}/api/ingest/documents/${doc.document_id}/download?tenant=${doc.collection || 'uploaded'}`, '_blank')
      return
    }

    // Case 3: connector file with no web_url → show sync banner
    // Don't fire API calls here — that's what was spamming 404s
    setSyncNeeded(true)
  }

  async function triggerSync() {
    setSyncing(true)
    setSyncStatus('Preparing to fetch file links...')
    try {
      const r = await fetch(`${API_BASE}/api/connectors/m365/`)
      const d = r.ok ? await r.json() : { connectors: [] }
      for (const c of (d.connectors || [])) {
        await fetch(`${API_BASE}/api/connectors/m365/${c.id}/populate-links`, { method: 'POST' })
      }
      setSyncStatus('Done! Reloading...')
      setTimeout(() => {
        load().then(() => { setSyncing(false); setSyncNeeded(false); setSyncStatus('') })
      }, 3000)
    } catch {
      setSyncStatus('Failed — try refreshing the page.')
      setSyncing(false)
    }
  }

  function toggleSort(col: 'name' | 'chunks' | 'source') {
    if (sortBy === col) setSortDir(d => d === 'asc' ? 'desc' : 'asc')
    else { setSortBy(col); setSortDir('asc') }
    setPage(1)
  }

  const getSourceKey = (doc: Doc) => {
    const ub = doc.uploaded_by || ''
    if (ub.includes('gdrive')) return 'gdrive'
    if (ub.includes('sharepoint') || doc.collection?.includes('sharepoint')) return 'sharepoint'
    if (ub.includes('teams') || doc.collection?.includes('teams')) return 'teams'
    if (ub.includes('onedrive') || doc.collection?.includes('onedrive')) return 'onedrive'
    return 'uploaded'
  }

  const sourceLabels: Record<string, string> = { all: 'All sources', gdrive: 'Google Drive', sharepoint: 'SharePoint', teams: 'Teams', onedrive: 'OneDrive', uploaded: 'Uploaded' }
  const sources = ['all', ...Array.from(new Set(allDocs.map(getSourceKey)))]

  const filtered = allDocs
    .filter(d => {
      if (search && !d.filename.toLowerCase().includes(search.toLowerCase())) return false
      if (filterSource !== 'all' && getSourceKey(d) !== filterSource) return false
      return true
    })
    .sort((a, b) => {
      let cmp = 0
      if (sortBy === 'name') cmp = a.filename.localeCompare(b.filename)
      else if (sortBy === 'chunks') cmp = a.chunk_count - b.chunk_count
      else if (sortBy === 'source') cmp = getSourceKey(a).localeCompare(getSourceKey(b))
      return sortDir === 'asc' ? cmp : -cmp
    })

  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE))
  const pageDocs = filtered.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE)

  const SortArrow = ({ col }: { col: string }) => (
    <span style={{ fontSize: 10, marginLeft: 3, color: sortBy === col ? NAVY : '#CBD5E1' }}>
      {sortBy === col ? (sortDir === 'asc' ? '↑' : '↓') : '↕'}
    </span>
  )

  const isConnectorFile = (doc: Doc) => {
    const ub = doc.uploaded_by || ''
    const col = doc.collection || ''
    return ub.includes('gdrive') || ub.includes('m365') || ub.includes('sharepoint') || ub.includes('teams') || ub.includes('onedrive') || ['sharepoint','teams','onedrive','gdrive'].includes(col)
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>

      {/* Upload zone */}
      <div
        onDragOver={e => { e.preventDefault(); setDragOver(true) }}
        onDragLeave={() => setDragOver(false)}
        onDrop={e => { e.preventDefault(); setDragOver(false); uploadFiles(Array.from(e.dataTransfer.files)) }}
        onClick={() => fileRef.current?.click()}
        style={{ border: `2px dashed ${dragOver ? ORANGE : uploading ? '#10B981' : '#CBD5E1'}`, borderRadius: 12, padding: '24px 20px', textAlign: 'center', cursor: 'pointer', background: dragOver ? '#FFF4E0' : '#fff', transition: 'all .15s' }}>
        <input ref={fileRef} type="file" multiple accept=".pdf,.docx,.doc,.xlsx,.xls,.pptx,.ppt,.txt,.md" style={{ display: 'none' }}
          onChange={e => uploadFiles(Array.from(e.target.files || []))} />
        <div style={{ fontSize: 28, marginBottom: 6 }}>{uploading ? '⏳' : '📂'}</div>
        <div style={{ fontSize: 14, fontWeight: 500, color: uploading ? '#10B981' : NAVY }}>
          {uploading ? 'Uploading and indexing...' : 'Click to upload or drag & drop files here'}
        </div>
        <div style={{ fontSize: 11, color: '#94A3B8', marginTop: 3 }}>PDF · Word · Excel · PowerPoint · TXT · Markdown — max 50 MB each</div>
      </div>

      {/* Upload results */}
      {uploadResults.length > 0 && (
        <div style={{ background: '#fff', borderRadius: 10, border: '1px solid #E2E8F2', padding: 12 }}>
          {uploadResults.map((r, i) => (
            <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '4px 0', borderBottom: i < uploadResults.length - 1 ? '1px solid #F1F5F9' : 'none', fontSize: 12 }}>
              <div style={{ width: 7, height: 7, borderRadius: '50%', background: r.status === 'success' ? '#10B981' : '#EF4444', flexShrink: 0 }} />
              <span style={{ flex: 1, color: NAVY }}>{r.filename}</span>
              {r.chunks && <span style={{ color: '#94A3B8' }}>{r.chunks} chunks</span>}
              {r.error && <span style={{ color: '#EF4444' }}>{r.error}</span>}
            </div>
          ))}
        </div>
      )}

      {/* Sync banner */}
      {syncNeeded && (
        <div style={{ padding: '12px 16px', background: '#FFF4E0', border: '1px solid #FED7AA', borderRadius: 10, fontSize: 12, color: '#854F0B' }}>
          {!syncing ? (
            <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
              <span style={{ flex: 1 }}>File links not available yet — these files were synced before link tracking was added. Click <strong>Sync now</strong> to update. After sync completes the table will refresh and Open will work.</span>
              <button onClick={triggerSync}
                style={{ padding: '6px 16px', background: '#F59E0B', color: '#fff', border: 'none', borderRadius: 7, fontSize: 12, fontWeight: 600, cursor: 'pointer', flexShrink: 0, whiteSpace: 'nowrap' }}>
                Sync now
              </button>
              <button onClick={() => setSyncNeeded(false)} style={{ background: 'none', border: 'none', color: '#94A3B8', cursor: 'pointer', fontSize: 20, lineHeight: 1, padding: '0 2px' }}>×</button>
            </div>
          ) : (
            <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
              <div style={{ width: 16, height: 16, border: '2px solid #F59E0B', borderTopColor: 'transparent', borderRadius: '50%', animation: 'spin 0.8s linear infinite', flexShrink: 0 }} />
              <span style={{ flex: 1, fontWeight: 500 }}>{syncStatus}</span>
            </div>
          )}
        </div>
      )}
      <style>{`@keyframes spin { to { transform: rotate(360deg) } }`}</style>

      {/* Table */}
      <div style={{ background: '#fff', borderRadius: 12, border: '1px solid #E2E8F2', overflow: 'hidden' }}>

        {/* Toolbar */}
        <div style={{ padding: '12px 16px', borderBottom: '1px solid #E2E8F2', display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'center' }}>
          <div style={{ position: 'relative', flex: 1, minWidth: 180 }}>
            <svg style={{ position: 'absolute', left: 10, top: '50%', transform: 'translateY(-50%)', pointerEvents: 'none' }} width="13" height="13" fill="none" viewBox="0 0 24 24">
              <circle cx="11" cy="11" r="8" stroke="#94A3B8" strokeWidth="2"/>
              <path d="M21 21l-4.35-4.35" stroke="#94A3B8" strokeWidth="2" strokeLinecap="round"/>
            </svg>
            <input value={search} onChange={e => { setSearch(e.target.value); setPage(1) }} placeholder="Search by filename..."
              style={{ width: '100%', border: '1px solid #E2E8F2', borderRadius: 8, padding: '6px 10px 6px 30px', fontSize: 12, color: NAVY, background: '#F5F7FA', outline: 'none', boxSizing: 'border-box' }} />
          </div>
          <select value={filterSource} onChange={e => { setFilterSource(e.target.value); setPage(1) }}
            style={{ border: '1px solid #E2E8F2', borderRadius: 8, padding: '6px 10px', fontSize: 12, color: NAVY, background: '#F5F7FA', cursor: 'pointer' }}>
            {sources.map(s => <option key={s} value={s}>{sourceLabels[s] || s}</option>)}
          </select>
          <span style={{ fontSize: 12, color: '#94A3B8', whiteSpace: 'nowrap' }}>{filtered.length} document{filtered.length !== 1 ? 's' : ''}</span>
          <button onClick={load} style={{ fontSize: 11, color: '#64748B', background: '#F5F7FA', border: '1px solid #E2E8F2', borderRadius: 6, padding: '5px 10px', cursor: 'pointer', whiteSpace: 'nowrap' }}>↻ Refresh</button>
        </div>

        {/* Header */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 80px 120px 160px', padding: '8px 16px', background: '#F8FAFC', borderBottom: '1px solid #E2E8F2' }}>
          {[['name','File name'],['chunks','Chunks'],['source','Source']].map(([col, label]) => (
            <div key={col} onClick={() => toggleSort(col as 'name'|'chunks'|'source')}
              style={{ fontSize: 11, fontWeight: 600, color: '#64748B', textTransform: 'uppercase', letterSpacing: '.04em', cursor: 'pointer', userSelect: 'none', display: 'flex', alignItems: 'center' }}>
              {label}<SortArrow col={col} />
            </div>
          ))}
          <div style={{ fontSize: 11, fontWeight: 600, color: '#64748B', textTransform: 'uppercase', letterSpacing: '.04em' }}>Actions</div>
        </div>

        {/* Body */}
        {loading ? (
          <div style={{ padding: '40px 0', textAlign: 'center', color: '#94A3B8', fontSize: 13 }}>Loading documents...</div>
        ) : pageDocs.length === 0 ? (
          <div style={{ padding: '48px 0', textAlign: 'center' }}>
            <div style={{ fontSize: 32, marginBottom: 8 }}>📭</div>
            <div style={{ fontSize: 13, color: '#94A3B8' }}>{search || filterSource !== 'all' ? 'No documents match your search' : 'No documents yet — upload files above'}</div>
          </div>
        ) : (
          pageDocs.map((doc, i) => (
            <div key={doc.document_id}
              style={{ display: 'grid', gridTemplateColumns: '1fr 80px 120px 160px', padding: '10px 16px', alignItems: 'center', borderBottom: i < pageDocs.length - 1 ? '1px solid #F1F5F9' : 'none', background: deletingId === doc.document_id ? '#FFF5F5' : 'transparent' }}>

              {/* Filename */}
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, minWidth: 0 }}>
                <FileIcon filename={doc.filename} />
                <span style={{ fontSize: 12, color: NAVY, fontWeight: 500, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={doc.filename}>
                  {doc.filename}
                </span>
              </div>

              {/* Chunks */}
              <div style={{ display: 'inline-flex', alignItems: 'center', gap: 4, fontSize: 12, color: '#334155' }}>
                <span style={{ width: 6, height: 6, borderRadius: '50%', background: '#10B981', display: 'inline-block', flexShrink: 0 }} />
                {doc.chunk_count}
              </div>

              {/* Source */}
              <div>
                <SourceBadge uploadedBy={doc.uploaded_by} collection={doc.collection} />
              </div>

              {/* Actions */}
              <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                <button
                  onClick={() => openFile(doc)}
                  style={{ fontSize: 11, padding: '4px 10px', borderRadius: 6, border: `1px solid ${isConnectorFile(doc) ? '#9FE1CB' : '#B5D4F4'}`, background: isConnectorFile(doc) ? '#E1F5EE' : '#E6F1FB', color: isConnectorFile(doc) ? '#085041' : '#0C447C', cursor: 'pointer', fontWeight: 500, whiteSpace: 'nowrap' }}>
                  {isConnectorFile(doc) ? 'Open ↗' : 'Open'}
                </button>
                <button
                  onClick={() => deleteDoc(doc)}
                  disabled={deletingId === doc.document_id}
                  style={{ fontSize: 11, padding: '4px 10px', borderRadius: 6, border: '1px solid #FED7D7', background: '#FFF5F5', color: '#EF4444', cursor: 'pointer', fontWeight: 500, whiteSpace: 'nowrap' }}>
                  {deletingId === doc.document_id ? '…' : 'Delete'}
                </button>
              </div>

            </div>
          ))
        )}

        {/* Pagination */}
        {totalPages > 1 && (
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '10px 16px', borderTop: '1px solid #E2E8F2', background: '#F8FAFC' }}>
            <span style={{ fontSize: 12, color: '#64748B' }}>Page {page} of {totalPages} · {filtered.length} total</span>
            <div style={{ display: 'flex', gap: 4 }}>
              <button onClick={() => setPage(1)} disabled={page === 1} style={{ fontSize: 11, padding: '4px 8px', borderRadius: 6, border: '1px solid #E2E8F2', background: '#fff', color: page === 1 ? '#CBD5E1' : NAVY, cursor: page === 1 ? 'default' : 'pointer' }}>«</button>
              <button onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page === 1} style={{ fontSize: 11, padding: '4px 8px', borderRadius: 6, border: '1px solid #E2E8F2', background: '#fff', color: page === 1 ? '#CBD5E1' : NAVY, cursor: page === 1 ? 'default' : 'pointer' }}>‹</button>
              {Array.from({ length: Math.min(5, totalPages) }, (_, idx) => {
                const p = Math.max(1, Math.min(totalPages - 4, page - 2)) + idx
                return <button key={p} onClick={() => setPage(p)} style={{ fontSize: 11, padding: '4px 9px', borderRadius: 6, border: `1px solid ${p === page ? NAVY : '#E2E8F2'}`, background: p === page ? NAVY : '#fff', color: p === page ? '#fff' : NAVY, cursor: 'pointer', fontWeight: p === page ? 600 : 400 }}>{p}</button>
              })}
              <button onClick={() => setPage(p => Math.min(totalPages, p + 1))} disabled={page === totalPages} style={{ fontSize: 11, padding: '4px 8px', borderRadius: 6, border: '1px solid #E2E8F2', background: '#fff', color: page === totalPages ? '#CBD5E1' : NAVY, cursor: page === totalPages ? 'default' : 'pointer' }}>›</button>
              <button onClick={() => setPage(totalPages)} disabled={page === totalPages} style={{ fontSize: 11, padding: '4px 8px', borderRadius: 6, border: '1px solid #E2E8F2', background: '#fff', color: page === totalPages ? '#CBD5E1' : NAVY, cursor: page === totalPages ? 'default' : 'pointer' }}>»</button>
            </div>
          </div>
        )}
      </div>

      <div style={{ padding: '8px 14px', background: '#F0F4FF', border: '1px solid #C7D2FE', borderRadius: 8, fontSize: 11, color: '#3730A3' }}>
        <strong>Tip:</strong> In the chat widget, select <strong>Uploaded Docs</strong> to search manually uploaded files, or <strong>Google Drive / SharePoint / Teams</strong> for connector files.
      </div>
    </div>
  )
}
