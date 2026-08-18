import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { AlertOctagon, Building2, Calendar, ChevronLeft, Clock, Flag, MapPin, MessageSquare, Sparkles } from 'lucide-react'
import { api } from '../lib/api'
import type { Report } from '../lib/types'
import { CATEGORY_ICONS } from '../lib/types'
import { useApp } from '../lib/store'
import { useI18n } from '../lib/i18n'
import IssueMap from '../components/IssueMap'
import { ConfirmDialog, DemoBadge, SeverityBadge, Skeleton, StatusBadge } from '../components/ui'

export default function ReportDetail() {
  const { id } = useParams()
  const { user, toast } = useApp()
  const { t } = useI18n()
  const [r, setR] = useState<Report | null>(null)
  const [err, setErr] = useState('')
  const [flagOpen, setFlagOpen] = useState(false)
  const [comment, setComment] = useState('')

  const load = () => api.get(`/api/reports/${id}`).then(setR).catch(e => setErr(e.message))
  useEffect(() => { load() }, [id]) // eslint-disable-line react-hooks/exhaustive-deps

  if (err) return (
    <div className="mx-auto max-w-3xl px-4 py-16 text-center">
      <AlertOctagon className="mx-auto size-12 text-gray-300" />
      <h1 className="mt-4 text-xl font-bold">Report not found</h1>
      <p className="mt-1 text-sm text-gray-500">{err}</p>
      <Link to="/reports" className="btn-primary mt-6">{t('explore')}</Link>
    </div>
  )
  if (!r) return (
    <div className="mx-auto max-w-5xl space-y-4 px-4 py-8">
      <Skeleton className="h-8 w-2/3" /><Skeleton className="h-64 w-full" /><Skeleton className="h-40 w-full" />
    </div>
  )

  const video = r.media.find(m => m.kind === 'video')
  const images = r.media.filter(m => m.kind === 'image')
  const resolutions = r.media.filter(m => m.kind === 'resolution')
  const conf = Math.round((r.ai?.confidence ?? 0) * 100)

  const submitComment = async () => {
    try {
      await api.post(`/api/reports/${r.id}/comments`, { body: comment })
      setComment(''); toast('success', 'Comment added'); load()
    } catch (e) { toast('error', (e as Error).message) }
  }

  return (
    <div className="mx-auto max-w-5xl px-4 py-8">
      <Link to="/reports" className="inline-flex items-center gap-1 text-sm font-semibold text-brand-700 hover:underline dark:text-brand-300"><ChevronLeft className="size-4" />{t('reports')}</Link>

      <div className="mt-3 flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-sm font-semibold text-gray-500">{CATEGORY_ICONS[r.category ?? 'Other']} {r.category ?? 'Uncategorised'}</span>
            {r.is_demo && <DemoBadge />}
            <span className="font-mono text-xs text-gray-400">{r.public_code}</span>
          </div>
          <h1 className="mt-1.5 text-2xl font-extrabold md:text-3xl">{r.title}</h1>
          <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1.5 text-sm text-gray-500 dark:text-gray-400">
            {(r.address || r.city) && <span className="inline-flex items-center gap-1"><MapPin className="size-4" />{r.address ?? r.city}</span>}
            <span className="inline-flex items-center gap-1"><Calendar className="size-4" />{new Date(r.created_at).toLocaleString()}</span>
            {r.organization_name && <span className="inline-flex items-center gap-1"><Building2 className="size-4" />{r.organization_name}</span>}
          </div>
        </div>
        <div className="flex items-center gap-2">
          <SeverityBadge sev={r.severity} size="lg" /><StatusBadge status={r.status} size="lg" />
        </div>
      </div>

      <div className="mt-6 grid gap-5 lg:grid-cols-3">
        <div className="space-y-5 lg:col-span-2">
          {/* evidence */}
          {(video || images.length > 0) && (
            <div className="card overflow-hidden">
              {video && (
                <video controls preload="metadata" className="max-h-[420px] w-full bg-black"
                  poster={video.has_thumb ? `/api/reports/${r.id}/media/${video.id}/thumb` : undefined}
                  src={`/api/reports/${r.id}/media/${video.id}/file`} />
              )}
              {images.length > 0 && (
                <div className="grid grid-cols-2 gap-2 p-3 sm:grid-cols-3">
                  {images.map(m => (
                    <a key={m.id} href={`/api/reports/${r.id}/media/${m.id}/file`} target="_blank" rel="noreferrer">
                      <img src={m.has_thumb ? `/api/reports/${r.id}/media/${m.id}/thumb` : `/api/reports/${r.id}/media/${m.id}/file`}
                        alt="Report evidence" className="h-32 w-full rounded-lg object-cover transition hover:opacity-90" loading="lazy" />
                    </a>
                  ))}
                </div>
              )}
            </div>
          )}

          <div className="card p-6">
            <h2 className="font-bold">Description</h2>
            <p className="mt-2 whitespace-pre-wrap text-sm leading-relaxed text-gray-700 dark:text-gray-300">{r.description}</p>
            {r.duplicate_of_code && <p className="mt-3 rounded-lg bg-gray-100 px-3 py-2 text-xs dark:bg-white/10">Marked as duplicate of <strong>{r.duplicate_of_code}</strong></p>}
          </div>

          {resolutions.length > 0 && (
            <div className="card border-emerald-300/50 p-6 dark:border-emerald-500/30">
              <h2 className="font-bold text-emerald-700 dark:text-emerald-300">Resolution evidence</h2>
              <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-3">
                {resolutions.map(m => m.content_type?.startsWith('video')
                  ? <video key={m.id} controls className="h-32 w-full rounded-lg bg-black object-cover" src={`/api/reports/${r.id}/media/${m.id}/file`} />
                  : <img key={m.id} alt="Resolution evidence" className="h-32 w-full rounded-lg object-cover" src={`/api/reports/${r.id}/media/${m.id}/file`} />)}
              </div>
            </div>
          )}

          {/* comments */}
          <div className="card p-6">
            <h2 className="flex items-center gap-2 font-bold"><MessageSquare className="size-4.5" />Comments</h2>
            <div className="mt-3 space-y-3">
              {(r as unknown as { comments: { id: string; body: string; author: string; internal: boolean; created_at: string }[] }).comments?.map(c => (
                <div key={c.id} className={`rounded-xl px-4 py-3 text-sm ${c.internal ? 'border border-dashed border-amber-300 bg-amber-50/60 dark:border-amber-500/40 dark:bg-amber-400/5' : 'bg-gray-50 dark:bg-white/5'}`}>
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-semibold">{c.author}{c.internal && <span className="ml-2 text-[10px] font-bold uppercase text-amber-600">internal note</span>}</span>
                    <span className="text-xs text-gray-400">{new Date(c.created_at).toLocaleString()}</span>
                  </div>
                  <p className="mt-1 text-gray-700 dark:text-gray-300">{c.body}</p>
                </div>
              ))}
              {!(r as unknown as { comments?: unknown[] }).comments?.length && <p className="text-sm text-gray-400">No comments yet.</p>}
            </div>
            {user && (
              <div className="mt-4 flex gap-2">
                <input className="input" placeholder="Add a comment…" value={comment} onChange={e => setComment(e.target.value)}
                  onKeyDown={e => e.key === 'Enter' && comment.trim() && submitComment()} />
                <button className="btn-primary" disabled={!comment.trim()} onClick={submitComment}>Post</button>
              </div>
            )}
          </div>
        </div>

        <div className="space-y-5">
          {/* AI card */}
          <div className="card overflow-hidden">
            <div className="bg-gradient-to-r from-violet-600 to-brand-600 px-5 py-3 text-white">
              <p className="flex items-center gap-2 text-xs font-bold uppercase tracking-widest"><Sparkles className="size-4" />{t('ai_classification')}</p>
            </div>
            <div className="p-5">
              {r.ai && !r.ai.success ? (
                <div className="py-1">
                  <p className="text-sm font-medium text-amber-700 dark:text-amber-300">{t('ai_failed')}</p>
                  <p className="mt-2 text-xs text-gray-400">{r.ai.reasoning}</p>
                </div>
              ) : r.ai ? (
                <>
                  <dl className="space-y-2.5 text-sm">
                    <div className="flex justify-between"><dt className="text-gray-500">Category</dt><dd className="font-semibold">{r.ai.category}</dd></div>
                    <div className="flex justify-between"><dt className="text-gray-500">Issue</dt><dd className="font-semibold">{r.ai.issue_type}</dd></div>
                    <div className="flex justify-between"><dt className="text-gray-500">{t('severity')}</dt><dd><SeverityBadge sev={r.ai.severity} /></dd></div>
                    <div className="flex justify-between"><dt className="text-gray-500">Urgency</dt><dd className="font-semibold capitalize">{r.ai.urgency}</dd></div>
                    <div>
                      <div className="flex justify-between"><dt className="text-gray-500">{t('confidence')}</dt><dd className="font-bold">{conf}%</dd></div>
                      <div className="mt-1.5 h-2 overflow-hidden rounded-full bg-gray-200 dark:bg-white/10" role="progressbar" aria-valuenow={conf} aria-valuemin={0} aria-valuemax={100} aria-label="AI confidence">
                        <div className={`h-full rounded-full transition-all ${conf >= 75 ? 'bg-emerald-500' : conf >= 50 ? 'bg-yellow-500' : 'bg-orange-500'}`} style={{ width: `${conf}%` }} />
                      </div>
                      {(r.ai as { confidence_band?: string }).confidence_band && (
                        <p className={`mt-1 text-[11px] font-medium ${conf >= 75 ? 'text-emerald-600 dark:text-emerald-400' : conf >= 50 ? 'text-yellow-600 dark:text-yellow-400' : 'text-orange-600 dark:text-orange-400'}`}>
                          {t(`conf_${(r.ai as { confidence_band?: string }).confidence_band}`)}
                        </p>
                      )}
                    </div>
                    {r.ai.responsible_organization && <div className="flex justify-between gap-2"><dt className="text-gray-500">Recommended org</dt><dd className="text-right font-semibold">{r.ai.responsible_organization}</dd></div>}
                  </dl>
                  {r.ai.reasoning && <p className="mt-3 rounded-lg bg-gray-50 px-3 py-2 text-xs leading-relaxed text-gray-600 dark:bg-white/5 dark:text-gray-300">{r.ai.reasoning}</p>}
                  <p className="mt-3 text-[11px] leading-snug text-amber-600 dark:text-amber-300">{t('ai_disclaimer')}{r.ai.corrected && ' · A human reviewer has adjusted this classification.'}</p>
                  <p className="mt-2 text-[10px] text-gray-400">Model: {r.ai.model_name} v{r.ai.model_version} · {r.ai.created_at ? new Date(r.ai.created_at).toLocaleString() : ''}</p>
                </>
              ) : (
                <div className="flex items-center gap-3 py-2">
                  <Sparkles className="size-6 animate-pulse-soft text-violet-500" />
                  <p className="text-sm text-gray-500">AI analysis pending…</p>
                </div>
              )}
            </div>
          </div>

          {/* location */}
          {r.latitude != null && r.longitude != null && (
            <div className="card overflow-hidden">
              <IssueMap points={[{ id: r.id, lat: r.latitude, lng: r.longitude, severity: r.severity, title: r.title }]}
                center={[r.latitude, r.longitude]} zoom={15} cluster={false} className="h-52" />
            </div>
          )}

          {/* timeline */}
          <div className="card p-5">
            <h2 className="flex items-center gap-2 font-bold"><Clock className="size-4.5" />Timeline</h2>
            <ol className="mt-4 space-y-0">
              {r.history?.map((h, i) => (
                <li key={i} className="relative pb-5 pl-6 last:pb-0">
                  {i < (r.history!.length - 1) && <span className="absolute left-[7px] top-4 h-full w-px bg-gray-200 dark:bg-white/10" />}
                  <span className="absolute left-0 top-1 size-3.5 rounded-full border-2 border-white bg-brand-500 shadow dark:border-gray-900" />
                  <StatusBadge status={h.to_status} />
                  {h.note && <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">{h.note}</p>}
                  <p className="mt-0.5 text-[11px] text-gray-400">{new Date(h.created_at).toLocaleString()}</p>
                </li>
              ))}
            </ol>
          </div>

          {/* Reopen / dispute (reporter or staff, on resolved/rejected) */}
          {user && ['resolved', 'rejected'].includes(r.status) && (
            <button onClick={async () => {
              const reason = window.prompt(t('reopen_confirm')) ?? ''
              if (reason === null) return
              try {
                await api.post(`/api/reports/${r.id}/reopen?reason=${encodeURIComponent(reason)}`)
                toast('success', t('reopen')); load()
              } catch (e) { toast('error', (e as Error).message) }
            }} className="btn-secondary w-full !text-amber-600 dark:!text-amber-300">{t('reopen')}</button>
          )}
          <button onClick={() => setFlagOpen(true)} className="btn-secondary w-full !text-gray-500"><Flag className="size-4" />Report as inappropriate / spam</button>
        </div>
      </div>

      <ConfirmDialog open={flagOpen} onClose={() => setFlagOpen(false)} danger
        title="Flag this report?" body="Flagged reports are hidden from the public and reviewed by moderators. Only flag content that is fake, offensive, or abusive."
        confirmLabel="Flag report"
        onConfirm={async () => {
          try { await api.post(`/api/reports/${r.id}/flag`, { reason: 'Flagged from report page' }); toast('success', 'Thanks — a moderator will review this report.') }
          catch (e) { toast('error', (e as Error).message) }
        }} />
    </div>
  )
}
