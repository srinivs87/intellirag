import { useState, useRef, useEffect, useCallback } from 'react'
import { ChatMessage, HistoryMessage } from '@/types/chat'
import { query, getHistory, clearSession } from '@/lib/api/query'
import { SESSION_KEY } from '@/lib/constants'

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8001'

function getWelcomeMessage(name?: string): ChatMessage {
  return {
    id: 'welcome',
    role: 'assistant',
    text: `Hi ${name || 'there'}! Welcome to ACL IntelliRAG. Use the source pills above to choose where to search.`,
  }
}

async function fetchSuggestions(question: string, answer: string): Promise<string[]> {
  try {
    const res = await fetch(`${API_BASE}/api/query/suggestions`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ prompt: `Based on this Q&A, suggest 3 short follow-up questions (max 8 words each). Return ONLY a JSON array. Q: ${question} A: ${answer.slice(0, 300)}` }),
    })
    const data = await res.json()
    return Array.isArray(data.suggestions) ? data.suggestions.slice(0, 3) : []
  } catch { return [] }
}

export function useChat(tenant: string, userName?: string, userId?: string, userRole?: string) {
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [restoring, setRestoring] = useState(true)
  const [suggestions, setSuggestions] = useState<string[]>([])
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    async function restore() {
      const stored = localStorage.getItem(SESSION_KEY(tenant))
      if (stored) {
        try {
          const history: HistoryMessage[] = await getHistory(stored)
          if (history.length > 0) {
            setSessionId(stored)
            setMessages(history.map((m, i) => ({ id: `restored_${i}`, role: m.role, text: m.content })))
          } else {
            localStorage.removeItem(SESSION_KEY(tenant))
            setMessages([getWelcomeMessage(userName)])
          }
        } catch { setMessages([getWelcomeMessage(userName)]) }
      } else { setMessages([getWelcomeMessage(userName)]) }
      setRestoring(false)
    }
    restore()
  }, [tenant, userName])

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [messages])

  // ── Standard text query ────────────────────────────────────────────────────
  const sendMessage = useCallback(async (question: string, sources: string[]) => {
    if (!question.trim() || loading) return
    setSuggestions([])
    const userMsg: ChatMessage = { id: Date.now().toString(), role: 'user', text: question }
    setMessages((prev) => [...prev, userMsg])
    setLoading(true)
    try {
      const res = await query({
        tenant,
        question,
        session_id: sessionId || undefined,
        sources: sources.length > 0 ? sources : undefined,
        user_context: userId ? { user_id: userId, role: userRole || 'user' } : undefined,
      })
      if (res.session_id) {
        setSessionId(res.session_id)
        localStorage.setItem(SESSION_KEY(tenant), res.session_id)
      }
      setMessages((prev) => [...prev, {
        id: Date.now().toString() + '_bot',
        role: 'assistant',
        text: res.answer,
        sources: res.sources,
        confidence: res.confidence,
        ms: res.total_ms,
      }])
      fetchSuggestions(question, res.answer).then(setSuggestions)
    } catch {
      setMessages((prev) => [...prev, {
        id: Date.now().toString() + '_err',
        role: 'assistant',
        text: 'Something went wrong. Please try again.',
      }])
    } finally { setLoading(false) }
  }, [loading, sessionId, tenant])

  // ── Attachment query ───────────────────────────────────────────────────────
  const sendMessageWithAttachment = useCallback(async (
    question: string,
    sources: string[],
    file: File,
  ) => {
    if (!question.trim() || loading) return
    setSuggestions([])

    // Show user message with attachment indicator
    const userMsg: ChatMessage = {
      id: Date.now().toString(),
      role: 'user',
      text: question,
      attachment: { name: file.name, size: file.size, type: file.type },
    }
    setMessages((prev) => [...prev, userMsg])
    setLoading(true)

    try {
      const formData = new FormData()
      formData.append('question', question)
      formData.append('tenant', tenant)
      if (sessionId) formData.append('session_id', sessionId)
      if (sources.length > 0) formData.append('sources', sources.join(','))
      formData.append('file', file)

      const res = await fetch(`${API_BASE}/api/query/with-attachment`, {
        method: 'POST',
        body: formData,
      })

      if (!res.ok) {
        const err = await res.json()
        throw new Error(err.detail || 'Attachment query failed')
      }

      const data = await res.json()

      if (data.session_id) {
        setSessionId(data.session_id)
        localStorage.setItem(SESSION_KEY(tenant), data.session_id)
      }

      setMessages((prev) => [...prev, {
        id: Date.now().toString() + '_bot',
        role: 'assistant',
        text: data.answer,
        sources: data.sources,
        confidence: data.confidence,
        ms: data.total_ms,
        attachmentType: data.attachment_type,
      }])

      fetchSuggestions(question, data.answer).then(setSuggestions)
    } catch (err: any) {
      setMessages((prev) => [...prev, {
        id: Date.now().toString() + '_err',
        role: 'assistant',
        text: `⚠️ ${err.message || 'Could not process attachment. Please try again.'}`,
      }])
    } finally { setLoading(false) }
  }, [loading, sessionId, tenant])

  const startNewConversation = useCallback(async () => {
    if (sessionId) {
      await clearSession(sessionId)
      localStorage.removeItem(SESSION_KEY(tenant))
    }
    setSessionId(null)
    setSuggestions([])
    setMessages([getWelcomeMessage(userName)])
  }, [sessionId, tenant, userName])

  return {
    messages, loading, restoring, bottomRef,
    suggestions, setSuggestions,
    sendMessage, sendMessageWithAttachment,
    startNewConversation, sessionId,
  }
}
