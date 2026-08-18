/* Shared UI primitives: badges, skeletons, empty states, dialogs, toasts. */
import { AlertTriangle, CheckCircle2, Info, Inbox, X } from 'lucide-react'
import type { ReactNode } from 'react'
import { SEVERITY, STATUS_META } from '../lib/types'
import { useApp } from '../lib/store'
import { useI18n } from '../lib/i18n'

export function SeverityBadge({ sev, size = 'sm' }: { sev?: number | null; size?: 'sm' | 'lg' }) {
  const { lang } = useI18n()
  if (!sev) return <span className="chip bg-ink-100 text-ink-600 dark:bg-white/10 dark:text-ink-300">…</span>
  const m = SEVERITY[sev as 1]
  return (
    <span className={`chip ${m.bg} ${size === 'lg' ? '!px-3 !py-1 !text-sm' : ''}`}>
      <span className="size-1.5 rounded-full" style={{ background: m.color }} aria-hidden />
      {lang === 'am' ? m.label_am : m.label}
    </span>
  )
}

export function StatusBadge({ status, size = 'sm' }: { status: string; size?: 'sm' | 'lg' }) {
  const { lang } = useI18n()
  const m = STATUS_META[status] ?? STATUS_META.submitted
  return (
    <span className={`chip ${m.cls} ${size === 'lg' ? '!px-3 !py-1 !text-sm' : ''}`}>
      {lang === 'am' ? m.label_am : m.label}
    </span>
  )
}

export function DemoBadge() {
  const { t } = useI18n()
  return <span className="rounded-md border border-dashed border-gold-500/60 bg-gold-400/10 px-1.5 py-0.5 text-[10px] font-bold tracking-wider text-gold-600 dark:text-gold-400">{t('demo_badge')}</span>
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
      <div className="relative grid size-16 place-items-center rounded-2xl bg-brand-50 dark:bg-brand-400/10">
        <Inbox className="size-7 text-brand-400" />
        <span className="absolute -right-1 -top-1 size-3 rounded-full bg-gold-400" aria-hidden />
      </div>
      <p className="text-lg font-bold">{title}</p>
      {sub && <p className="max-w-sm text-sm text-ink-500 dark:text-ink-400">{sub}</p>}
      {action}
    </div>
  )
}

export function Toasts() {
  const { toasts } = useApp()
  const icons = {
    success: <CheckCircle2 className="size-5 shrink-0 text-brand-500" />,
    error: <AlertTriangle className="size-5 shrink-0 text-et-red" />,
    info: <Info className="size-5 shrink-0 text-sky-500" />,
  }
  return (
    <div className="pointer-events-none fixed inset-x-0 top-4 z-[1200] flex flex-col items-center gap-2 px-4">
      {toasts.map(t => (
        <div key={t.id} role="status" className="pointer-events-auto flex w-full max-w-md items-center gap-3 rounded-2xl border border-ink-200/80 bg-white/95 px-4 py-3 text-sm font-medium backdrop-blur dark:border-white/10 dark:bg-ink-900/95 animate-fade-up" style={{ boxShadow: 'var(--shadow-pop)' }}>
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
    <div className="fixed inset-0 z-[1100] grid place-items-center bg-brand-950/50 p-4 backdrop-blur-sm animate-fade-in" onClick={onClose} role="dialog" aria-modal="true" aria-label={title}>
      <div className="card w-full max-w-sm !rounded-3xl p-6 animate-pop" onClick={e => e.stopPropagation()} style={{ boxShadow: 'var(--shadow-pop)' }}>
        <div className="flex items-start justify-between gap-4">
          <h3 className="text-lg font-bold">{title}</h3>
          <button onClick={onClose} aria-label="Close" className="rounded-lg p-1 text-ink-400 hover:bg-ink-100 hover:text-ink-700 dark:hover:bg-white/10"><X className="size-4" /></button>
        </div>
        <p className="mt-2 text-sm leading-relaxed text-ink-600 dark:text-ink-300">{body}</p>
        <div className="mt-6 flex justify-end gap-2">
          <button className="btn-secondary" onClick={onClose}>Cancel</button>
          <button className={danger ? 'btn-danger' : 'btn-primary'} onClick={() => { onConfirm(); onClose() }}>{confirmLabel}</button>
        </div>
      </div>
    </div>
  )
}

export function StatCard({ label, value, icon, accent }: { label: string; value: ReactNode; icon?: ReactNode; accent?: string }) {
  return (
    <div className="card card-lift relative overflow-hidden p-5">
      <div className={`absolute inset-x-0 top-0 h-[3px] ${accent ?? 'bg-gradient-to-r from-brand-500 via-gold-400 to-brand-500'}`} aria-hidden />
      <div className="flex items-center justify-between">
        <p className="text-xs font-semibold uppercase tracking-wider text-ink-500 dark:text-ink-400">{label}</p>
        {icon}
      </div>
      <p className="mt-2 text-3xl font-extrabold tabular-nums">{value}</p>
    </div>
  )
}
