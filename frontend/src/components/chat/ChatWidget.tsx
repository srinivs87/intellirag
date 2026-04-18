'use client'
import { useState } from 'react'
import { AuthUser } from '@/types/auth'
import { SourceKey } from '@/types/connector'
import { useChat } from '@/hooks/useChat'
import { ChatMessage } from './ChatMessage'
import { ChatInput } from './ChatInput'
import { SourcePills } from './SourcePills'
import { FollowUpSuggestions } from './FollowUpSuggestions'
import { NAVY } from '@/lib/constants'

interface ChatWidgetProps {
  tenant?: string
  user: AuthUser
  allowedSources: SourceKey[]
}

const BOUNCE_CSS = `@keyframes bounce{0%,80%,100%{transform:translateY(0)}40%{transform:translateY(-4px)}}`

export function ChatWidget({ tenant = 'general', user, allowedSources }: ChatWidgetProps) {
  const [input, setInput] = useState('')

  const defaultSource: SourceKey = allowedSources.includes('localfs')
    ? 'localfs'
    : allowedSources[0]

  const [activeSource, setActiveSource] = useState<SourceKey>(defaultSource)

  const {
    messages, loading, restoring, bottomRef,
    suggestions, setSuggestions,
    sendMessage, sendMessageWithAttachment,
    startNewConversation, sessionId,
  } = useChat(tenant, user.name)

  async function handleSend() {
    const q = input.trim()
    if (!q || loading) return
    setInput('')
    await sendMessage(q, [activeSource])
  }

  async function handleSendWithAttachment(file: File) {
    const q = input.trim()
    if (!q || loading) return
    setInput('')
    await sendMessageWithAttachment(q, [activeSource], file)
  }

  function handleSuggestionSelect(s: string) {
    setInput(s)
    setSuggestions([])
  }

  return (
    <div className="flex flex-col h-full w-full bg-white rounded-xl border border-slate-200 overflow-hidden shadow-sm">
      <style>{BOUNCE_CSS}</style>

      {/* ── Source bar — light, clean ── */}
      <div className="bg-slate-50 border-b border-slate-200 shrink-0">
        <div className="flex items-center justify-between px-4 py-2.5 gap-3">
          <SourcePills
            availableSources={allowedSources}
            activeSource={activeSource}
            onSelect={setActiveSource}
          />
          <div className="flex items-center gap-2 shrink-0">
            {!restoring && sessionId && messages.length > 1 && (
              <span className="text-xs text-amber-600 bg-amber-50 border border-amber-200 px-2 py-0.5 rounded-full whitespace-nowrap">
                Memory active
              </span>
            )}
            <button
              onClick={startNewConversation}
              className="text-xs text-slate-500 bg-white border border-slate-200 rounded-lg px-3 py-1.5 hover:bg-slate-50 transition-colors cursor-pointer whitespace-nowrap"
            >
              + New chat
            </button>
          </div>
        </div>
      </div>

      {/* ── Messages — internal scroll only ── */}
      <div className="flex-1 overflow-y-auto min-h-0 px-4 py-4 flex flex-col gap-3">
        {restoring ? (
          <div className="flex justify-center items-center h-full text-slate-400 text-sm">
            Restoring conversation...
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

        {loading && (
          <div className="flex gap-2 items-end self-start">
            <div
              className="w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold text-white shrink-0"
              style={{ background: NAVY }}
            >
              IR
            </div>
            <div className="bg-slate-100 px-3 py-2.5 rounded-xl rounded-bl-sm flex gap-1 items-center">
              {[0, 150, 300].map((d) => (
                <span
                  key={d}
                  className="inline-block rounded-full"
                  style={{
                    width: 6, height: 6,
                    background: '#94A3B8',
                    animation: 'bounce 1.2s infinite',
                    animationDelay: `${d}ms`,
                  }}
                />
              ))}
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* ── Follow-up suggestions ── */}
      <FollowUpSuggestions suggestions={suggestions} onSelect={handleSuggestionSelect} />

      {/* ── Input with attachment support ── */}
      <ChatInput
        value={input}
        onChange={setInput}
        onSend={handleSend}
        onSendWithAttachment={handleSendWithAttachment}
        loading={loading}
      />
    </div>
  )
}
