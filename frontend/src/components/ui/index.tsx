import { HTMLAttributes, InputHTMLAttributes, forwardRef } from 'react'
import { clsx } from 'clsx'

// ── Card ─────────────────────────────────────────────────────────────────────
export function Card({ className, children, ...props }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={clsx('bg-white rounded-xl border border-[#E2E8F2] overflow-hidden', className)}
      {...props}
    >
      {children}
    </div>
  )
}

// ── Badge ────────────────────────────────────────────────────────────────────
type BadgeVariant = 'success' | 'warning' | 'error' | 'info' | 'default'

interface BadgeProps extends HTMLAttributes<HTMLSpanElement> {
  variant?: BadgeVariant
}

export function Badge({ variant = 'default', className, children, ...props }: BadgeProps) {
  return (
    <span
      className={clsx(
        'inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold',
        {
          'bg-emerald-100 text-emerald-800': variant === 'success',
          'bg-amber-100 text-amber-800': variant === 'warning',
          'bg-red-100 text-red-700': variant === 'error',
          'bg-blue-100 text-blue-800': variant === 'info',
          'bg-slate-100 text-slate-700': variant === 'default',
        },
        className
      )}
      {...props}
    >
      {children}
    </span>
  )
}

// ── Input ────────────────────────────────────────────────────────────────────
export const Input = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(
  ({ className, ...props }, ref) => (
    <input
      ref={ref}
      className={clsx(
        'w-full border border-[#E2E8F2] rounded-lg px-3 py-2.5 text-sm text-[#060B4E]',
        'bg-[#F5F7FA] outline-none focus:ring-2 focus:ring-[#060B4E]/20 focus:border-[#060B4E]',
        'transition-all duration-150 placeholder:text-slate-400',
        className
      )}
      {...props}
    />
  )
)
Input.displayName = 'Input'

// ── StatusDot ────────────────────────────────────────────────────────────────
type StatusType = 'idle' | 'syncing' | 'error' | 'disconnected'

const STATUS_STYLES: Record<StatusType, string> = {
  idle:         'bg-emerald-500 text-emerald-800 bg-emerald-100 border-emerald-200',
  syncing:      'bg-amber-500 text-amber-800 bg-amber-100 border-amber-200',
  error:        'bg-red-500 text-red-700 bg-red-100 border-red-200',
  disconnected: 'bg-slate-300 text-slate-600 bg-slate-100 border-slate-200',
}

const STATUS_LABELS: Record<StatusType, string> = {
  idle: 'Connected', syncing: 'Syncing...', error: 'Error', disconnected: 'Not connected',
}

export function StatusDot({ status }: { status: StatusType }) {
  const [dot, ...rest] = STATUS_STYLES[status].split(' ')
  const badgeClasses = rest.join(' ')
  return (
    <span className={clsx('inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold border', badgeClasses)}>
      <span className={clsx('w-1.5 h-1.5 rounded-full', dot)} />
      {STATUS_LABELS[status]}
    </span>
  )
}

// ── ProgressBar ───────────────────────────────────────────────────────────────
interface ProgressBarProps {
  percent: number
  synced?: number
  skipped?: number
  total?: number
}

export function ProgressBar({ percent, synced = 0, skipped = 0, total = 0 }: ProgressBarProps) {
  return (
    <div className="mt-2 p-3 bg-emerald-50 rounded-lg border border-emerald-200">
      <div className="flex justify-between items-center text-xs text-emerald-700 mb-1.5">
        <span className="font-medium">
          {total > 0
            ? `${synced} new · ${skipped} unchanged of ${total} files`
            : 'Connecting...'}
        </span>
        <span className="font-bold text-sm">{percent > 0 ? `${percent}%` : ''}</span>
      </div>
      <div className="h-2 bg-emerald-100 rounded-full overflow-hidden">
        <div
          className="h-full bg-gradient-to-r from-emerald-700 to-emerald-500 rounded-full transition-all duration-700"
          style={{ width: `${Math.max(percent, total > 0 ? 2 : 5)}%` }}
        />
      </div>
      {total > 0 && (
        <div className="flex gap-3 mt-1.5 text-xs text-emerald-700">
          <span>✓ {synced} synced</span>
          <span>⟳ {skipped} unchanged</span>
        </div>
      )}
    </div>
  )
}
