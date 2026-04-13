'use client'
import { downloadSvgAsPng } from '@/lib/utils/chartDetection'

const COLORS = ['#060B4E', '#FA9600', '#0096D5', '#10B981', '#8B5CF6', '#EF4444', '#F59E0B', '#06B6D4']

interface PieChartProps {
  labels: string[]
  values: number[]
  msgId: string
}

export function PieChart({ labels, values, msgId }: PieChartProps) {
  const total = values.reduce((a, b) => a + b, 0)
  const W = 500, H = 260, cx = 160, cy = 125, r = 100
  const chartId = `pie-${msgId}`

  let angle = -Math.PI / 2
  const slices = values.map((v, i) => {
    const pct = v / total
    const a0 = angle
    const a1 = angle + pct * 2 * Math.PI
    angle = a1
    const x0 = cx + r * Math.cos(a0), y0 = cy + r * Math.sin(a0)
    const x1 = cx + r * Math.cos(a1), y1 = cy + r * Math.sin(a1)
    const large = pct > 0.5 ? 1 : 0
    const mx = cx + r * 0.65 * Math.cos((a0 + a1) / 2)
    const my = cy + r * 0.65 * Math.sin((a0 + a1) / 2)
    return { path: `M${cx},${cy} L${x0},${y0} A${r},${r} 0 ${large},1 ${x1},${y1} Z`, pct, mx, my, value: v, label: labels[i] }
  })

  return (
    <div className="mt-3 bg-slate-50 rounded-xl p-3 border border-slate-200">
      <div className="flex justify-between items-center mb-2">
        <span className="text-xs font-bold text-slate-500 tracking-wider">PIE CHART</span>
        <button
          onClick={() => downloadSvgAsPng(chartId, 'intellirag-pie.png')}
          className="text-xs px-2.5 py-1 bg-[#060B4E] text-white rounded-md font-semibold hover:bg-[#0a1065]"
        >
          ⬇ PNG
        </button>
      </div>
      <svg id={chartId} width={W} height={H} style={{ maxWidth: '100%', display: 'block' }}>
        <rect width={W} height={H} fill="#F8FAFC" rx="8" />
        {slices.map((s, i) => (
          <g key={i}>
            <path d={s.path} fill={COLORS[i % COLORS.length]} opacity="0.9" stroke="#fff" strokeWidth="1.5" />
            {s.pct > 0.06 && (
              <text x={s.mx} y={s.my} fontSize="9" fill="#fff" textAnchor="middle" fontWeight="700">
                {Math.round(s.pct * 100)}%
              </text>
            )}
          </g>
        ))}
        {slices.map((s, i) => (
          <g key={i} transform={`translate(${W - 180}, ${20 + i * 22})`}>
            <rect width="12" height="12" fill={COLORS[i % COLORS.length]} rx="2" />
            <text x="18" y="10" fontSize="10" fill="#334155">
              {s.label.length > 16 ? s.label.slice(0, 16) + '…' : s.label} ({s.value})
            </text>
          </g>
        ))}
      </svg>
    </div>
  )
}
