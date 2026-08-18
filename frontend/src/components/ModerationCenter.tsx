/* Unified Moderation Center — one queue for all human-attention signals. */
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { EyeOff, Flag, History, MessageSquareWarning, ShieldAlert, Undo2, Layers } from 'lucide-react'
import { api } from '../lib/api'
import { useApp } from '../lib/store'
import { SeverityBadge, Skeleton } from './ui'

interface QueueItem {
  kind: string; id: string; reason: string; detail?: string; created_at?: string
  severity?: number | null; report?: { id: string; public_code: string; title: string } | null
  report_id?: string; author?: string
}

const KIND_META: Record<string, { label: string; icon: typeof Flag; cls: string }> = {
  ai_review: { label: 'AI uncertain', icon: ShieldAlert, cls: 'bg-violet-100 text-violet-700 dark:bg-violet-500/15 dark:text-violet-300' },
  flagged_report: { label: 'Flagged report', icon: Flag, cls: 'bg-red-100 text-red-700 dark:bg-red-500/15 dark:text-red-300' },
  flagged_comment: { label: 'Reported comment', icon: MessageSquareWarning, cls: 'bg-amber-100 text-amber-800 dark:bg-amber-500/15 dark:text-amber-300' },
  dup_cluster: { label: 'High-volume cluster', icon: Layers, cls: 'bg-sky-100 text-sky-700 dark:bg-sky-500/15 dark:text-sky-300' },
}

export default function ModerationCenter() {
  const { toast } = useApp()
  const [data, setData] = useState<{ counts: Record<string, number>; items: QueueItem[] } | null>(null)
  const [filter, setFilter] = useState('')
  const [history, setHistory] = useState<{ id: string; action: string; detail?: string; created_at: string }[] | null>(null)
  const [showHistory, setShowHistory] = useState(false)

  const load = () => api.get(`/api/moderation/queue${filter ? `?kind=${filter}` : ''}`).then(setData).catch(() => setData({ counts: { total: 0 }, items: [] }))
  useEffect(() => { load() }, [filter]) // eslint-disable-line react-hooks/exhaustive-deps

  const act = async (fn: () => Promise<unknown>, msg: string) => {
    try { await fn(); toast('success', msg); load() } catch (e) { toast('error', (e as Error).message) }
  }

  if (!data) return <div className="mt-6 space-y-3"><Skeleton className="h-20" /><Skeleton className="h-40" /></div>

  return (
    <div className="mt-6 space-y-4">
      <div className="grid gap-3 sm:grid-cols-5">
        <button onClick={() => setFilter('')} className={`card p-4 text-left ${!filter ? 'ring-2 ring-brand-500' : ''}`}>
          <p className="text-xs font-semibold uppercase tracking-wider text-ink-500 dark:text-ink-400">All queues</p>
          <p className="mt-1 text-2xl font-extrabold">{data.counts.total ?? 0}</p>
        </button>
        {Object.entries(KIND_META).map(([k, m]) => (
          <button key={k} onClick={() => setFilter(filter === k ? '' : k)}
            className={`card p-4 text-left ${filter === k ? 'ring-2 ring-brand-500' : ''}`}>
            <span className={`chip ${m.cls}`}><m.icon className="size-3" />{m.label}</span>
            <p className="mt-2 text-2xl font-extrabold">{data.counts[k] ?? 0}</p>
          </button>
        ))}
      </div>

      <div className="flex justify-end">
        <button className="btn-secondary !py-1.5 !text-xs" onClick={() => {
          setShowHistory(h => !h)
          if (!history) api.get('/api/moderation/history').then(setHistory).catch(() => setHistory([]))
        }}><History className="size-3.5" />{showHistory ? 'Hide' : 'Show'} moderation history</button>
      </div>

      {showHistory && history && (
        <div className="card max-h-72 overflow-auto p-4">
          {history.length === 0 && <p className="text-sm text-ink-500">No moderation actions yet.</p>}
          {history.map(h => (
            <div key={h.id} className="flex items-start justify-between gap-3 border-b border-ink-100 py-2 text-xs last:border-0 dark:border-white/5">
              <span className="font-mono font-semibold">{h.action}</span>
              <span className="min-w-0 flex-1 truncate text-ink-500">{h.detail}</span>
              <span className="shrink-0 text-ink-400">{new Date(h.created_at).toLocaleString()}</span>
            </div>
          ))}
        </div>
      )}

      {data.items.length === 0 && (
        <div className="card p-10 text-center">
          <ShieldAlert className="mx-auto size-8 text-brand-400" />
          <p className="mt-2 font-bold">Moderation queue is clear</p>
        </div>
      )}

      {data.items.map(item => {
        const m = KIND_META[item.kind] ?? KIND_META.ai_review
        return (
          <div key={`${item.kind}-${item.id}`} className="card flex flex-wrap items-center gap-3 p-4">
            <span className={`chip ${m.cls}`}><m.icon className="size-3" />{m.label}</span>
            {item.severity != null && <SeverityBadge sev={item.severity} />}
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-semibold">
                {item.report?.title ?? item.detail?.slice(0, 90) ?? item.reason}
                {item.author && <span className="ml-2 text-xs font-normal text-ink-400">by {item.author}</span>}
              </p>
              {item.report && <p className="text-xs text-ink-400">{item.report.public_code} · {item.detail?.slice(0, 100)}</p>}
            </div>
            <div className="flex shrink-0 gap-1.5">
              {item.kind === 'ai_review' && (
                <span className="text-xs text-ink-400">→ decide in the <strong>AI Review</strong> tab</span>
              )}
              {(item.report || item.report_id) && item.kind !== 'dup_cluster' && (
                <Link to={`/reports/${item.report?.id ?? item.report_id}`} className="btn-secondary !py-1.5 !text-xs">Open</Link>
              )}
              {item.kind === 'flagged_report' && item.report && (
                <button className="btn-secondary !py-1.5 !text-xs" onClick={() => act(() =>
                  api.patch(`/api/reports/${item.report!.id}/unflag`), 'Report restored to public view')}>
                  <Undo2 className="size-3" />Restore</button>
              )}
              {item.kind === 'flagged_comment' && (
                <>
                  <button className="btn-secondary !py-1.5 !text-xs !text-et-red" onClick={() => act(() =>
                    api.post(`/api/moderation/comments/${item.id}/hide`, { hidden: true, reason: 'Moderator hid reported comment' }),
                    'Comment hidden (reversible)')}><EyeOff className="size-3" />Hide</button>
                  <button className="btn-secondary !py-1.5 !text-xs" onClick={() => act(() =>
                    api.post(`/api/moderation/comments/${item.id}/hide`, { hidden: false }),
                    'Comment kept & flag cleared')}>Keep</button>
                </>
              )}
            </div>
          </div>
        )
      })}
    </div>
  )
}
