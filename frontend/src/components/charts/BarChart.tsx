'use client'
import { downloadSvgAsPng } from '@/lib/utils/chartDetection'

const COLORS = ['#060B4E', '#FA9600', '#0096D5', '#10B981', '#8B5CF6', '#EF4444', '#F59E0B', '#06B6D4']

interface BarChartProps {
  labels: string[]
  values: number[]
  msgId: string
}

export function BarChart({ labels, values, msgId }: BarChartProps) {
  const W = 500, H = 220, padL = 45, padB = 55, padT = 20, padR = 15
  const cW = W - padL - padR
  const cH = H - padT - padB
  const max = Math.max(...values) || 1
  const barW = Math.min(44, cW / labels.length - 6)
  const chartId = `chart-${msgId}`

  return (
    <div className="mt-3 bg-slate-50 rounded-xl p-3 border border-slate-200">
      <div className="flex justify-between items-center mb-2">
        <span className="text-xs font-bold text-slate-500 tracking-wider">CHART</span>
        <button
          onClick={() => downloadSvgAsPng(chartId, 'intellirag-chart.png')}
          className="text-xs px-2.5 py-1 bg-[#060B4E] text-white rounded-md font-semibold hover:bg-[#0a1065]"
        >
          ⬇ PNG
        </button>
      </div>
      <svg id={chartId} width={W} height={H} style={{ maxWidth: '100%', display: 'block' }}>
        <rect width={W} height={H} fill="#F8FAFC" rx="8" />
        {[0, 0.25, 0.5, 0.75, 1].map((t) => (
          <g key={t}>
            <line x1={padL} y1={padT + cH * (1 - t)} x2={padL + cW} y2={padT + cH * (1 - t)}
              stroke="#E2E8F2" strokeWidth="1" strokeDasharray="3,3" />
            <text x={padL - 5} y={padT + cH * (1 - t) + 4} fontSize="8" fill="#94A3B8" textAnchor="end">
              {t > 0 ? (max * t).toFixed(1) : '0'}
            </text>
          </g>
        ))}
        {labels.map((label, i) => {
          const x = padL + (i + 0.5) * (cW / labels.length) - barW / 2
          const bH = (values[i] / max) * cH
          const y = padT + cH - bH
          const short = label.length > 12 ? label.slice(0, 12) + '…' : label
          return (
            <g key={i}>
              <rect x={x} y={y} width={barW} height={bH} fill={COLORS[i % COLORS.length]} rx="3" opacity="0.9" />
              <text x={x + barW / 2} y={y - 4} fontSize="8" fill="#334155" textAnchor="middle" fontWeight="700">
                {values[i]}
              </text>
              <text x={x + barW / 2} y={H - padB + 14} fontSize="8" fill="#64748B" textAnchor="middle"
                transform={`rotate(-25,${x + barW / 2},${H - padB + 14})`}>
                {short}
              </text>
            </g>
          )
        })}
        <line x1={padL} y1={padT} x2={padL} y2={padT + cH} stroke="#CBD5E1" strokeWidth="1.5" />
        <line x1={padL} y1={padT + cH} x2={padL + cW} y2={padT + cH} stroke="#CBD5E1" strokeWidth="1.5" />
      </svg>
    </div>
  )
}
