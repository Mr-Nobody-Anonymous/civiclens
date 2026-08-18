/* AI Review Queue — moderators accept / correct / reject AI recommendations. */
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { BrainCircuit, Check, ExternalLink, ShieldAlert, X } from 'lucide-react'
import { api } from '../lib/api'
import { useApp } from '../lib/store'
import { SeverityBadge, Skeleton } from './ui'

interface ReviewItem {
  id: string; reason: string; detail?: string; created_at: string
  report: { id: string; public_code: string; title: string; category?: string; severity?: number
            integrity_score?: number; integrity_notes?: string } | null
  ai: { category?: string; issue_type?: string; severity?: number; confidence?: number } | null
}

const REASON_META: Record<string, { label: string; cls: string }> = {
  low_confidence: { label: 'Low confidence', cls: 'bg-orange-100 text-orange-700 dark:bg-orange-500/15 dark:text-orange-300' },
  high_severity: { label: 'High severity', cls: 'bg-red-100 text-red-700 dark:bg-red-500/15 dark:text-red-300' },
  ai_disagreement: { label: 'AI disagreement', cls: 'bg-violet-100 text-violet-700 dark:bg-violet-500/15 dark:text-violet-300' },
  integrity_flag: { label: 'Needs verification', cls: 'bg-amber-100 text-amber-800 dark:bg-amber-500/15 dark:text-amber-300' },
}

