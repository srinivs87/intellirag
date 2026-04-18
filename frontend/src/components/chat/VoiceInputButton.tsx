'use client'
import { useState } from 'react'

interface VoiceInputButtonProps {
  onTranscript: (text: string) => void
  disabled?: boolean
}

export function VoiceInputButton({ onTranscript, disabled }: VoiceInputButtonProps) {
  const [listening, setListening] = useState(false)

  function handleClick() {
    const SpeechRecognition =
      (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition
    if (!SpeechRecognition) {
      alert('Voice input is not supported in this browser. Please use Chrome.')
      return
    }

    const recognition = new SpeechRecognition()
    recognition.lang = 'en-US'
    recognition.interimResults = false
    recognition.maxAlternatives = 1

    recognition.onstart = () => setListening(true)
    recognition.onend = () => setListening(false)
    recognition.onerror = () => setListening(false)
    recognition.onresult = (e: any) => {
      const transcript = e.results[0][0].transcript
      onTranscript(transcript)
    }

    recognition.start()
  }

  return (
    <button
      onClick={handleClick}
      disabled={disabled || listening}
      title={listening ? 'Listening...' : 'Voice input'}
      className="w-9 h-9 rounded-full flex items-center justify-center shrink-0 transition-all duration-200 border-none cursor-pointer"
      style={{
        background: listening ? '#EF4444' : '#E6F1FB',
        opacity: disabled ? 0.5 : 1,
        cursor: disabled ? 'not-allowed' : 'pointer',
        animation: listening ? 'pulse 1s infinite' : 'none',
      }}
    >
      <svg width="14" height="14" fill="none" viewBox="0 0 24 24">
        <path d="M12 2a3 3 0 013 3v7a3 3 0 01-6 0V5a3 3 0 013-3z"
          fill={listening ? '#fff' : '#0096D5'} />
        <path d="M19 10v1a7 7 0 01-14 0v-1M12 19v3M9 22h6"
          stroke={listening ? '#fff' : '#0096D5'}
          strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    </button>
  )
}
