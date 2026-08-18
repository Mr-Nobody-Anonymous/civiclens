import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { Flame, Search } from 'lucide-react'
import { api } from '../lib/api'
import type { Report } from '../lib/types'
import { SEVERITY, STATUS_META } from '../lib/types'
import { useApp } from '../lib/store'
import { useI18n } from '../lib/i18n'
import ReportCard from '../components/ReportCard'
import { CardSkeleton, EmptyState } from '../components/ui'

export default function Reports() {
  const { meta, user } = useApp()
  const { t } = useI18n()
  const [params, setParams] = useSearchParams()
  const [data, setData] = useState<{ items: Report[]; total: number } | null>(null)
  const [loading, setLoading] = useState(true)

  const q = params.get('q') ?? ''
  const category = params.get('category') ?? ''
  const status = params.get('status') ?? ''
  const severity = params.get('severity') ?? ''
  const sort = params.get('sort') ?? 'recent'
  const mine = params.get('mine') === '1'
  const page = parseInt(params.get('page') ?? '1', 10)

  const set = (k: string, v: string) => {
    const p = new URLSearchParams(params)
    if (v) p.set(k, v); else p.delete(k)
    if (k !== 'page') p.delete('page')
    setParams(p, { replace: true })
  }

  useEffect(() => {
    setLoading(true)
    const usp = new URLSearchParams({ page: String(page), page_size: '12', sort })
    if (q) usp.set('q', q)
    if (category) usp.set('category', category)
    if (status) usp.set('status', status)
    if (severity) usp.set('severity', severity)
    if (mine) usp.set('mine', 'true')
    api.get(`/api/reports?${usp}`).then(setData).catch(() => setData({ items: [], total: 0 })).finally(() => setLoading(false))
  }, [q, category, status, severity, sort, mine, page])

  const pages = data ? Math.max(1, Math.ceil(data.total / 12)) : 1

  return (
    <div className="mx-auto max-w-7xl px-4 py-8">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-extrabold md:text-3xl">{t('explore')}</h1>
          <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">{data ? `${data.total} report(s)` : '…'}</p>
        </div>
        <div className="flex gap-2">
          <button onClick={() => set('sort', sort === 'severity' ? 'recent' : 'severity')}
            className={`btn-secondary ${sort === 'severity' ? '!border-orange-400 !text-orange-600 dark:!text-orange-300' : ''}`}>
            <Flame className="size-4" />High severity first
          </button>
          {user && <button onClick={() => set('mine', mine ? '' : '1')} className={`btn-secondary ${mine ? '!border-brand-500 !text-brand-700 dark:!text-brand-300' : ''}`}>My reports</button>}
        </div>
      </div>

      {/* filters */}
      <div className="card mt-5 grid gap-3 p-4 sm:grid-cols-2 lg:grid-cols-4">
        <div className="relative">
          <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-gray-400" />
          <input aria-label="Search" className="input !pl-9" placeholder={t('search')} defaultValue={q}
            onKeyDown={e => { if (e.key === 'Enter') set('q', (e.target as HTMLInputElement).value) }}
            onBlur={e => set('q', e.target.value)} />
        </div>
        <select aria-label="Category filter" className="input" value={category} onChange={e => set('category', e.target.value)}>
          <option value="">{t('all_categories')}</option>
          {(meta?.categories ?? []).map(c => <option key={c}>{c}</option>)}
        </select>
        <select aria-label="Status filter" className="input" value={status} onChange={e => set('status', e.target.value)}>
          <option value="">{t('all_statuses')}</option>
          {Object.entries(STATUS_META).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
        </select>
        <select aria-label="Severity filter" className="input" value={severity} onChange={e => set('severity', e.target.value)}>
          <option value="">{t('all_severities')}</option>
          {Object.entries(SEVERITY).map(([k, v]) => <option key={k} value={k}>{k} — {v.label}</option>)}
        </select>
      </div>

      <div className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {loading && Array.from({ length: 6 }).map((_, i) => <CardSkeleton key={i} />)}
        {!loading && data?.items.map(r => <ReportCard key={r.id} r={r} />)}
      </div>
      {!loading && data?.items.length === 0 && (
        <div className="mt-6"><EmptyState title={t('no_results')} sub="Try removing some filters, or be the first to report an issue in your area."
          action={<Link to="/report" className="btn-primary mt-2">{t('report_issue')}</Link>} /></div>
      )}

      {pages > 1 && (
        <nav className="mt-8 flex items-center justify-center gap-2" aria-label="Pagination">
          <button className="btn-secondary" disabled={page <= 1} onClick={() => set('page', String(page - 1))}>←</button>
          <span className="px-3 text-sm font-medium">Page {page} / {pages}</span>
          <button className="btn-secondary" disabled={page >= pages} onClick={() => set('page', String(page + 1))}>→</button>
        </nav>
      )}
    </div>
  )
}
