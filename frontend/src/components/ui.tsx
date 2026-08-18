/* Shared UI primitives: badges, skeletons, empty states, dialogs, toasts. */
import { AlertTriangle, CheckCircle2, Info, Inbox, X } from 'lucide-react'
import type { ReactNode } from 'react'
import { SEVERITY, STATUS_META } from '../lib/types'
import { useApp } from '../lib/store'
import { useI18n } from '../lib/i18n'

export function SeverityBadge({ sev, size = 'sm' }: { sev?: number | null; size?: 'sm' | 'lg' }) {
  const { lang } = useI18n()
  if (!sev) return <span className="rounded-full bg-gray-100 px-2.5 py-0.5 text-xs font-medium text-gray-500 dark:bg-white/10 dark:text-gray-400">Pending</span>
  const m = SEVERITY[sev as 1]
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full font-semibold ${m.bg} ${size === 'lg' ? 'px-3 py-1 text-sm' : 'px-2.5 py-0.5 text-xs'}`}>
      <span className="size-1.5 rounded-full" style={{ background: m.color }} />
      {lang === 'am' ? m.label_am : m.label}
    </span>
  )
}

export function StatusBadge({ status, size = 'sm' }: { status: string; size?: 'sm' | 'lg' }) {
  const { lang } = useI18n()
  const m = STATUS_META[status] ?? STATUS_META.submitted
  return (
    <span className={`inline-flex items-center rounded-full font-medium ${m.cls} ${size === 'lg' ? 'px-3 py-1 text-sm' : 'px-2.5 py-0.5 text-xs'}`}>
      {lang === 'am' ? m.label_am : m.label}
    </span>
  )
}

export function DemoBadge() {
  const { t } = useI18n()
  return <span className="rounded-md border border-dashed border-amber-400/70 bg-amber-50 px-1.5 py-0.5 text-[10px] font-bold tracking-wider text-amber-600 dark:bg-amber-400/10 dark:text-amber-300">{t('demo_badge')}</span>
}

export function Skeleton({ className = '' }: { className?: string }) {
  return <div className={`skeleton ${className}`} />
}

export function CardSkeleton() {
  return (
    <div className="card p-5 space-y-3">
      <div className="flex justify-between"><Skeleton className="h-4 w-24" /><Skeleton className="h-5 w-16" /></div>
      <Skeleton className="h-5 w-3/4" /><Skeleton className="h-4 w-full" /><Skeleton className="h-4 w-1/2" />
    </div>
  )
}

export function EmptyState({ title, sub, action }: { title: string; sub?: string; action?: ReactNode }) {
  return (
    <div className="card flex flex-col items-center justify-center gap-3 px-6 py-16 text-center animate-fade-in">
      <div className="grid size-14 place-items-center rounded-2xl bg-gray-100 dark:bg-white/5">
        <Inbox className="size-7 text-gray-400" />
      </div>
      <p className="font-semibold">{title}</p>
      {sub && <p className="max-w-sm text-sm text-gray-500 dark:text-gray-400">{sub}</p>}
      {action}
    </div>
  )
}

export function Toasts() {
  const { toasts } = useApp()
  const icons = {
    success: <CheckCircle2 className="size-5 text-emerald-500" />,
    error: <AlertTriangle className="size-5 text-red-500" />,
    info: <Info className="size-5 text-sky-500" />,
  }
  return (
    <div className="pointer-events-none fixed inset-x-0 top-4 z-[1200] flex flex-col items-center gap-2 px-4">
      {toasts.map(t => (
        <div key={t.id} role="status" className="pointer-events-auto flex w-full max-w-md items-center gap-3 rounded-xl border border-gray-200 bg-white/95 px-4 py-3 text-sm font-medium shadow-xl backdrop-blur dark:border-white/10 dark:bg-gray-900/95 animate-fade-up">
          {icons[t.kind]}<span>{t.msg}</span>
        </div>
      ))}
    </div>
  )
}

export function ConfirmDialog({ open, title, body, confirmLabel = 'Confirm', danger, onConfirm, onClose }: {
  open: boolean; title: string; body: string; confirmLabel?: string; danger?: boolean
  onConfirm: () => void; onClose: () => void
}) {
  if (!open) return null
  return (
    <div className="fixed inset-0 z-[1100] grid place-items-center bg-black/50 p-4 animate-fade-in" onClick={onClose} role="dialog" aria-modal="true">
      <div className="card w-full max-w-sm p-6 animate-fade-up" onClick={e => e.stopPropagation()}>
        <div className="flex items-start justify-between gap-4">
          <h3 className="text-lg font-bold">{title}</h3>
          <button onClick={onClose} aria-label="Close" className="rounded-lg p-1 hover:bg-gray-100 dark:hover:bg-white/10"><X className="size-4" /></button>
        </div>
        <p className="mt-2 text-sm text-gray-600 dark:text-gray-300">{body}</p>
        <div className="mt-5 flex justify-end gap-2">
          <button className="btn-secondary" onClick={onClose}>Cancel</button>
          <button className={danger ? 'btn-danger' : 'btn-primary'} onClick={() => { onConfirm(); onClose() }}>{confirmLabel}</button>
        </div>
      </div>
    </div>
  )
}

export function StatCard({ label, value, icon, accent }: { label: string; value: ReactNode; icon?: ReactNode; accent?: string }) {
  return (
    <div className="card relative overflow-hidden p-5 transition-transform hover:-translate-y-0.5">
      <div className={`absolute inset-x-0 top-0 h-0.5 ${accent ?? 'eth-strip'}`} />
      <div className="flex items-center justify-between">
        <p className="text-xs font-medium uppercase tracking-wider text-gray-500 dark:text-gray-400">{label}</p>
        {icon}
      </div>
      <p className="mt-2 text-3xl font-extrabold tabular-nums">{value}</p>
    </div>
  )
}
