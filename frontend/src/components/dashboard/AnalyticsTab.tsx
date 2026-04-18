'use client'
import { Card } from '@/components/ui'
import { Button } from '@/components/ui/Button'
import { AuditTrail } from './AuditTrail'
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
          <p className="text-sm text-slate-500 mt-1">Query insights and user activity</p>
        </div>
        <Button onClick={onRefresh} size="sm">Refresh</Button>
      </div>

      {loading && <p className="text-center text-slate-400 py-8 text-sm">Loading...</p>}

      {!loading && analytics && (
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
      )}

      {/* Audit Trail */}
      <AuditTrail />
    </div>
  )
}
