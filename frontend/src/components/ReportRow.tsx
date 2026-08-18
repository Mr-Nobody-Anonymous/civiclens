/* Staff triage row: inline status/severity/category/org controls per report. */
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Check, ChevronDown, ChevronUp, ExternalLink, Flag } from 'lucide-react'
import { api } from '../lib/api'
import type { Report } from '../lib/types'
import { STATUS_META } from '../lib/types'
import { useApp } from '../lib/store'
import { DemoBadge, SeverityBadge, StatusBadge } from './ui'

export default function ReportRow({ r, onChanged, orgMode = false }: { r: Report; onChanged: () => void; orgMode?: boolean }) {
  const { user, meta, toast } = useApp()
  const [open, setOpen] = useState(false)
  const [orgs, setOrgs] = useState<{ id: string; name: string }[]>([])
  const [status, setStatus] = useState(r.status)
  const [severity, setSeverity] = useState(r.severity ?? 3)
  const [category, setCategory] = useState(r.category ?? '')
  const [orgId, setOrgId] = useState('')
  const [note, setNote] = useState('')

  const isAdmin = user && ['admin', 'moderator'].includes(user.role)

  useEffect(() => { if (open && isAdmin) api.get('/api/organizations').then(setOrgs).catch(() => {}) }, [open, isAdmin])

  const act = async (fn: () => Promise<unknown>, msg: string) => {
    try { await fn(); toast('success', msg); onChanged() }
    catch (e) { toast('error', (e as Error).message) }
  }

  return (
    <div className="card overflow-hidden">
      <button onClick={() => setOpen(o => !o)} className="flex w-full items-center gap-3 px-4 py-3.5 text-left hover:bg-ink-50 dark:hover:bg-white/5" aria-expanded={open}>
        <SeverityBadge sev={r.severity} />
        <div className="min-w-0 flex-1">
          <p className="truncate font-semibold">{r.title} {r.is_demo && <DemoBadge />} {r.is_flagged && <Flag className="ml-1 inline size-3.5 text-et-red" />}</p>
          <p className="truncate text-xs text-ink-500">{r.public_code} · {r.category ?? '—'} · {r.city ?? ''} · {new Date(r.created_at).toLocaleDateString()}{r.organization_name ? ` · ${r.organization_name}` : ''}</p>
        </div>
        <StatusBadge status={r.status} />
        {open ? <ChevronUp className="size-4 shrink-0 text-ink-500 dark:text-ink-400" /> : <ChevronDown className="size-4 shrink-0 text-ink-500 dark:text-ink-400" />}
      </button>

      {open && (
        <div className="border-t border-ink-100 p-4 dark:border-white/10 animate-fade-in">
          <div className="mb-3 flex flex-wrap items-center gap-2 text-xs text-ink-500">
            {r.ai && <span className="rounded-full bg-violet-100 px-2.5 py-1 font-medium text-violet-700 dark:bg-violet-500/15 dark:text-violet-300">
              AI: {r.ai.category} · sev {r.ai.severity} · {Math.round((r.ai.confidence ?? 0) * 100)}% {r.ai.corrected && '· corrected'}</span>}
            {r.reporter_name && <span className="rounded-full bg-ink-100 px-2.5 py-1 dark:bg-white/10">Reporter: {r.reporter_name}</span>}
            <Link to={`/reports/${r.id}`} className="inline-flex items-center gap-1 font-semibold text-brand-700 hover:underline dark:text-brand-300">Open<ExternalLink className="size-3" /></Link>
          </div>

          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <div>
              <label className="label !text-xs" htmlFor={`status-${r.id}`}>Status</label>
              <select id={`status-${r.id}`} className="input !py-2 !text-xs" value={status} onChange={e => setStatus(e.target.value)}>
                {Object.entries(STATUS_META).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
              </select>
            </div>
            {isAdmin && <>
              <div>
                <label className="label !text-xs" htmlFor={`sev-${r.id}`}>Severity (correct AI)</label>
                <select id={`sev-${r.id}`} className="input !py-2 !text-xs" value={severity} onChange={e => setSeverity(+e.target.value)}>
                  {[1, 2, 3, 4, 5].map(s => <option key={s} value={s}>{s}</option>)}
                </select>
              </div>
              <div>
                <label className="label !text-xs" htmlFor={`cat-${r.id}`}>Category (correct AI)</label>
                <select id={`cat-${r.id}`} className="input !py-2 !text-xs" value={category} onChange={e => setCategory(e.target.value)}>
                  <option value="">—</option>
                  {(meta?.categories ?? []).map(c => <option key={c}>{c}</option>)}
                </select>
              </div>
              <div>
                <label className="label !text-xs" htmlFor={`org-${r.id}`}>Route to organization</label>
                <select id={`org-${r.id}`} className="input !py-2 !text-xs" value={orgId} onChange={e => setOrgId(e.target.value)}>
                  <option value="">— keep current —</option>
                  {orgs.map(o => <option key={o.id} value={o.id}>{o.name}</option>)}
                </select>
              </div>
            </>}
          </div>
          <div className="mt-3">
            <label className="sr-only" htmlFor={`note-${r.id}`}>Internal note</label>
            <input id={`note-${r.id}`} className="input !py-2 !text-xs" placeholder="Internal note (visible to staff only)" value={note} onChange={e => setNote(e.target.value)} />
          </div>

          <div className="mt-3 flex flex-wrap gap-2">
            <button className="btn-primary !py-2 !text-xs" onClick={() => act(async () => {
              if (status !== r.status) await api.patch(`/api/reports/${r.id}/status`, { status, note: note || undefined })
              if (isAdmin && (severity !== r.severity || (category && category !== r.category)))
                await api.patch(`/api/reports/${r.id}/correction`, { severity, category: category || undefined, note: note || undefined })
              if (isAdmin && orgId) await api.patch(`/api/reports/${r.id}/assignment`, { organization_id: orgId, note: note || undefined })
              if (note) await api.post(`/api/reports/${r.id}/comments`, { body: note, internal: true })
            }, 'Report updated')}><Check className="size-3.5" />Apply changes</button>

            {orgMode && r.status !== 'in_progress' && r.status !== 'resolved' && (
              <button className="btn-secondary !py-2 !text-xs" onClick={() => act(() =>
                api.patch(`/api/reports/${r.id}/assignment`, { accept: true }), 'Assignment accepted')}>Accept assignment</button>
            )}
            <button className="btn-secondary !py-2 !text-xs" onClick={() => act(() =>
              api.patch(`/api/reports/${r.id}/status`, { status: 'in_progress', note: note || 'Work started' }), 'Marked in progress')}>Start work</button>
            <button className="btn-secondary !py-2 !text-xs !text-emerald-600" onClick={() => act(() =>
              api.patch(`/api/reports/${r.id}/status`, { status: 'resolved', note: note || 'Issue resolved' }), 'Marked resolved')}>Mark resolved</button>
            {isAdmin && (!r.ai || r.ai.success === false || (r as { processing_error?: string }).processing_error) && (
              <button className="btn-secondary !py-2 !text-xs" onClick={() => act(() =>
                api.post(`/api/reports/${r.id}/retry-analysis`), 'AI analysis requeued')}>Re-run AI analysis</button>
            )}
            {isAdmin && (r.is_flagged
              ? <button className="btn-secondary !py-2 !text-xs" onClick={() => act(() => api.patch(`/api/reports/${r.id}/unflag`), 'Unflagged')}>Unflag</button>
              : <button className="btn-secondary !py-2 !text-xs !text-et-red" onClick={() => act(() =>
                  api.post(`/api/reports/${r.id}/flag`, { reason: note || 'Flagged by staff' }), 'Flagged & hidden from public')}>Flag as fake/abuse</button>)}
          </div>
        </div>
      )}
    </div>
  )
}
