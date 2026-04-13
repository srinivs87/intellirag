import { useState, useRef, useEffect, useCallback } from 'react'
import { ChatMessage, HistoryMessage } from '@/types/chat'
import { query, getHistory, clearSession } from '@/lib/api/query'
import { SESSION_KEY } from '@/lib/constants'

function getWelcomeMessage(name?: string): ChatMessage {
  return {
    id: 'welcome',
    role: 'assistant',
    text: `Hi ${name || 'there'}! Welcome to ACL IntelliRAG. Use the source pills above to choose where to search.`,
  }
}

export function useChat(tenant: string, userName?: string) {
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [restoring, setRestoring] = useState(true)
  const bottomRef = useRef<HTMLDivElement>(null)

  // Restore session on mount
  useEffect(() => {
    async function restore() {
      const stored = localStorage.getItem(SESSION_KEY(tenant))
      if (stored) {
        try {
          const history: HistoryMessage[] = await getHistory(stored)
          if (history.length > 0) {
            setSessionId(stored)
            setMessages(history.map((m, i) => ({
              id: `restored_${i}`,
              role: m.role,
              text: m.content,
            })))
          } else {
            localStorage.removeItem(SESSION_KEY(tenant))
            setMessages([getWelcomeMessage(userName)])
          }
        } catch {
          setMessages([getWelcomeMessage(userName)])
        }
      } else {
        setMessages([getWelcomeMessage(userName)])
      }
      setRestoring(false)
    }
    restore()
  }, [tenant, userName])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const sendMessage = useCallback(async (
    question: string,
    sources: string[],
  ) => {
    if (!question.trim() || loading) return

    const userMsg: ChatMessage = { id: Date.now().toString(), role: 'user', text: question }
    setMessages((prev) => [...prev, userMsg])
    setLoading(true)

    try {
      const res = await query({
        tenant,
        question,
        session_id: sessionId || undefined,
        sources: sources.length > 0 ? sources : undefined,
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
    } catch {
      setMessages((prev) => [...prev, {
        id: Date.now().toString() + '_err',
        role: 'assistant',
        text: 'Something went wrong. Please try again.',
      }])
    } finally {
      setLoading(false)
    }
  }, [loading, sessionId, tenant])

  const startNewConversation = useCallback(async () => {
    if (sessionId) {
      await clearSession(sessionId)
      localStorage.removeItem(SESSION_KEY(tenant))
    }
    setSessionId(null)
    setMessages([getWelcomeMessage(userName)])
  }, [sessionId, tenant, userName])

  return { messages, loading, restoring, bottomRef, sendMessage, startNewConversation, sessionId }
}
