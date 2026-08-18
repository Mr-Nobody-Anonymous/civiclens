import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { AlertTriangle, ListOrdered } from 'lucide-react'
import { api } from '../lib/api'
import type { Report } from '../lib/types'
import { SEVERITY } from '../lib/types'
import { useApp } from '../lib/store'
import { Skeleton } from '../components/ui'
import ReportRow from '../components/ReportRow'

export default function PriorityQueue() {
  const { user, authLoaded } = useApp()
  const [rows, setRows] = useState<Report[] | null>(null)

  const load = () => api.get('/api/reports/priority').then(setRows).catch(() => setRows([]))
  useEffect(() => { if (user) load() }, [user])

  if (authLoaded && (!user || !['admin', 'moderator', 'org_staff'].includes(user.role))) {
    return <div className="mx-auto max-w-md px-4 py-20 text-center">
      <AlertTriangle className="mx-auto size-10 text-amber-500" />
      <h1 className="mt-3 text-xl font-bold">Authorized users only</h1>
      <Link to="/login" className="btn-primary mt-5">Sign in</Link>
    </div>
  }

  const groups = [5, 4, 3, 2, 1].map(s => ({ sev: s, items: rows?.filter(r => (r.severity ?? 0) === s) ?? [] }))
  const unrated = rows?.filter(r => !r.severity) ?? []

  return (
    <div className="mx-auto max-w-5xl px-4 py-8">
      <h1 className="flex items-center gap-2 text-2xl font-extrabold"><ListOrdered className="size-6 text-brand-600" />Priority Queue</h1>
      <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">Unresolved reports ordered by severity — critical first.{user?.role === 'org_staff' ? ' Showing only your organization.' : ''}</p>

      {rows === null && <div className="mt-6 space-y-3"><Skeleton className="h-24" /><Skeleton className="h-24" /></div>}
      {rows?.length === 0 && <p className="card mt-6 p-10 text-center text-sm text-gray-500">Queue is empty — no open reports. 🎉</p>}

      <div className="mt-6 space-y-7">
        {groups.map(g => g.items.length > 0 && (
          <section key={g.sev}>
            <h2 className="mb-2.5 flex items-center gap-2 text-sm font-bold uppercase tracking-wider" style={{ color: SEVERITY[g.sev as 1].color }}>
              <span className="size-2.5 rounded-full" style={{ background: SEVERITY[g.sev as 1].color }} />
              {g.sev} — {SEVERITY[g.sev as 1].label} ({g.items.length})
            </h2>
            <div className="space-y-2.5">{g.items.map(r => <ReportRow key={r.id} r={r} onChanged={load} orgMode={user?.role === 'org_staff'} />)}</div>
          </section>
        ))}
        {unrated.length > 0 && (
          <section>
            <h2 className="mb-2.5 text-sm font-bold uppercase tracking-wider text-gray-400">Awaiting AI severity ({unrated.length})</h2>
            <div className="space-y-2.5">{unrated.map(r => <ReportRow key={r.id} r={r} onChanged={load} />)}</div>
          </section>
        )}
      </div>
    </div>
  )
}
