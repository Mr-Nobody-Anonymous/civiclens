import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Bar, BarChart, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { AlertTriangle, Building2, CheckCircle2, FileText, FolderOpen, Upload } from 'lucide-react'
import { api, uploadWithProgress } from '../lib/api'
import type { Report } from '../lib/types'
import { SEVERITY } from '../lib/types'
import { useApp } from '../lib/store'
import { StatCard, Skeleton } from '../components/ui'
import ReportRow from '../components/ReportRow'

interface OrgStats {
  organization: string; total: number; open: number; resolved: number
  by_status: Record<string, number>; by_severity: Record<string, number>
}

export default function OrgDashboard() {
  const { user, authLoaded, toast } = useApp()
  const [stats, setStats] = useState<OrgStats | null>(null)
  const [sla, setSla] = useState<{ open: number; overdue: number; critical_overdue: number; avg_ack_hours: number | null; sla_compliance: number | null } | null>(null)
  const [reports, setReports] = useState<Report[] | null>(null)
  const [filter, setFilter] = useState('')
  const [resFor, setResFor] = useState<Report | null>(null)
  const [pct, setPct] = useState(0)

  const load = () => {
    api.get('/api/dashboard/org-stats').then(s => {
      setStats(s)
      if (user?.organization_id) api.get(`/api/organizations/${user.organization_id}/sla-stats`).then(setSla).catch(() => {})
    }).catch(() => {})
    api.get(`/api/dashboard/org-reports${filter ? `?status=${filter}` : ''}`).then(setReports).catch(() => setReports([]))
  }
  useEffect(() => { if (user) load() }, [user, filter]) // eslint-disable-line react-hooks/exhaustive-deps

  if (authLoaded && (!user || !['org_staff', 'admin'].includes(user.role))) {
    return <div className="mx-auto max-w-md px-4 py-20 text-center">
      <AlertTriangle className="mx-auto size-10 text-amber-500" />
      <h1 className="mt-3 text-xl font-bold">Organization access required</h1>
      <p className="mt-1 text-sm text-ink-500">Sign in with an organization staff account (e.g. staff@ethiotelecom.et).</p>
      <Link to="/login" className="btn-primary mt-5">Sign in</Link>
    </div>
  }

  const sevData = stats ? Object.entries(stats.by_severity).map(([k, v]) => ({ name: `Sev ${k}`, count: v, color: SEVERITY[+k as 1]?.color })) : []

  const uploadResolution = async (file: File) => {
    if (!resFor) return
    try {
      await uploadWithProgress(`/api/reports/${resFor.id}/media`, file, { kind: 'resolution' }, setPct)
      toast('success', 'Resolution evidence uploaded')
      setResFor(null); setPct(0); load()
    } catch (e) { toast('error', (e as Error).message) }
  }

  return (
    <div className="mx-auto max-w-7xl px-4 py-8">
      <div className="flex items-center gap-3">
        <span className="grid size-12 place-items-center rounded-2xl bg-brand-600/10 text-brand-700 dark:text-brand-300"><Building2 className="size-6" /></span>
        <div>
          <h1 className="text-2xl font-extrabold">{stats?.organization ?? user?.organization_name ?? 'Organization Portal'}</h1>
          <p className="text-sm text-ink-500 dark:text-ink-400">Reports assigned to your organization only.</p>
        </div>
      </div>

      <div className="mt-6 grid gap-4 sm:grid-cols-3">
        <StatCard label="Assigned reports" value={stats?.total ?? '–'} icon={<FileText className="size-5 text-brand-600" />} />
        <StatCard label="Open" value={stats?.open ?? '–'} icon={<FolderOpen className="size-5 text-amber-500" />} />
        <StatCard label="Resolved" value={stats?.resolved ?? '–'} icon={<CheckCircle2 className="size-5 text-emerald-500" />} />
      </div>
      {sla && (
        <div className="mt-4 grid gap-4 sm:grid-cols-3">
          <StatCard label="SLA compliance" accent={sla.sla_compliance != null && sla.sla_compliance < 0.8 ? 'bg-et-red' : undefined}
            value={sla.sla_compliance != null ? `${Math.round(sla.sla_compliance * 100)}%` : '—'} />
          <StatCard label="Overdue (SLA breached)" accent={sla.overdue > 0 ? 'bg-orange-400' : undefined}
            value={<span className={sla.overdue > 0 ? 'text-orange-600 dark:text-orange-400' : ''}>{sla.overdue}{sla.critical_overdue > 0 && <span className="ml-2 text-sm font-bold text-et-red">({sla.critical_overdue} critical)</span>}</span>} />
          <StatCard label="Avg. response time" value={sla.avg_ack_hours != null ? `${sla.avg_ack_hours}h` : '—'} />
        </div>
      )}

      <div className="mt-5 grid gap-5 lg:grid-cols-3">
        <div className="card p-5">
          <h2 className="font-bold">Severity mix</h2>
          <div className="mt-3 h-44">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={sevData}>
                <XAxis dataKey="name" tick={{ fontSize: 10 }} /><YAxis allowDecimals={false} width={24} tick={{ fontSize: 10 }} />
                <Tooltip /><Bar dataKey="count" radius={[6, 6, 0, 0]}>{sevData.map((d, i) => <Cell key={i} fill={d.color} />)}</Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="lg:col-span-2">
          <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
            <h2 className="font-bold">Assigned reports</h2>
            <select aria-label="Status filter" className="input !w-auto !py-2 !text-xs" value={filter} onChange={e => setFilter(e.target.value)}>
              <option value="">All statuses</option>
              {['assigned', 'in_progress', 'under_review', 'resolved'].map(s => <option key={s} value={s}>{s.replace('_', ' ')}</option>)}
            </select>
          </div>
          <div className="space-y-3">
            {reports === null && <Skeleton className="h-40" />}
            {reports?.length === 0 && <p className="card p-8 text-center text-sm text-ink-500">No reports assigned to your organization yet.</p>}
            {reports?.map(r => (
              <div key={r.id}>
                <ReportRow r={r} onChanged={load} orgMode />
                <button onClick={() => setResFor(r)} className="mt-1 text-xs font-semibold text-brand-700 hover:underline dark:text-brand-300">
                  <Upload className="mr-1 inline size-3" />Upload resolution evidence
                </button>
              </div>
            ))}
          </div>
        </div>
      </div>

      {resFor && (
        <div className="fixed inset-0 z-[1100] grid place-items-center bg-black/50 p-4" onClick={() => setResFor(null)} role="dialog" aria-modal="true">
          <div className="card w-full max-w-sm p-6" onClick={e => e.stopPropagation()}>
            <h3 className="font-bold">Resolution evidence — {resFor.public_code}</h3>
            <p className="mt-1 text-sm text-ink-500">Upload a photo or video showing the fixed issue.</p>
            <label className="btn-primary mt-4 w-full cursor-pointer">
              <Upload className="size-4" />Choose file
              <input type="file" accept="video/mp4,video/webm,image/jpeg,image/png,image/webp" className="sr-only"
                onChange={e => e.target.files?.[0] && uploadResolution(e.target.files[0])} />
            </label>
            {pct > 0 && <div className="mt-3 h-2 overflow-hidden rounded-full bg-ink-200 dark:bg-white/10"><div className="h-full bg-brand-600 transition-all" style={{ width: `${pct}%` }} /></div>}
          </div>
        </div>
      )}
    </div>
  )
}
