/* City Intelligence — reports → clusters → hotspots → emerging trends.
   All real aggregated data; advisories are clearly labelled. */
import { useEffect, useState } from 'react'
import { AlertTriangle, Flame, Layers, TrendingDown, TrendingUp } from 'lucide-react'
import { api } from '../lib/api'
import { useApp } from '../lib/store'
import { SeverityBadge, Skeleton, StatCard } from './ui'
import IssueMap from './IssueMap'

interface Overview {
  city: string; open_reports: number; critical_open: number; active_clusters: number
  hotspots: { lat: number; lng: number; count: number; top_category: string
              max_severity: number; unique_reporters: number; trend_pct: number | null
              advisory: string | null }[]
  emerging_trends: { category: string; this_week: number; prev_week: number
                     change_pct: number | null; advisory: string | null }[]
  advisory_note: string
}

export default function CityIntelligence() {
  const { meta } = useApp()
  const [city, setCity] = useState('')
  const [data, setData] = useState<Overview | null>(null)

  const [briefing, setBriefing] = useState<{ kpis: Record<string, number>; advisory: string
    advisory_label: string; largest_clusters: { id: string; title: string; report_count: number
    unique_reporters: number }[] } | null>(null)

  useEffect(() => {
    setData(null)
    const qp = city ? `?city=${encodeURIComponent(city)}` : ''
    api.get(`/api/intelligence/overview${qp}`).then(setData).catch(() => {})
    api.get(`/api/intelligence/briefing${qp}`).then(setBriefing).catch(() => {})
  }, [city])

  if (!data) return <div className="mt-6 space-y-3"><Skeleton className="h-24" /><Skeleton className="h-64" /></div>

  return (
    <div className="mt-6 space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-ink-500 dark:text-ink-400">{data.advisory_note}</p>
        <select aria-label="City" className="input !w-auto !py-2 !text-sm" value={city} onChange={e => setCity(e.target.value)}>
          <option value="">All cities</option>
          {(meta?.cities ?? []).map(c => <option key={c}>{c}</option>)}
        </select>
      </div>

      {/* Civic Briefing — the morning screen */}
      {briefing && (
        <div className="card overflow-hidden !rounded-3xl">
          <div className="bg-gradient-to-r from-brand-800 to-brand-950 px-6 py-4 text-white">
            <h3 className="text-lg font-extrabold">📋 Civic Briefing{city ? ` — ${city}` : ''}</h3>
            <p className="text-xs text-brand-200/80">{new Date().toLocaleDateString(undefined, { weekday: 'long', month: 'long', day: 'numeric' })}</p>
          </div>
          <div className="grid grid-cols-2 gap-px bg-ink-100 p-px sm:grid-cols-3 lg:grid-cols-6 dark:bg-white/5">
            {([['🚨', 'Critical open', briefing.kpis.critical_emerging],
               ['📈', 'New this week', briefing.kpis.new_reports_week],
               ['⏰', 'SLA breaches (7d)', briefing.kpis.sla_breaches_week],
               ['🔄', 'Reopened', briefing.kpis.reopened_issues],
               ['👥', 'Citizens engaged', briefing.kpis.citizens_engaged_week],
               ['🗳️', 'Community votes', briefing.kpis.community_votes_week]] as const).map(([icon, label, v], i) => (
              <div key={i} className="bg-white px-4 py-3 dark:bg-ink-900">
                <p className="text-lg" aria-hidden>{icon}</p>
                <p className="text-xl font-extrabold tabular-nums">{v}</p>
                <p className="text-[10px] font-semibold uppercase tracking-wider text-ink-500 dark:text-ink-400">{label}</p>
              </div>
            ))}
          </div>
          <div className="border-t border-ink-100 px-6 py-4 dark:border-white/10">
            <p className="flex items-center gap-2 text-[11px] font-bold uppercase tracking-widest text-violet-600 dark:text-violet-300">🤖 AI advisory</p>
            <p className="mt-1.5 text-sm leading-relaxed text-ink-700 dark:text-ink-200">{briefing.advisory}</p>
            {briefing.largest_clusters.length > 0 && (
              <p className="mt-2 text-xs text-ink-500 dark:text-ink-400">
                Largest cluster: <strong>{briefing.largest_clusters[0].title.slice(0, 60)}</strong> — {briefing.largest_clusters[0].report_count} reports, {briefing.largest_clusters[0].unique_reporters} citizens
              </p>
            )}
            <p className="mt-2 text-[11px] font-semibold text-amber-600 dark:text-amber-400">{briefing.advisory_label}</p>
          </div>
        </div>
      )}

      <div className="grid gap-4 sm:grid-cols-3">
        <StatCard label="Open reports" value={data.open_reports} icon={<Layers className="size-5 text-brand-600" />} />
        <StatCard label="Critical open" value={data.critical_open} accent={data.critical_open > 0 ? 'bg-et-red' : undefined}
          icon={<AlertTriangle className="size-5 text-et-red" />} />
        <StatCard label="Active clusters (≥2 reports)" value={data.active_clusters} icon={<Flame className="size-5 text-orange-500" />} />
      </div>

      {/* hotspot map */}
      <div className="card overflow-hidden">
        <div className="flex items-center justify-between px-5 py-3">
          <h3 className="font-bold">Geographic hotspots (last 30 days)</h3>
          <span className="text-xs text-ink-400">{data.hotspots.length} hotspot cells</span>
        </div>
        <IssueMap heatmap points={data.hotspots.flatMap(h =>
          Array.from({ length: Math.min(h.count, 20) }, (_, i) => ({
            id: `${h.lat}-${h.lng}-${i}`, lat: h.lat, lng: h.lng, severity: h.max_severity })))}
          center={data.hotspots[0] ? [data.hotspots[0].lat, data.hotspots[0].lng] : undefined}
          className="h-72" />
      </div>

      <div className="grid gap-5 lg:grid-cols-2">
        {/* hotspot list */}
        <div className="card p-5">
          <h3 className="font-bold">Hotspot detail</h3>
          <div className="mt-3 space-y-2.5">
            {data.hotspots.length === 0 && <p className="text-sm text-ink-400">No hotspots detected (needs ≥3 reports per ~1km cell).</p>}
            {data.hotspots.slice(0, 8).map((h, i) => (
              <div key={i} className="rounded-xl border border-ink-200/70 p-3 dark:border-white/10">
                <div className="flex flex-wrap items-center gap-2 text-sm">
                  <span className="font-bold">{h.top_category}</span>
                  <SeverityBadge sev={h.max_severity} />
                  {h.trend_pct != null && (
                    <span className={`chip ${h.trend_pct > 0 ? 'bg-red-100 text-red-700 dark:bg-red-500/15 dark:text-red-300' : 'bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-300'}`}>
                      {h.trend_pct > 0 ? <TrendingUp className="size-3" /> : <TrendingDown className="size-3" />}
                      {h.trend_pct > 0 ? '+' : ''}{h.trend_pct}%
                    </span>
                  )}
                </div>
                <p className="mt-1 text-xs text-ink-500 dark:text-ink-400">
                  {h.count} reports · {h.unique_reporters} citizens · {h.lat}, {h.lng}
                </p>
                {h.advisory && (
                  <p className="mt-1.5 rounded-lg bg-amber-50 px-2.5 py-1.5 text-[11px] text-amber-800 dark:bg-amber-400/10 dark:text-amber-300">
                    ⚠️ AI advisory: {h.advisory}
                  </p>
                )}
              </div>
            ))}
          </div>
        </div>

        {/* emerging trends */}
        <div className="card p-5">
          <h3 className="font-bold">Emerging trends (week over week)</h3>
          <div className="mt-3 space-y-2.5">
            {data.emerging_trends.length === 0 && <p className="text-sm text-ink-400">Not enough recent data for trend analysis.</p>}
            {data.emerging_trends.map((t, i) => (
              <div key={i} className="flex items-center justify-between gap-3 rounded-xl border border-ink-200/70 px-3 py-2.5 dark:border-white/10">
                <div className="min-w-0">
                  <p className="text-sm font-semibold">{t.category}</p>
                  <p className="text-xs text-ink-400">{t.this_week} this week · {t.prev_week} last week</p>
                  {t.advisory && <p className="mt-1 text-[11px] text-amber-700 dark:text-amber-300">⚠️ {t.advisory}</p>}
                </div>
                {t.change_pct != null && (
                  <span className={`shrink-0 text-lg font-extrabold tabular-nums ${t.change_pct > 0 ? 'text-et-red' : 'text-brand-600'}`}>
                    {t.change_pct > 0 ? '+' : ''}{t.change_pct}%
                  </span>
                )}
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
