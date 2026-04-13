'use client'
import { useState } from 'react'
import { AuthUser } from '@/types/auth'
import { SourceKey } from '@/types/connector'
import { useChat } from '@/hooks/useChat'
import { ChatMessage } from './ChatMessage'
import { ChatInput } from './ChatInput'
import { SourcePills } from './SourcePills'
import { NAVY, ORANGE, BLUE, ROLE_COLORS } from '@/lib/constants'

interface ChatWidgetProps {
  tenant?: string
  user: AuthUser
  allowedSources: SourceKey[]
  fullScreen?: boolean
  onLogout?: () => void
  onNewConversation?: () => void
}

const BOUNCE_CSS = `@keyframes bounce{0%,80%,100%{transform:translateY(0)}40%{transform:translateY(-4px)}}`

export function ChatWidget({
  tenant = 'general',
  user,
  allowedSources,
  fullScreen = false,
  onLogout,
  onNewConversation,
}: ChatWidgetProps) {
  const [input, setInput] = useState('')
  const [activeSources, setActiveSources] = useState<SourceKey[]>(allowedSources)

  const { messages, loading, restoring, bottomRef, sendMessage, startNewConversation, sessionId } =
    useChat(tenant, user.name)

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

  async function handleNew() {
    await startNewConversation()
    onNewConversation?.()
  }

  const containerStyle = fullScreen
    ? { display: 'flex', flexDirection: 'column' as const, height: '100%', width: '100%', background: '#fff', fontFamily: 'Inter, system-ui, sans-serif' }
    : { display: 'flex', flexDirection: 'column' as const, background: '#fff', borderRadius: 16, border: '1px solid #E2E8F2', overflow: 'hidden', height: 580, width: '100%', maxWidth: 420, fontFamily: 'Inter, system-ui, sans-serif', boxShadow: '0 4px 24px rgba(6,11,78,0.10)' }

  return (
    <div style={containerStyle}>
      <style>{BOUNCE_CSS}</style>

      {/* Widget Header */}
      <div style={{ background: NAVY, flexShrink: 0 }}>
        <div className="flex items-center gap-2.5 px-3.5 py-3">
          <img src="/acl-logo.png" alt="ACL" style={{ height: 26, width: 'auto' }} />
          <div style={{ width: 1, height: 20, background: 'rgba(255,255,255,0.2)' }} />
          <span className="font-semibold text-sm text-white flex-1">ACL IntelliRAG</span>
          <div className="flex items-center gap-1.5">
            <div className="w-2 h-2 rounded-full bg-emerald-400" />
            <span className="text-xs text-white/60 bg-white/10 px-2 py-0.5 rounded-full">{tenant}</span>
            <span className="text-xs font-bold text-white px-1.5 py-0.5 rounded capitalize"
              style={{ background: ROLE_COLORS[user.role] || '#94A3B8' }}>
              {user.role}
            </span>
            <button onClick={handleNew} title="New conversation"
              className="text-xs text-white/70 bg-white/10 px-2 py-1 rounded-md border-none cursor-pointer">
              + New
            </button>
            {onLogout && (
              <button onClick={onLogout} title="Sign out"
                className="text-xs text-white/50 bg-white/8 border border-white/15 px-1.5 py-1 rounded-md cursor-pointer">
                ⏏
              </button>
            )}
          </div>
        </div>
        <div style={{ display: 'flex', height: 2 }}>
          <div style={{ width: '65%', background: ORANGE }} />
          <div style={{ width: '35%', background: BLUE }} />
        </div>
        <SourcePills availableSources={allowedSources} activeSources={activeSources} onToggle={toggleSource} />
      </div>

      {/* Session resumed banner */}
      {!restoring && sessionId && messages.length > 1 && (
        <div className="bg-amber-50 px-3.5 py-1.5 text-xs text-amber-800 flex items-center gap-1.5 shrink-0">
          <div className="w-1.5 h-1.5 rounded-full" style={{ background: ORANGE }} />
          Conversation resumed · 7-day memory active
        </div>
      )}

      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-3.5 flex flex-col gap-3">
        {restoring ? (
          <div className="flex justify-center items-center h-full text-slate-400 text-sm">
            Restoring conversation...
          </div>
        ) : (
          messages.map((msg) => (
            <ChatMessage key={msg.id} message={msg} userInitial={(user.name?.[0] || 'U').toUpperCase()} />
          ))
        )}

        {/* Typing indicator */}
        {loading && (
          <div className="flex gap-2 items-end self-start">
            <div className="w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold text-white shrink-0"
              style={{ background: NAVY }}>IR</div>
            <div className="bg-slate-100 px-3 py-2.5 rounded-xl rounded-bl-sm flex gap-1">
              {[0, 150, 300].map((d) => (
                <span key={d} style={{ width: 6, height: 6, borderRadius: '50%', background: '#94A3B8', display: 'inline-block', animation: 'bounce 1.2s infinite', animationDelay: `${d}ms` }} />
              ))}
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      <ChatInput value={input} onChange={setInput} onSend={handleSend} loading={loading} />
    </div>
  )
}