export default function ReviewQueue() {
  const { meta, toast } = useApp()
  const [data, setData] = useState<{ counts: Record<string, number>; items: ReviewItem[] } | null>(null)
  const [filter, setFilter] = useState('')
  const [busy, setBusy] = useState('')
  const [corr, setCorr] = useState<Record<string, { category: string; severity: number; reason: string }>>({})

  const load = () => api.get(`/api/reviews${filter ? `?reason=${filter}` : ''}`).then(setData).catch(() => setData({ counts: { total: 0 }, items: [] }))
  useEffect(() => { load() }, [filter]) // eslint-disable-line react-hooks/exhaustive-deps

  const act = async (id: string, action: string, extra: Record<string, unknown> = {}) => {
    setBusy(id)
    try {
      await api.post(`/api/reviews/${id}/decide`, { action, ...extra })
      toast('success', action === 'accepted' ? 'AI recommendation confirmed' : action === 'corrected' ? 'Correction applied' : 'Recommendation rejected')
      load()
    } catch (e) { toast('error', (e as Error).message) } finally { setBusy('') }
  }

  if (!data) return <div className="mt-6 space-y-3"><Skeleton className="h-20" /><Skeleton className="h-40" /></div>

  return (
    <div className="mt-6 space-y-4">
      {/* counts header */}
      <div className="grid gap-3 sm:grid-cols-4">
        <button onClick={() => setFilter('')} className={`card p-4 text-left transition ${!filter ? 'ring-2 ring-brand-500' : ''}`}>
          <p className="text-xs font-semibold uppercase tracking-wider text-ink-500 dark:text-ink-400">Pending total</p>
          <p className="mt-1 text-2xl font-extrabold">{data.counts.total ?? 0}</p>
        </button>
        {Object.entries(REASON_META).map(([k, m]) => (
          <button key={k} onClick={() => setFilter(filter === k ? '' : k)}
            className={`card p-4 text-left transition ${filter === k ? 'ring-2 ring-brand-500' : ''}`}>
            <span className={`chip ${m.cls}`}>{m.label}</span>
            <p className="mt-2 text-2xl font-extrabold">{data.counts[k] ?? 0}</p>
          </button>
        ))}
      </div>

      {data.items.length === 0 && (
        <div className="card p-10 text-center">
          <BrainCircuit className="mx-auto size-8 text-brand-400" />
          <p className="mt-2 font-bold">Review queue is clear</p>
          <p className="text-sm text-ink-500 dark:text-ink-400">New AI recommendations that need human eyes will appear here.</p>
        </div>
      )}

      {data.items.map(item => {
        const c = corr[item.id] ?? { category: item.ai?.category ?? '', severity: item.ai?.severity ?? 3, reason: '' }
        const setC = (patch: Partial<typeof c>) => setCorr(s => ({ ...s, [item.id]: { ...c, ...patch } }))
        const m = REASON_META[item.reason] ?? { label: item.reason, cls: 'bg-ink-100 text-ink-600' }
        return (
          <div key={item.id} className="card p-5">
            <div className="flex flex-wrap items-start justify-between gap-2">
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <span className={`chip ${m.cls}`}>{m.label}</span>
                  {item.report && <span className="font-mono text-xs text-ink-400">{item.report.public_code}</span>}
                </div>
                <p className="mt-1.5 font-bold">{item.report?.title}</p>
                <p className="mt-1 text-sm text-ink-500 dark:text-ink-400">{item.detail}</p>
                {item.report?.integrity_score != null && item.report.integrity_score < 0.6 && (
                  <p className="mt-2 flex items-start gap-1.5 rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-800 dark:bg-amber-400/10 dark:text-amber-300">
                    <ShieldAlert className="mt-0.5 size-3.5 shrink-0" />
                    Evidence integrity {Math.round(item.report.integrity_score * 100)}% — {item.report.integrity_notes}
                  </p>
                )}
              </div>
              {item.report && (
                <Link to={`/reports/${item.report.id}`} className="btn-secondary !py-1.5 !text-xs">
                  Open<ExternalLink className="size-3" />
                </Link>
              )}
            </div>

            {item.ai && (
              <div className="mt-3 flex flex-wrap items-center gap-x-5 gap-y-1.5 rounded-xl bg-ink-50 px-4 py-2.5 text-sm dark:bg-white/5">
                <span className="text-xs font-bold uppercase tracking-wider text-violet-600 dark:text-violet-300">AI says</span>
                <span>{item.ai.category} · {item.ai.issue_type}</span>
                <SeverityBadge sev={item.ai.severity} />
                <span className="font-semibold">{Math.round((item.ai.confidence ?? 0) * 100)}% confidence</span>
              </div>
            )}

            <div className="mt-3 grid gap-2.5 lg:grid-cols-[1fr_1fr_2fr]">
              <div>
                <label className="label !text-xs" htmlFor={`rc-${item.id}`}>Correct category</label>
                <select id={`rc-${item.id}`} className="input !py-2 !text-xs" value={c.category} onChange={e => setC({ category: e.target.value })}>
                  {(meta?.categories ?? []).map(x => <option key={x}>{x}</option>)}
                </select>
              </div>
              <div>
                <label className="label !text-xs" htmlFor={`rs-${item.id}`}>Correct severity</label>
                <select id={`rs-${item.id}`} className="input !py-2 !text-xs" value={c.severity} onChange={e => setC({ severity: +e.target.value })}>
                  {[1, 2, 3, 4, 5].map(s => <option key={s} value={s}>{s}</option>)}
                </select>
              </div>
              <div>
                <label className="label !text-xs" htmlFor={`rr-${item.id}`}>Reason (recorded)</label>
                <input id={`rr-${item.id}`} className="input !py-2 !text-xs" value={c.reason}
                  onChange={e => setC({ reason: e.target.value })} placeholder="e.g. Large pothole affecting traffic" />
              </div>
            </div>

            <div className="mt-3 flex flex-wrap gap-2">
              <button disabled={busy === item.id} onClick={() => act(item.id, 'accepted', { reason: c.reason })}
                className="btn-primary !py-2 !text-xs"><Check className="size-3.5" />Accept AI recommendation</button>
              <button disabled={busy === item.id} onClick={() => act(item.id, 'corrected', {
                corrected_category: c.category, corrected_severity: c.severity, reason: c.reason })}
                className="btn-secondary !py-2 !text-xs">Apply correction</button>
              <button disabled={busy === item.id} onClick={() => act(item.id, 'rejected', { reason: c.reason })}
                className="btn-secondary !py-2 !text-xs !text-et-red"><X className="size-3.5" />Reject</button>
            </div>
          </div>
        )
      })}
    </div>
  )
}
