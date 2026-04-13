import { apiFetch, API_BASE } from './client'

export interface IngestResponse {
  document_id: string
  filename: string
  status: string
  chunks_created: number
  message?: string
}

export async function uploadDocument(file: File, tenant: string): Promise<IngestResponse> {
  const form = new FormData()
  form.append('file', file)
  form.append('tenant', tenant)
  form.append('uploaded_by', 'admin-ui')
  const res = await fetch(`${API_BASE}/api/ingest/upload`, { method: 'POST', body: form })
  if (!res.ok) throw new Error(`Upload failed: ${res.statusText}`)
  return res.json()
}

export async function listDocuments(tenant: string) {
  return apiFetch<any[]>(`/api/ingest/documents?tenant=${tenant}`)
}

export async function deleteDocument(documentId: string) {
  return apiFetch(`/api/ingest/documents/${documentId}`, { method: 'DELETE' })
}

export async function getWidgetSnippet(tenant: string): Promise<string> {
  const base = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'
  return `<script\n  src="${base}/widget.js"\n  data-tenant="${tenant}"\n  data-theme="light"\n  data-position="bottom-right"\n></script>`
}

export async function health(): Promise<{ status: string }> {
  return apiFetch('/health/')
}
