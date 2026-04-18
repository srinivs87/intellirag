'use client'
import { useRef, KeyboardEvent, useState, useEffect } from 'react'
import { NAVY, ORANGE } from '@/lib/constants'
import { VoiceInputButton } from './VoiceInputButton'

interface ChatInputProps {
  value: string
  onChange: (val: string) => void
  onSend: () => void
  onSendWithAttachment: (file: File) => void
  loading: boolean
  placeholder?: string
}

const ACCEPTED = '.pdf,.docx,.doc,.xlsx,.xls,.pptx,.ppt,.txt,.csv,.md,.png,.jpg,.jpeg,.webp'
const MAX_SIZE_MB = 10

const FILE_META: Record<string, { icon: string; color: string; bg: string; label: string }> = {
  pdf:  { icon: '📄', color: '#DC2626', bg: '#FEF2F2', label: 'PDF' },
  docx: { icon: '📝', color: '#2563EB', bg: '#EFF6FF', label: 'Word' },
  doc:  { icon: '📝', color: '#2563EB', bg: '#EFF6FF', label: 'Word' },
  xlsx: { icon: '📊', color: '#16A34A', bg: '#F0FDF4', label: 'Excel' },
  xls:  { icon: '📊', color: '#16A34A', bg: '#F0FDF4', label: 'Excel' },
  pptx: { icon: '📑', color: '#EA580C', bg: '#FFF7ED', label: 'PowerPoint' },
  ppt:  { icon: '📑', color: '#EA580C', bg: '#FFF7ED', label: 'PowerPoint' },
  txt:  { icon: '📃', color: '#6B7280', bg: '#F9FAFB', label: 'Text' },
  csv:  { icon: '📃', color: '#6B7280', bg: '#F9FAFB', label: 'CSV' },
  md:   { icon: '📃', color: '#6B7280', bg: '#F9FAFB', label: 'Markdown' },
}

const IMAGE_EXTS = new Set(['png', 'jpg', 'jpeg', 'webp'])

function getExt(filename: string) {
  return filename.split('.').pop()?.toLowerCase() || ''
}

function isImage(filename: string) {
  return IMAGE_EXTS.has(getExt(filename))
}

function formatSize(bytes: number) {
  if (bytes < 1024) return `${bytes}B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)}KB`
  return `${(bytes / 1024 / 1024).toFixed(1)}MB`
}

