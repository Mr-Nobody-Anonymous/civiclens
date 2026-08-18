import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Bar, BarChart, Cell, Line, LineChart, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { Activity, AlertTriangle, BrainCircuit, CheckCircle2, Clock, FileText, Flag, FolderOpen, RotateCw, Route, ScrollText, Users as UsersIcon, Wrench } from 'lucide-react'
import { api } from '../lib/api'
import type { Report } from '../lib/types'
import { SEVERITY, STATUS_META } from '../lib/types'
import { useApp } from '../lib/store'
import { StatCard, Skeleton } from '../components/ui'
import ReportRow from '../components/ReportRow'

interface Stats {
  total: number; today: number; week: number; month: number; open: number
  resolved: number; flagged: number
  by_category: Record<string, number>; by_status: Record<string, number>
  by_severity: Record<string, number>; by_organization: { name: string; count: number }[]
  ai: { avg_confidence: number | null; analyzed: number; corrected: number }
  avg_resolution_hours: number | null
  hotspots: { lat: number; lng: number; count: number }[]
  trend: { date: string; count: number }[]
}

const PIE_COLORS = ['#0d8a50', '#FCDD09', '#DA121A', '#3b82f6', '#8b5cf6', '#f97316', '#14b8a6', '#ec4899', '#64748b', '#a3e635']

type Tab = 'overview' | 'review' | 'flagged' | 'rules' | 'users' | 'jobs' | 'audit'

interface AdminUser { id: string; name: string; email: string; role: string; city?: string; is_active: boolean; organization?: string; created_at: string }
interface AdminJob { id: string; name: string; status: string; attempts: number; max_attempts: number; last_error?: string; payload?: string; created_at: string }

