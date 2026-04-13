// Re-exports for backward compatibility
export type { QueryRequest, QueryResponse, HistoryMessage } from '@/types/chat'
export { query, getHistory, clearSession } from '@/lib/api/query'
export { uploadDocument, health, getWidgetSnippet } from '@/lib/api/documents'

// Legacy api object for components still using api.xxx pattern
const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

export const api = {
  async query(req: any) {
    const { query } = await import('@/lib/api/query')
    return query(req)
  },
  async getHistory(sessionId: string) {
    const { getHistory } = await import('@/lib/api/query')
    return getHistory(sessionId)
  },
  async clearSession(sessionId: string) {
    const { clearSession } = await import('@/lib/api/query')
    return clearSession(sessionId)
  },
  async uploadDocument(file: File, tenant: string) {
    const { uploadDocument } = await import('@/lib/api/documents')
    return uploadDocument(file, tenant)
  },
  async health() {
    const { health } = await import('@/lib/api/documents')
    return health()
  },
  getWidgetSnippet(tenant: string) {
    return `<script\n  src="${API_BASE}/widget.js"\n  data-tenant="${tenant}"\n  data-theme="light"\n  data-position="bottom-right"\n></script>`
  },
}
