'use client'
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

export function ChatMessage({ message: msg, userInitial }: ChatMessageProps) {
  const isUser = msg.role === 'user'

  // Filter out chart type prefix from displayed text
  const displayText = msg.text
    .split('\n')
    .filter((line) => !line.match(/^(BAR_CHART|PIE_CHART|LINE_CHART):/))
    .join('\n')

  const chartData = msg.role === 'assistant' ? detectChartData(msg.text) : null

  return (
    <div
      className="flex gap-2 items-end"
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
        <div
          className="px-3 py-2.5 rounded-xl text-sm leading-relaxed"
          style={{
            background: isUser ? NAVY : '#F5F7FA',
            color: isUser ? '#fff' : NAVY,
            borderBottomRightRadius: isUser ? 3 : 13,
            borderBottomLeftRadius: isUser ? 13 : 3,
            wordBreak: 'break-word',
          }}
        >
          {displayText.split('\n').map((line, i, arr) => (
            <span key={i}>{line}{i < arr.length - 1 && <br />}</span>
          ))}
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
              const srcType = s.document_id?.includes('gdrive') ? 'gdrive'
                : s.document_id?.includes('teams') ? 'teams'
                : s.document_id?.includes('sharepoint') ? 'sharepoint'
                : s.document_id?.includes('onedrive') ? 'onedrive'
                : s.document_id?.includes('localfs') ? 'localfs' : 'uploaded'
              const cfg = SOURCE_CONFIG[srcType as keyof typeof SOURCE_CONFIG] || SOURCE_CONFIG.uploaded
              return (
                <div
                  key={i}
                  className="flex items-center gap-1.5 text-xs px-2 py-1 rounded-lg"
                  style={{ background: cfg.bg, border: `1px solid ${cfg.border}` }}
                >
                  <span className="font-medium flex-1 overflow-hidden text-ellipsis whitespace-nowrap" style={{ color: cfg.color }}>
                    {s.filename}
                  </span>
                  {s.web_url && (
                    <a href={s.web_url} target="_blank" rel="noopener noreferrer"
                      className="font-semibold shrink-0 px-1.5 py-0.5 rounded text-xs"
                      style={{ color: cfg.color, background: 'rgba(0,0,0,0.06)' }}>
                      Open ↗
                    </a>
                  )}
                </div>
              )
            })}
          </div>
        )}

        {/* Confidence */}
        {msg.confidence !== undefined && (
          <div className="flex items-center gap-2 text-xs text-slate-400">
            <div className="w-12 h-1 bg-slate-200 rounded-full overflow-hidden">
              <div
                className="h-full bg-emerald-500 rounded-full"
                style={{ width: `${Math.round(msg.confidence * 100)}%` }}
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
