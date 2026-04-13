export interface SourceReference {
  filename: string
  document_id: string
  chunk_index: number
  relevance_score: number
  web_url?: string
  file_path?: string
  source_type?: string
}

export interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  text: string
  sources?: SourceReference[]
  confidence?: number
  ms?: number
}

export interface QueryRequest {
  tenant: string
  question: string
  session_id?: string
  top_k?: number
  user_context?: Record<string, string>
  sources?: string[]
}

export interface QueryResponse {
  query_id: string
  session_id: string
  answer: string
  sources: SourceReference[]
  confidence: number
  retrieval_ms: number
  generation_ms: number
  total_ms: number
  chunks_used: number
}

export interface HistoryMessage {
  role: 'user' | 'assistant'
  content: string
  created_at?: string
}

export interface ChartData {
  labels: string[]
  values: number[]
  chartType: 'bar' | 'pie' | 'line'
}
