'use client'
import { useRef, useState } from 'react'

interface AttachmentButtonProps {
  onAttach: (file: File) => void
  disabled?: boolean
  attachment: File | null
  onRemove: () => void
}

const ACCEPTED = '.pdf,.docx,.doc,.xlsx,.xls,.pptx,.ppt,.txt,.csv,.md,.png,.jpg,.jpeg,.webp'
const MAX_SIZE_MB = 10

const FILE_ICONS: Record<string, string> = {
  pdf:  '📄',
  docx: '📝', doc: '📝',
  xlsx: '📊', xls: '📊',
  pptx: '📑', ppt: '📑',
  txt:  '📃', csv: '📃', md: '📃',
  png:  '🖼️', jpg: '🖼️', jpeg: '🖼️', webp: '🖼️',
}

function getFileIcon(filename: string): string {
  const ext = filename.split('.').pop()?.toLowerCase() || ''
  return FILE_ICONS[ext] || '📎'
}

function isImage(filename: string): boolean {
  const ext = filename.split('.').pop()?.toLowerCase() || ''
  return ['png', 'jpg', 'jpeg', 'webp'].includes(ext)
}

export function AttachmentButton({ onAttach, disabled, attachment, onRemove }: AttachmentButtonProps) {
  const ref = useRef<HTMLInputElement>(null)
  const [error, setError] = useState<string | null>(null)
  const [preview, setPreview] = useState<string | null>(null)

  function handleClick() {
    setError(null)
    ref.current?.click()
  }

  function handleChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (!file) return

    // Size check
    if (file.size > MAX_SIZE_MB * 1024 * 1024) {
      setError(`File too large. Max ${MAX_SIZE_MB}MB.`)
      e.target.value = ''
      return
    }

    // Image preview
    if (isImage(file.name)) {
      const reader = new FileReader()
      reader.onload = (ev) => setPreview(ev.target?.result as string)
      reader.readAsDataURL(file)
    } else {
      setPreview(null)
    }

    setError(null)
    onAttach(file)
    e.target.value = ''
  }

  function handleRemove() {
    setPreview(null)
    setError(null)
    onRemove()
  }

  return (
    <div className="flex flex-col gap-1">
      <input
        ref={ref}
        type="file"
        accept={ACCEPTED}
        onChange={handleChange}
        className="hidden"
      />

      {/* Error message */}
      {error && (
        <p className="text-xs text-red-500 px-4">{error}</p>
      )}

      {/* Upload button */}
      <button
        onClick={handleClick}
        disabled={disabled}
        title="Attach file or image (PDF, DOCX, XLSX, PPTX, PNG, JPG)"
        className={[
          'w-9 h-9 rounded-full flex items-center justify-center transition-all duration-150',
          'border border-slate-200 bg-white cursor-pointer',
          disabled ? 'opacity-40 cursor-not-allowed' : 'hover:bg-slate-50 hover:border-slate-300',
          attachment ? 'border-blue-300 bg-blue-50' : '',
        ].join(' ')}
      >
        <svg width="16" height="16" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="1.8"
          className={attachment ? 'text-blue-500' : 'text-slate-500'}
        >
          <path d="M21.44 11.05l-9.19 9.19a6 6 0 01-8.49-8.49l9.19-9.19a4 4 0 015.66 5.66l-9.2 9.19a2 2 0 01-2.83-2.83l8.49-8.48"
            strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </button>
    </div>
  )
}
