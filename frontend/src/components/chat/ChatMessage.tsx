'use client'
import { useState } from 'react'
import { ChatMessage as ChatMessageType } from '@/types/chat'
import { SOURCE_CONFIG } from '@/lib/constants'
import { BarChart } from '@/components/charts/BarChart'
import { PieChart } from '@/components/charts/PieChart'
import { detectChartData } from '@/lib/utils/chartDetection'

const NAVY = '#060B4E'
const ORANGE = '#FA9600'

interface ChatMessageProps {
  message: ChatMessageType
  userInitial: string
}

function renderMarkdown(text: string) {
  return text
    .split('\n')
    .map((line, i, arr) => {
      // Bold: **text**
      const parts = line.split(/(\*\*[^*]+\*\*)/g).map((part, j) => {
        if (part.startsWith('**') && part.endsWith('**')) {
          return <strong key={j}>{part.slice(2, -2)}</strong>
        }
        return part
      })
      // Bullet points
      if (line.trim().startsWith('* ') || line.trim().startsWith('- ')) {
        return (
          <div key={i} className="flex gap-2 my-0.5">
            <span className="shrink-0 mt-1 w-1.5 h-1.5 rounded-full bg-slate-400 inline-block" />
            <span>{parts.map((p, j) => typeof p === 'string' ? p.replace(/^[\*\-]\s/, '') : p)}</span>
          </div>
        )
      }
      return <span key={i}>{parts}{i < arr.length - 1 && <br />}</span>
    })
}

export function ChatMessage({ message: msg, userInitial }: ChatMessageProps) {
  const [copied, setCopied] = useState(false)
  const isUser = msg.role === 'user'

  const displayText = msg.text
    .split('\n')
    .filter((line) => !line.match(/^(BAR_CHART|PIE_CHART|LINE_CHART):/))
    .join('\n')

  const chartData = msg.role === 'assistant' ? detectChartData(msg.text) : null

  function handleCopy() {
    navigator.clipboard.writeText(displayText)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <div
      className="flex gap-2 items-end group"
      style={{
        flexDirection: isUser ? 'row-reverse' : 'row',
        alignSelf: isUser ? 'flex-end' : 'flex-start',
        maxWidth: '90%',
      }}
    >
      {/* Avatar */}
      <div
        className="w-7 h-7 rounded-full shrink-0 flex items-center justify-center text-xs font-bold text-white"
        style={{ background: isUser ? ORANGE : NAVY }}
      >
        {isUser ? userInitial : 'IR'}
      </div>

      <div className="flex flex-col gap-1.5">
        {/* Bubble */}
        <div className="relative">
          <div
            className="px-3.5 py-2.5 rounded-xl text-sm leading-relaxed"
            style={{
              background: isUser ? NAVY : '#F5F7FA',
              color: isUser ? '#fff' : NAVY,
              borderBottomRightRadius: isUser ? 3 : 13,
              borderBottomLeftRadius: isUser ? 13 : 3,
              wordBreak: 'break-word',
            }}
          >
            {isUser ? (
              displayText.split('\n').map((line, i, arr) => (
                <span key={i}>{line}{i < arr.length - 1 && <br />}</span>
              ))
            ) : (
              renderMarkdown(displayText)
            )}
          </div>

          {/* Copy button — appears on hover for assistant messages */}
          {!isUser && (
            <button
              onClick={handleCopy}
              className="absolute -top-2 -right-2 opacity-0 group-hover:opacity-100 transition-opacity w-7 h-7 rounded-full bg-white border border-slate-200 shadow-sm flex items-center justify-center cursor-pointer hover:bg-slate-50"
              title="Copy answer"
            >
              {copied ? (
                <svg width="12" height="12" fill="none" viewBox="0 0 24 24" stroke="#10B981" strokeWidth="2.5">
                  <path d="M5 13l4 4L19 7" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              ) : (
                <svg width="12" height="12" fill="none" viewBox="0 0 24 24" stroke="#64748B" strokeWidth="2">
                  <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
                  <path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1" strokeLinecap="round" />
                </svg>
              )}
            </button>
          )}
        </div>

        {/* Chart */}
        {chartData && (
          chartData.chartType === 'pie'
            ? <PieChart labels={chartData.labels} values={chartData.values} msgId={msg.id} />
            : <BarChart labels={chartData.labels} values={chartData.values} msgId={msg.id} />
        )}

        {/* Source chips */}
        {msg.sources && msg.sources.length > 0 && (
          <div className="flex flex-col gap-1 mt-1">
            {msg.sources.slice(0, 3).map((s, i) => {
              const srcType = s.source_type?.includes('gdrive') ? 'gdrive'
                : s.source_type?.includes('teams') ? 'teams'
                : s.source_type?.includes('sharepoint') ? 'sharepoint'
                : s.source_type?.includes('onedrive') ? 'onedrive'
                : s.source_type?.includes('attachment') ? 'uploaded'
                : 'localfs'
              const cfg = SOURCE_CONFIG[srcType as keyof typeof SOURCE_CONFIG] || SOURCE_CONFIG.uploaded
              return (
                <div
                  key={i}
                  className="flex items-center gap-1.5 text-xs px-2 py-1 rounded-lg"
                  style={{ background: cfg.bg, border: `1px solid ${cfg.border}` }}
                >
                  <span
                    className="font-medium flex-1 overflow-hidden text-ellipsis whitespace-nowrap"
                    style={{ color: cfg.color }}
                  >
                    {s.filename}
                  </span>
                  {s.web_url && (
                    <a
                      href={s.web_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="font-semibold shrink-0 px-1.5 py-0.5 rounded text-xs"
                      style={{ color: cfg.color, background: 'rgba(0,0,0,0.06)' }}
                    >
                      Open ↗
                    </a>
                  )}
                </div>
              )
            })}
          </div>
        )}

        {/* Confidence + timing */}
        {msg.confidence !== undefined && (
          <div className="flex items-center gap-2 text-xs text-slate-400">
            <div className="w-12 h-1 bg-slate-200 rounded-full overflow-hidden">
              <div
                className="h-full rounded-full transition-all"
                style={{
                  width: `${Math.round(msg.confidence * 100)}%`,
                  background: msg.confidence > 0.7 ? '#10B981' : msg.confidence > 0.4 ? '#F59E0B' : '#EF4444',
                }}
              />
            </div>
            <span>{Math.round(msg.confidence * 100)}% confidence</span>
            {msg.ms && <span>· {msg.ms}ms</span>}
          </div>
        )}
      </div>
    </div>
  )
}
