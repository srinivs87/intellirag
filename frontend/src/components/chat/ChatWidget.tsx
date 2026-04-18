'use client'
import { useState } from 'react'
import { AuthUser } from '@/types/auth'
import { SourceKey } from '@/types/connector'
import { useChat } from '@/hooks/useChat'
import { ChatMessage } from './ChatMessage'
import { ChatInput } from './ChatInput'
import { SourcePills } from './SourcePills'
import { FollowUpSuggestions } from './FollowUpSuggestions'

interface ChatWidgetProps {
  tenant?: string
  user: AuthUser
  allowedSources: SourceKey[]
  onLogout?: () => void
}

const BOUNCE_CSS = `
  @keyframes bounce {
    0%, 80%, 100% { transform: translateY(0); }
    40% { transform: translateY(-4px); }
  }
  .typing-dot {
    width: 6px; height: 6px; border-radius: 50%;
    background: #94A3B8; display: inline-block;
    animation: bounce 1.2s infinite;
  }
`

export function ChatWidget({ tenant = 'general', user, allowedSources, onLogout }: ChatWidgetProps) {
  const [input, setInput] = useState('')
  const [activeSources, setActiveSources] = useState<SourceKey[]>(allowedSources)
  const { messages, loading, restoring, bottomRef, suggestions, setSuggestions, sendMessage, startNewConversation, sessionId } = useChat(tenant, user.name)

  function toggleSource(source: SourceKey) {
    setActiveSources((prev) =>
      prev.includes(source)
        ? prev.length === 1 ? prev : prev.filter((s) => s !== source)
        : [...prev, source]
    )
  }

  async function handleSend() {
    const q = input.trim()
    if (!q || loading) return
    setInput('')
    await sendMessage(q, activeSources)
  }

  function handleSuggestionSelect(s: string) {
    setInput(s)
    setSuggestions([])
  }

  return (
    <div className="flex flex-col h-full w-full bg-white rounded-xl border border-slate-200 overflow-hidden shadow-sm">
      <style>{BOUNCE_CSS}</style>

      {/* Source pills bar */}
      <div className="bg-slate-900 shrink-0">
        <div className="flex items-center justify-between px-4 py-2">
          <SourcePills
            availableSources={allowedSources}
            activeSources={activeSources}
            onToggle={toggleSource}
          />
          <button
            onClick={startNewConversation}
            className="text-xs text-white/60 hover:text-white/90 bg-white/10 hover:bg-white/20 px-3 py-1 rounded-full border border-white/10 transition-all cursor-pointer ml-4 shrink-0"
          >
            + New chat
          </button>
        </div>
      </div>

      {/* Session resumed banner */}
      {!restoring && sessionId && messages.length > 1 && (
        <div className="bg-amber-50 border-b border-amber-100 px-4 py-2 text-xs text-amber-700 flex items-center gap-2 shrink-0">
          <div className="w-1.5 h-1.5 rounded-full bg-amber-400" />
          Conversation resumed · 7-day memory active
        </div>
      )}

      {/* Messages area */}
      <div className="flex-1 overflow-y-auto px-4 py-6 flex flex-col gap-4 bg-slate-50">
        {restoring ? (
          <div className="flex justify-center items-center h-full text-slate-400 text-sm">
            Restoring conversation...
          </div>
        ) : messages.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full gap-3 text-center">
            <div className="w-14 h-14 rounded-full bg-[#060B4E] flex items-center justify-center text-white font-bold text-xl">
              IR
            </div>
            <p className="text-slate-600 font-medium">How can I help you today?</p>
            <p className="text-slate-400 text-sm">Ask anything about your documents</p>
          </div>
        ) : (
          messages.map((msg) => (
            <ChatMessage
              key={msg.id}
              message={msg}
              userInitial={(user.name?.[0] || 'U').toUpperCase()}
            />
          ))
        )}

        {/* Typing indicator */}
        {loading && (
          <div className="flex gap-3 items-end">
            <div className="w-8 h-8 rounded-full bg-[#060B4E] flex items-center justify-center text-xs font-bold text-white shrink-0">
              IR
            </div>
            <div className="bg-white border border-slate-200 px-4 py-3 rounded-2xl rounded-bl-sm flex gap-1 shadow-sm">
              <span className="typing-dot" style={{ animationDelay: '0ms' }} />
              <span className="typing-dot" style={{ animationDelay: '150ms' }} />
              <span className="typing-dot" style={{ animationDelay: '300ms' }} />
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Follow-up suggestions */}
      <FollowUpSuggestions suggestions={suggestions} onSelect={handleSuggestionSelect} />

      {/* Input area */}
      <div className="bg-white border-t border-slate-200 shrink-0 px-4 pb-3 pt-2">
        <ChatInput value={input} onChange={setInput} onSend={handleSend} loading={loading} />
        <p className="text-center text-xs text-slate-400 mt-1">
          All data stays on-premise · ACL IntelliRAG
        </p>
      </div>
    </div>
  )
}
