/* Public transparency portal — no account needed, privacy-preserving. */
import { useEffect, useState } from 'react'
import { Bar, BarChart, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { Building2, CheckCircle2, FolderOpen, Megaphone, ShieldCheck } from 'lucide-react'
import { api } from '../lib/api'
import { useApp } from '../lib/store'
import { useI18n } from '../lib/i18n'
import { Skeleton, StatCard } from '../components/ui'
import { LogoMark } from '../components/Logo'

interface TData {
  city: string; reports: number; resolved: number; open: number
  resolution_rate: number | null
  top_issues: { category: string; count: number }[]
  organization_performance: { organization: string; reports: number; resolved: number
                              resolution_rate: number; avg_resolution_days: number | null }[]
  monthly_trend: { month: string; reports: number; resolved: number }[]
  active_clusters: number
  privacy_note: string
}

export default function Transparency() {
  const { meta } = useApp()
  const { lang } = useI18n()
  const [city, setCity] = useState('')
  const [data, setData] = useState<TData | null>(null)

  useEffect(() => {
    setData(null)
    api.get(`/api/transparency${city ? `?city=${encodeURIComponent(city)}` : ''}`)
      .then(setData).catch(() => {})
  }, [city])

  return (
    <div className="mx-auto max-w-7xl px-4 py-10">
      <div className="text-center">
        <LogoMark size={44} className="mx-auto" />
        <h1 className="mt-3 text-3xl font-extrabold tracking-tight md:text-4xl">
          {lang === 'am' ? 'የCivicLens ግልጽነት' : 'CivicLens Transparency'}
        </h1>
        <p className="mx-auto mt-2 max-w-xl text-sm text-ink-500 dark:text-ink-400">
          {lang === 'am'
            ? 'የከተማዎ የዜጎች ሪፖርቶች እና የተቋማት ምላሽ — ለሁሉም ክፍት።'
            : 'How citizen reports are being resolved across Ethiopian cities — open to everyone.'}
        </p>
        <select aria-label="City" className="input mx-auto mt-4 !w-auto" value={city} onChange={e => setCity(e.target.value)}>
          <option value="">{lang === 'am' ? 'ሁሉም ከተሞች' : 'All cities'}</option>
          {(meta?.cities ?? []).map(c => <option key={c}>{c}</option>)}
        </select>
      </div>

      {!data ? (
        <div className="mt-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-28" />)}
        </div>
      ) : (
        <>
          <div className="mt-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <StatCard label={lang === 'am' ? 'ሪፖርቶች' : 'Reports'} value={data.reports.toLocaleString()} icon={<Megaphone className="size-5 text-brand-600" />} />
            <StatCard label={lang === 'am' ? 'ተፈትተዋል' : 'Resolved'} value={data.resolved.toLocaleString()} icon={<CheckCircle2 className="size-5 text-emerald-500" />} />
            <StatCard label={lang === 'am' ? 'ክፍት' : 'Open'} value={data.open.toLocaleString()} icon={<FolderOpen className="size-5 text-amber-500" />} />
            <StatCard label={lang === 'am' ? 'የመፍትሄ መጠን' : 'Resolution rate'}
              value={data.resolution_rate != null ? `${Math.round(data.resolution_rate * 100)}%` : '—'}
              icon={<ShieldCheck className="size-5 text-brand-600" />} />
          </div>

          <div className="mt-6 grid gap-5 lg:grid-cols-2">
            <div className="card p-5">
              <h2 className="font-bold">{lang === 'am' ? 'ዋና ዋና ችግሮች' : 'Top issues'}</h2>
              <div className="mt-4 h-64">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={data.top_issues} layout="vertical" margin={{ left: 30 }}>
                    <XAxis type="number" allowDecimals={false} tick={{ fontSize: 10 }} />
                    <YAxis type="category" dataKey="category" width={130} tick={{ fontSize: 10 }} />
                    <Tooltip /><Bar dataKey="count" fill="#0c7d48" radius={[0, 6, 6, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>
            <div className="card p-5">
              <h2 className="font-bold">{lang === 'am' ? 'ወርሃዊ አዝማሚያ' : 'Monthly trend'}</h2>
              <div className="mt-4 h-64">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={data.monthly_trend}>
                    <XAxis dataKey="month" tick={{ fontSize: 10 }} />
                    <YAxis allowDecimals={false} tick={{ fontSize: 10 }} width={28} />
                    <Tooltip />
                    <Line type="monotone" dataKey="reports" stroke="#0c7d48" strokeWidth={2.5} dot={false} name="Reports" />
                    <Line type="monotone" dataKey="resolved" stroke="#F4B942" strokeWidth={2.5} dot={false} name="Resolved" />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </div>
          </div>

          <div className="card mt-6 overflow-x-auto">
            <h2 className="px-5 pt-5 font-bold">{lang === 'am' ? 'የተቋማት አፈጻጸም' : 'Organization performance'}</h2>
            <table className="mt-3 w-full text-sm">
              <thead>
                <tr className="border-b border-ink-200 text-left text-xs uppercase tracking-wider text-ink-500 dark:border-white/10">
                  <th className="px-5 py-3">Organization</th>
                  <th className="px-5 py-3">Reports</th>
                  <th className="px-5 py-3">Resolved</th>
                  <th className="px-5 py-3">Rate</th>
                  <th className="px-5 py-3">Avg. days</th>
                </tr>
              </thead>
              <tbody>
                {data.organization_performance.map(o => (
                  <tr key={o.organization} className="border-b border-ink-100 dark:border-white/5">
                    <td className="px-5 py-3 font-semibold"><Building2 className="mr-1.5 inline size-4 text-brand-600" />{o.organization}</td>
                    <td className="px-5 py-3 tabular-nums">{o.reports}</td>
                    <td className="px-5 py-3 tabular-nums">{o.resolved}</td>
                    <td className="px-5 py-3">
                      <div className="flex items-center gap-2">
                        <div className="h-1.5 w-20 overflow-hidden rounded-full bg-ink-200 dark:bg-white/10">
                          <div className="h-full rounded-full bg-brand-500" style={{ width: `${o.resolution_rate * 100}%` }} />
                        </div>
                        <span className="text-xs font-bold tabular-nums">{Math.round(o.resolution_rate * 100)}%</span>
                      </div>
                    </td>
                    <td className="px-5 py-3 tabular-nums">{o.avg_resolution_days ?? '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <p className="mt-6 text-center text-xs text-ink-400">{data.privacy_note}</p>
        </>
      )}
    </div>
  )
}
