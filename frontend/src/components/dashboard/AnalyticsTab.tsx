'use client'
import { Card } from '@/components/ui'
import { Button } from '@/components/ui/Button'
import { NAVY } from '@/lib/constants'

interface AnalyticsTabProps {
  analytics: any
  loading: boolean
  onRefresh: () => void
}

export function AnalyticsTab({ analytics, loading, onRefresh }: AnalyticsTabProps) {
  return (
    <div className="flex flex-col gap-5">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold" style={{ color: NAVY }}>Analytics Dashboard</h1>
          <p className="text-sm text-slate-500 mt-1">Query insights and user feedback</p>
        </div>
        <Button onClick={onRefresh} size="sm">Refresh</Button>
      </div>

      {loading && <p className="text-center text-slate-400 py-16 text-sm">Loading...</p>}
      {!loading && !analytics && (
        <p className="text-center text-slate-400 py-16 text-sm">No data yet — ask questions in Try It first.</p>
      )}

      {!loading && analytics && (
        <>
          <div className="grid grid-cols-4 gap-3">
            {[
              ['Total queries', analytics.totals?.all_time],
              ['Today', analytics.totals?.today],
              ['This week', analytics.totals?.this_week],
              ['Avg confidence', Math.round((analytics.averages?.confidence || 0) * 100) + '%',
                (analytics.averages?.confidence || 0) > 0.6 ? '#10B981' : '#F59E0B'],
            ].map(([label, value, color]) => (
              <Card key={label as string} className="p-4">
                <div className="text-xs text-slate-400 mb-1">{label}</div>
                <div className="text-xl font-semibold" style={{ color: (color as string) || NAVY }}>{value ?? 0}</div>
              </Card>
            ))}
          </div>

          {analytics.recent_queries?.length > 0 && (
            <Card className="p-5">
              <h3 className="text-sm font-semibold mb-3" style={{ color: NAVY }}>Recent Queries</h3>
              {analytics.recent_queries.map((q: any) => (
                <div key={q.id} className="flex items-center gap-3 py-2 border-b border-slate-100 last:border-0">
                  <div className={`w-2 h-2 rounded-full shrink-0 ${q.confidence > 0.6 ? 'bg-emerald-500' : q.confidence > 0.4 ? 'bg-amber-500' : 'bg-red-500'}`} />
                  <span className="text-sm text-slate-600 flex-1">
                    {q.question.length > 70 ? q.question.slice(0, 70) + '...' : q.question}
                  </span>
                  <span className="text-xs text-slate-400">{Math.round(q.confidence * 100)}%</span>
                </div>
              ))}
            </Card>
          )}
        </>
      )}
    </div>
  )
}