export function ChatInput({
  value, onChange, onSend, onSendWithAttachment, loading, placeholder
}: ChatInputProps) {
  const textRef = useRef<HTMLTextAreaElement>(null)
  const fileRef = useRef<HTMLInputElement>(null)
  const [attachment, setAttachment] = useState<File | null>(null)
  const [imagePreview, setImagePreview] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  // Generate image preview URL
  useEffect(() => {
    if (!attachment || !isImage(attachment.name)) {
      setImagePreview(null)
      return
    }
    const url = URL.createObjectURL(attachment)
    setImagePreview(url)
    return () => URL.revokeObjectURL(url)
  }, [attachment])

  function handleKey(e: KeyboardEvent) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  function handleSend() {
    if (!value.trim() || loading) return
    if (attachment) {
      onSendWithAttachment(attachment)
      setAttachment(null)
      setImagePreview(null)
    } else {
      onSend()
    }
  }

  function handleFileClick() {
    setError(null)
    fileRef.current?.click()
  }

  function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (!file) return
    if (file.size > MAX_SIZE_MB * 1024 * 1024) {
      setError(`File too large (max ${MAX_SIZE_MB}MB)`)
      e.target.value = ''
      return
    }
    setError(null)
    setAttachment(file)
    e.target.value = ''
    textRef.current?.focus()
  }

  function handleRemove() {
    setAttachment(null)
    setImagePreview(null)
    setError(null)
  }

  // Paste image support
  function handlePaste(e: React.ClipboardEvent) {
    const items = Array.from(e.clipboardData.items)
    const imageItem = items.find(item => item.type.startsWith('image/'))
    if (imageItem) {
      const file = imageItem.getAsFile()
      if (file) {
        const named = new File([file], `pasted-image-${Date.now()}.png`, { type: file.type })
        setAttachment(named)
      }
    }
  }

  const canSend = value.trim().length > 0 && !loading
  const ext = attachment ? getExt(attachment.name) : ''
  const meta = FILE_META[ext]

  return (
    <div className="border-t border-slate-100 bg-white shrink-0">
      <input
        ref={fileRef}
        type="file"
        accept={ACCEPTED}
        onChange={handleFileChange}
        className="hidden"
      />

      {/* ── Main input container — Claude-style rounded box ── */}
      <div className="mx-3 my-3 rounded-2xl border border-slate-200 bg-white shadow-sm overflow-hidden focus-within:border-slate-400 focus-within:shadow-md transition-all">

        {/* ── Attachment preview inside the box ── */}
        {attachment && (
          <div className="px-3 pt-3">
            {isImage(attachment.name) && imagePreview ? (
              /* Image thumbnail — like Claude */
              <div className="relative inline-block">
                <img
                  src={imagePreview}
                  alt={attachment.name}
                  className="max-h-32 max-w-48 rounded-xl object-cover border border-slate-200"
                />
                <button
                  onClick={handleRemove}
                  className="absolute -top-2 -right-2 w-5 h-5 rounded-full bg-slate-700 text-white text-xs flex items-center justify-center cursor-pointer border-2 border-white hover:bg-slate-900 transition-colors"
                  title="Remove"
                >
                  ×
                </button>
                <div className="mt-1 text-xs text-slate-400 truncate max-w-48">
                  {attachment.name} · {formatSize(attachment.size)}
                </div>
              </div>
            ) : (
              /* Document card — like ChatGPT */
              <div className="inline-flex items-center gap-3 rounded-xl border border-slate-200 px-3 py-2.5 max-w-xs relative"
                style={{ background: meta?.bg || '#F9FAFB' }}>
                <div className="text-2xl shrink-0">{meta?.icon || '📎'}</div>
                <div className="min-w-0">
                  <p className="text-xs font-semibold text-slate-800 truncate">{attachment.name}</p>
                  <p className="text-xs mt-0.5" style={{ color: meta?.color || '#6B7280' }}>
                    {meta?.label || 'File'} · {formatSize(attachment.size)}
                  </p>
                </div>
                <button
                  onClick={handleRemove}
                  className="absolute -top-2 -right-2 w-5 h-5 rounded-full bg-slate-700 text-white text-xs flex items-center justify-center cursor-pointer border-2 border-white hover:bg-slate-900 transition-colors shrink-0"
                  title="Remove"
                >
                  ×
                </button>
              </div>
            )}
          </div>
        )}

        {/* ── Textarea ── */}
        <textarea
          ref={textRef}
          rows={attachment ? 1 : 2}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={handleKey}
          onPaste={handlePaste}
          placeholder={
            attachment
              ? `Ask anything about ${attachment.name}...`
              : (placeholder || 'Ask anything about your documents...')
          }
          className="w-full resize-none px-4 pt-3 pb-1 text-sm bg-transparent outline-none font-[inherit] leading-relaxed placeholder:text-slate-400"
          style={{ color: NAVY, minHeight: attachment ? 44 : 60, maxHeight: 120 }}
        />

        {/* ── Bottom toolbar ── */}
        <div className="flex items-center justify-between px-3 pb-2.5 pt-1">
          <div className="flex items-center gap-1">
            {/* Attach button */}
            <button
              onClick={handleFileClick}
              disabled={loading}
              title="Attach file or image (PDF, DOCX, XLSX, PNG, JPG…)"
              className={[
                'w-8 h-8 rounded-lg flex items-center justify-center transition-all cursor-pointer border-none',
                attachment
                  ? 'bg-blue-50 text-blue-500'
                  : 'text-slate-400 hover:text-slate-600 hover:bg-slate-100',
                loading ? 'opacity-40 cursor-not-allowed' : '',
              ].join(' ')}
            >
              <svg width="16" height="16" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="1.8">
                <path d="M21.44 11.05l-9.19 9.19a6 6 0 01-8.49-8.49l9.19-9.19a4 4 0 015.66 5.66l-9.2 9.19a2 2 0 01-2.83-2.83l8.49-8.48"
                  strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </button>

            {/* Voice button */}
            <VoiceInputButton onTranscript={onChange} disabled={loading} />
          </div>

          {/* Send button */}
          <button
            onClick={handleSend}
            disabled={!canSend}
            className="w-8 h-8 rounded-lg flex items-center justify-center transition-all duration-150 disabled:cursor-not-allowed cursor-pointer border-none"
            style={{ background: canSend ? NAVY : '#E2E8F0' }}
            title="Send (Enter)"
          >
            <svg width="14" height="14" fill="none" viewBox="0 0 24 24">
              <path d="M22 2L11 13M22 2L15 22l-4-9-9-4 20-7z"
                stroke="white" strokeWidth="2.2"
                strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </button>
        </div>
      </div>

      {/* Error */}
      {error && (
        <p className="text-center text-xs text-red-500 pb-1">{error}</p>
      )}

      <p className="text-center text-xs text-slate-400 pb-2.5">
        Enter to send · Shift+Enter for new line · You can also paste images
      </p>
    </div>
  )
}