export default function AdminDashboard() {
  const { user, authLoaded } = useApp()
  const [stats, setStats] = useState<Stats | null>(null)
  const [tab, setTab] = useState<Tab>('overview')
  const [reviewList, setReviewList] = useState<Report[] | null>(null)
  const [rules, setRules] = useState<{ id: string; category: string; keywords?: string; city?: string; organization_name: string; priority: number; auto_assign: boolean; is_active: boolean }[]>([])
  const [logs, setLogs] = useState<{ id: string; action: string; detail?: string; entity?: string; created_at: string; ip?: string }[]>([])
  const [users, setUsers] = useState<AdminUser[] | null>(null)
  const [jobs, setJobs] = useState<AdminJob[] | null>(null)
  const { toast } = useApp()

  useEffect(() => {
    if (!user) return
    api.get('/api/dashboard/stats').then(setStats).catch(() => {})
  }, [user])

  useEffect(() => {
    if (!user) return
    if (tab === 'review') {
      api.get('/api/reports?status=under_review&page_size=50').then(d => setReviewList(d.items)).catch(() => setReviewList([]))
    } else if (tab === 'flagged') {
      api.get('/api/reports/priority').then((rows: Report[]) => setReviewList(rows.filter(r => r.is_flagged))).catch(() => setReviewList([]))
    } else if (tab === 'rules') {
      api.get('/api/rules').then(setRules).catch(() => {})
    } else if (tab === 'audit') {
      api.get('/api/audit-logs?limit=100').then(setLogs).catch(() => {})
    } else if (tab === 'users') {
      api.get('/api/admin/users?page_size=100').then(d => setUsers(d.items)).catch(() => setUsers([]))
    } else if (tab === 'jobs') {
      api.get('/api/admin/jobs?limit=100').then(setJobs).catch(() => setJobs([]))
    }
  }, [tab, user])

  if (authLoaded && (!user || !['admin', 'moderator'].includes(user.role))) {
    return <div className="mx-auto max-w-md px-4 py-20 text-center">
      <AlertTriangle className="mx-auto size-10 text-amber-500" />
      <h1 className="mt-3 text-xl font-bold">Staff access required</h1>
      <p className="mt-1 text-sm text-gray-500">Sign in with an administrator or moderator account.</p>
      <Link to="/login" className="btn-primary mt-5">Sign in</Link>
    </div>
  }

  const sevData = stats ? Object.entries(stats.by_severity).map(([k, v]) => ({ name: `${k} ${SEVERITY[+k as 1]?.label ?? ''}`, count: v, color: SEVERITY[+k as 1]?.color })) : []
  const catData = stats ? Object.entries(stats.by_category).map(([name, value]) => ({ name, value })) : []
  const statusData = stats ? Object.entries(stats.by_status).filter(([, v]) => v > 0).map(([k, v]) => ({ name: STATUS_META[k]?.label ?? k, count: v })) : []

  return (
    <div className="mx-auto max-w-7xl px-4 py-8">
      <h1 className="text-2xl font-extrabold md:text-3xl">Admin Dashboard</h1>
      <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">Platform overview, triage and AI oversight.</p>

      <div className="mt-5 flex flex-wrap gap-2" role="tablist">
        {([['overview', 'Overview', Activity], ['review', 'Needs Review', FolderOpen], ['flagged', 'Flagged', Flag], ['rules', 'Routing Rules', Route], ['users', 'Users', UsersIcon], ['jobs', 'Jobs', Wrench], ['audit', 'Audit Log', ScrollText]] as [Tab, string, typeof Activity][]).map(([id, label, Icon]) => (
          <button key={id} role="tab" aria-selected={tab === id} onClick={() => setTab(id)}
            className={`btn ${tab === id ? 'bg-brand-600 text-white shadow-lg shadow-brand-600/25' : 'border border-gray-300 bg-white text-gray-700 hover:bg-gray-100 dark:border-white/15 dark:bg-white/5 dark:text-gray-200'}`}>
            <Icon className="size-4" />{label}
          </button>
        ))}
      </div>

      {tab === 'overview' && (
        <div className="mt-6 space-y-5">
          {!stats ? <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">{Array.from({ length: 8 }).map((_, i) => <Skeleton key={i} className="h-28" />)}</div> : (
            <>
              <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
                <StatCard label="Total reports" value={stats.total} icon={<FileText className="size-5 text-brand-600" />} />
                <StatCard label="Today / Week / Month" value={<span className="text-xl">{stats.today} / {stats.week} / {stats.month}</span>} icon={<Clock className="size-5 text-sky-500" />} />
                <StatCard label="Open" value={stats.open} icon={<FolderOpen className="size-5 text-amber-500" />} />
                <StatCard label="Resolved" value={stats.resolved} icon={<CheckCircle2 className="size-5 text-emerald-500" />} />
                <StatCard label="AI avg. confidence" value={stats.ai.avg_confidence ? `${Math.round(stats.ai.avg_confidence * 100)}%` : '—'} icon={<BrainCircuit className="size-5 text-violet-500" />} />
                <StatCard label="AI corrected by humans" value={`${stats.ai.corrected} / ${stats.ai.analyzed}`} icon={<BrainCircuit className="size-5 text-orange-400" />} />
                <StatCard label="Avg. resolution time" value={stats.avg_resolution_hours ? `${(stats.avg_resolution_hours / 24).toFixed(1)}d` : '—'} icon={<Clock className="size-5 text-teal-500" />} />
                <StatCard label="Flagged reports" value={stats.flagged} icon={<Flag className="size-5 text-et-red" />} />
              </div>

              <div className="grid gap-5 lg:grid-cols-2">
                <div className="card p-5">
                  <h2 className="font-bold">Reports — last 14 days</h2>
                  <div className="mt-4 h-56">
                    <ResponsiveContainer width="100%" height="100%">
                      <LineChart data={stats.trend}>
                        <XAxis dataKey="date" tick={{ fontSize: 10 }} tickFormatter={d => d.slice(5)} />
                        <YAxis allowDecimals={false} tick={{ fontSize: 10 }} width={26} />
                        <Tooltip /><Line type="monotone" dataKey="count" stroke="#0d8a50" strokeWidth={2.5} dot={false} />
                      </LineChart>
                    </ResponsiveContainer>
                  </div>
                </div>
                <div className="card p-5">
                  <h2 className="font-bold">Severity distribution</h2>
                  <div className="mt-4 h-56">
                    <ResponsiveContainer width="100%" height="100%">
                      <BarChart data={sevData}>
                        <XAxis dataKey="name" tick={{ fontSize: 10 }} /><YAxis allowDecimals={false} tick={{ fontSize: 10 }} width={26} />
                        <Tooltip /><Bar dataKey="count" radius={[6, 6, 0, 0]}>
                          {sevData.map((d, i) => <Cell key={i} fill={d.color} />)}
                        </Bar>
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                </div>
                <div className="card p-5">
                  <h2 className="font-bold">By category</h2>
                  <div className="mt-4 h-56">
                    <ResponsiveContainer width="100%" height="100%">
                      <PieChart>
                        <Pie data={catData} dataKey="value" nameKey="name" innerRadius={45} outerRadius={80} paddingAngle={2}>
                          {catData.map((_, i) => <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />)}
                        </Pie>
                        <Tooltip />
                      </PieChart>
                    </ResponsiveContainer>
                  </div>
                </div>
                <div className="card p-5">
                  <h2 className="font-bold">By status / organization</h2>
                  <div className="mt-4 h-56">
                    <ResponsiveContainer width="100%" height="100%">
                      <BarChart data={statusData} layout="vertical">
                        <XAxis type="number" allowDecimals={false} tick={{ fontSize: 10 }} />
                        <YAxis type="category" dataKey="name" width={90} tick={{ fontSize: 10 }} />
                        <Tooltip /><Bar dataKey="count" fill="#0d8a50" radius={[0, 6, 6, 0]} />
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                  <div className="mt-2 flex flex-wrap gap-2 text-xs">
                    {stats.by_organization.map(o => <span key={o.name} className="rounded-full bg-gray-100 px-2.5 py-1 dark:bg-white/10">{o.name}: <b>{o.count}</b></span>)}
                  </div>
                </div>
              </div>

              <div className="card p-5">
                <h2 className="font-bold">Geographic hotspots</h2>
                <div className="mt-3 flex flex-wrap gap-2 text-xs">
                  {stats.hotspots.map((h, i) => (
                    <span key={i} className="rounded-full border border-orange-300/50 bg-orange-50 px-3 py-1.5 font-mono dark:bg-orange-400/10">
                      {h.lat.toFixed(2)}, {h.lng.toFixed(2)} · <b>{h.count}</b> reports
                    </span>
                  ))}
                  {stats.hotspots.length === 0 && <span className="text-gray-400">No location data yet.</span>}
                </div>
              </div>
            </>
          )}
        </div>
      )}

      {(tab === 'review' || tab === 'flagged') && (
        <div className="mt-6 space-y-3">
          {reviewList === null && <Skeleton className="h-40" />}
          {reviewList?.length === 0 && <p className="card p-8 text-center text-sm text-gray-500">Nothing here — all clear! 🎉</p>}
          {reviewList?.map(r => <ReportRow key={r.id} r={r} onChanged={() => {
            api.get(tab === 'review' ? '/api/reports?status=under_review&page_size=50' : '/api/reports/priority')
              .then(d => setReviewList(tab === 'review' ? d.items : (d as Report[]).filter((x: Report) => x.is_flagged)))
          }} />)}
        </div>
      )}

      {tab === 'rules' && (
        <div className="card mt-6 overflow-x-auto">
          <table className="w-full text-sm">
            <thead><tr className="border-b border-gray-200 text-left text-xs uppercase tracking-wider text-gray-500 dark:border-white/10">
              <th className="px-4 py-3">Category</th><th className="px-4 py-3">Keywords</th><th className="px-4 py-3">City</th>
              <th className="px-4 py-3">Organization</th><th className="px-4 py-3">Priority</th><th className="px-4 py-3">Auto-assign</th>
            </tr></thead>
            <tbody>
              {rules.map(r => (
                <tr key={r.id} className={`border-b border-gray-100 dark:border-white/5 ${!r.is_active ? 'opacity-40' : ''}`}>
                  <td className="px-4 py-3 font-semibold">{r.category}</td>
                  <td className="max-w-48 truncate px-4 py-3 text-xs text-gray-500">{r.keywords || '—'}</td>
                  <td className="px-4 py-3">{r.city || <span className="text-gray-400">National</span>}</td>
                  <td className="px-4 py-3">{r.organization_name}</td>
                  <td className="px-4 py-3">{r.priority}</td>
                  <td className="px-4 py-3">{r.auto_assign ? <span className="font-semibold text-emerald-600">Yes</span> : 'No'}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="px-4 py-3 text-xs text-gray-400">Rules route AI-classified reports to organizations. Manage via API: POST /api/rules (admin only).</p>
        </div>
      )}

      {tab === 'users' && (
        <div className="card mt-6 overflow-x-auto">
          {users === null ? <Skeleton className="m-4 h-40" /> : (
            <table className="w-full text-sm">
              <thead><tr className="border-b border-gray-200 text-left text-xs uppercase tracking-wider text-gray-500 dark:border-white/10">
                <th className="px-4 py-3">Name</th><th className="px-4 py-3">Email</th><th className="px-4 py-3">Role</th>
                <th className="px-4 py-3">Organization</th><th className="px-4 py-3">Active</th><th className="px-4 py-3">Actions</th>
              </tr></thead>
              <tbody>
                {users.map(u => (
                  <tr key={u.id} className={`border-b border-gray-100 dark:border-white/5 ${!u.is_active ? 'opacity-40' : ''}`}>
                    <td className="px-4 py-2.5 font-semibold">{u.name}</td>
                    <td className="px-4 py-2.5 text-xs">{u.email}</td>
                    <td className="px-4 py-2.5">
                      <select aria-label={`Role for ${u.email}`} className="input !w-auto !py-1 !text-xs" value={u.role}
                        disabled={u.id === user?.id}
                        onChange={async e => {
                          try {
                            await api.patch(`/api/admin/users/${u.id}/role`, { role: e.target.value })
                            toast('success', 'Role updated')
                            setUsers(us => us!.map(x => x.id === u.id ? { ...x, role: e.target.value } : x))
                          } catch (err) { toast('error', (err as Error).message) }
                        }}>
                        {['citizen', 'moderator', 'org_staff', 'admin'].map(r => <option key={r}>{r}</option>)}
                      </select>
                    </td>
                    <td className="px-4 py-2.5 text-xs">{u.organization ?? '—'}</td>
                    <td className="px-4 py-2.5 text-xs">{u.is_active ? 'Yes' : 'No'}</td>
                    <td className="px-4 py-2.5">
                      {u.id !== user?.id && (
                        <button className="btn-secondary !py-1 !text-xs" onClick={async () => {
                          if (!window.confirm(`${u.is_active ? 'Deactivate' : 'Reactivate'} ${u.email}?`)) return
                          try {
                            await api.patch(`/api/admin/users/${u.id}/active?active=${!u.is_active}`)
                            setUsers(us => us!.map(x => x.id === u.id ? { ...x, is_active: !u.is_active } : x))
                            toast('success', 'Updated')
                          } catch (err) { toast('error', (err as Error).message) }
                        }}>{u.is_active ? 'Deactivate' : 'Reactivate'}</button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}

      {tab === 'jobs' && (
        <div className="card mt-6 overflow-x-auto">
          {jobs === null ? <Skeleton className="m-4 h-40" /> : jobs.length === 0 ? (
            <p className="p-8 text-center text-sm text-gray-500">No background jobs yet.</p>
          ) : (
            <table className="w-full text-sm">
              <thead><tr className="border-b border-gray-200 text-left text-xs uppercase tracking-wider text-gray-500 dark:border-white/10">
                <th className="px-4 py-3">Job</th><th className="px-4 py-3">Status</th><th className="px-4 py-3">Attempts</th>
                <th className="px-4 py-3">Error</th><th className="px-4 py-3">Created</th><th className="px-4 py-3"></th>
              </tr></thead>
              <tbody>
                {jobs.map(j => (
                  <tr key={j.id} className="border-b border-gray-100 dark:border-white/5">
                    <td className="px-4 py-2.5 font-mono text-xs">{j.name}</td>
                    <td className="px-4 py-2.5">
                      <span className={`rounded-full px-2 py-0.5 text-xs font-semibold ${
                        j.status === 'done' ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-300' :
                        j.status === 'dead' ? 'bg-red-100 text-red-700 dark:bg-red-500/15 dark:text-red-300' :
                        j.status === 'failed' ? 'bg-orange-100 text-orange-700 dark:bg-orange-500/15 dark:text-orange-300' :
                        'bg-gray-100 text-gray-600 dark:bg-white/10 dark:text-gray-300'}`}>{j.status}</span>
                    </td>
                    <td className="px-4 py-2.5 text-xs">{j.attempts}/{j.max_attempts}</td>
                    <td className="max-w-64 truncate px-4 py-2.5 text-xs text-gray-500">{j.last_error ?? '—'}</td>
                    <td className="whitespace-nowrap px-4 py-2.5 text-xs text-gray-400">{new Date(j.created_at).toLocaleString()}</td>
                    <td className="px-4 py-2.5">
                      {['failed', 'dead'].includes(j.status) && (
                        <button className="btn-secondary !py-1 !text-xs" onClick={async () => {
                          try {
                            await api.post(`/api/admin/jobs/${j.id}/retry`)
                            toast('success', 'Job requeued')
                            api.get('/api/admin/jobs?limit=100').then(setJobs)
                          } catch (err) { toast('error', (err as Error).message) }
                        }}><RotateCw className="size-3" />Retry</button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}

      {tab === 'audit' && (
        <div className="card mt-6 overflow-x-auto">
          <table className="w-full text-sm">
            <thead><tr className="border-b border-gray-200 text-left text-xs uppercase tracking-wider text-gray-500 dark:border-white/10">
              <th className="px-4 py-3">Time</th><th className="px-4 py-3">Action</th><th className="px-4 py-3">Entity</th><th className="px-4 py-3">Detail</th><th className="px-4 py-3">IP</th>
            </tr></thead>
            <tbody>
              {logs.map(l => (
                <tr key={l.id} className="border-b border-gray-100 dark:border-white/5">
                  <td className="whitespace-nowrap px-4 py-2.5 text-xs text-gray-500">{new Date(l.created_at).toLocaleString()}</td>
                  <td className="px-4 py-2.5 font-mono text-xs font-semibold">{l.action}</td>
                  <td className="px-4 py-2.5 text-xs">{l.entity}</td>
                  <td className="max-w-56 truncate px-4 py-2.5 text-xs text-gray-500">{l.detail}</td>
                  <td className="px-4 py-2.5 font-mono text-xs text-gray-400">{l.ip}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
