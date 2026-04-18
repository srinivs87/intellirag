'use client'
import { useRef, KeyboardEvent } from 'react'
import { NAVY, ORANGE } from '@/lib/constants'
import { VoiceInputButton } from './VoiceInputButton'

interface ChatInputProps {
  value: string
  onChange: (val: string) => void
  onSend: () => void
  loading: boolean
  placeholder?: string
}

export function ChatInput({ value, onChange, onSend, loading, placeholder }: ChatInputProps) {
  const ref = useRef<HTMLTextAreaElement>(null)

  function handleKey(e: KeyboardEvent) {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); onSend() }
  }

  return (
    <div className="px-3 py-2.5 border-t border-slate-200 bg-white shrink-0">
      <div className="flex gap-2 items-end">
        <textarea
          ref={ref}
          rows={1}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={handleKey}
          placeholder={placeholder || 'Ask anything about your documents...'}
          className="flex-1 resize-none border border-slate-200 rounded-xl px-3 py-2.5 text-sm bg-slate-50 outline-none focus:ring-2 focus:ring-[#060B4E]/20 focus:border-[#060B4E] max-h-24 font-[inherit] leading-relaxed"
          style={{ color: NAVY }}
        />
        <VoiceInputButton onTranscript={onChange} disabled={loading} />
        <button
          onClick={onSend}
          disabled={loading || !value.trim()}
          className="w-9 h-9 rounded-full border-none shrink-0 flex items-center justify-center transition-all duration-150"
          style={{
            background: loading || !value.trim() ? '#CBD5E1' : ORANGE,
            cursor: loading || !value.trim() ? 'not-allowed' : 'pointer',
          }}
        >
          <svg width="15" height="15" fill="none" viewBox="0 0 24 24">
            <path d="M22 2L11 13M22 2L15 22l-4-9-9-4 20-7z" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </button>
      </div>
      <p className="text-center text-xs text-slate-400 mt-1.5">
        7-day memory active · All data stays on-premise · ACL IntelliRAG
      </p>
    </div>
  )
}
