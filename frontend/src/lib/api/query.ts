import { apiFetch, API_BASE } from './client'
import { QueryRequest, QueryResponse, HistoryMessage } from '@/types/chat'

export async function query(req: QueryRequest): Promise<QueryResponse> {
  return apiFetch<QueryResponse>('/api/query/', {
    method: 'POST',
    body: JSON.stringify(req),
  })
}

export async function getHistory(sessionId: string): Promise<HistoryMessage[]> {
  try {
    const data = await apiFetch<{ messages: HistoryMessage[] }>(
      `/api/query/history/${sessionId}`
    )
    return data.messages || []
  } catch {
    return []
  }
}

export async function clearSession(sessionId: string): Promise<void> {
  await fetch(`${API_BASE}/api/query/session/${sessionId}`, { method: 'DELETE' })
}
