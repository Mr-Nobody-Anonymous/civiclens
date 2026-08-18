import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { ArrowRight, BrainCircuit, Building2, CheckCircle2, Clapperboard, Megaphone, Route, ShieldCheck, Sparkles } from 'lucide-react'
import { api } from '../lib/api'
import type { Report } from '../lib/types'
import { useI18n } from '../lib/i18n'
import IssueMap, { type MapPoint } from '../components/IssueMap'
import ReportCard from '../components/ReportCard'
import { CardSkeleton } from '../components/ui'

function Counter({ value }: { value: number }) {
  const [n, setN] = useState(0)
  useEffect(() => {
    let raf = 0; const start = performance.now()
    const tick = (t: number) => {
      const p = Math.min(1, (t - start) / 1200)
      setN(Math.round(value * (1 - Math.pow(1 - p, 3))))
      if (p < 1) raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [value])
  return <span className="tabular-nums">{n.toLocaleString()}</span>
}

export default function Landing() {
  const { t } = useI18n()
  const nav = useNavigate()
  const [stats, setStats] = useState<{ reports: number; resolved: number; organizations: number; routed: number } | null>(null)
  const [recent, setRecent] = useState<Report[] | null>(null)
  const [points, setPoints] = useState<MapPoint[]>([])

  useEffect(() => {
    api.get('/api/dashboard/public-stats').then(setStats).catch(() => {})
    api.get('/api/reports?page_size=6').then(d => setRecent(d.items)).catch(() => setRecent([]))
    api.get('/api/reports/map').then(d => setPoints(d.map((p: MapPoint & { code: string }) => ({ ...p })))).catch(() => {})
  }, [])

  const steps = [
    { icon: Clapperboard, title: 'Capture', text: 'Record a short video or photo of the problem right from your phone.' },
    { icon: BrainCircuit, title: 'AI triage', text: 'Local AI classifies the issue, estimates severity, and suggests who is responsible.' },
    { icon: Route, title: 'Routing', text: 'Configurable rules route it to Ethio telecom, the Water Authority, the Roads Authority and more.' },
    { icon: CheckCircle2, title: 'Resolution', text: 'Track status changes and get notified when the issue is fixed.' },
  ]

  return (
    <div>
      {/* HERO */}
      <section className="relative overflow-hidden">
        <div className="pointer-events-none absolute -top-32 left-1/2 size-[600px] -translate-x-1/2 rounded-full bg-brand-500/15 blur-3xl" aria-hidden />
        <div className="pointer-events-none absolute right-[-120px] top-40 size-72 rounded-full bg-et-yellow/10 blur-3xl" aria-hidden />
        <div className="mx-auto max-w-7xl px-4 pb-14 pt-16 text-center md:pt-24">
          <span className="inline-flex items-center gap-2 rounded-full border border-brand-600/25 bg-brand-600/10 px-4 py-1.5 text-xs font-semibold text-brand-700 dark:text-brand-300 animate-fade-up">
            <Sparkles className="size-3.5" /> Civic reporting powered by local AI
          </span>
          <h1 className="mx-auto mt-5 max-w-3xl text-4xl font-extrabold leading-tight tracking-tight md:text-6xl animate-fade-up" style={{ animationDelay: '.05s' }}>
            {t('tagline')}<br />
            <span className="bg-gradient-to-r from-brand-600 via-emerald-500 to-et-yellow bg-clip-text text-transparent">{t('tagline2')}</span>
          </h1>
          <p className="mx-auto mt-5 max-w-2xl text-base text-gray-600 md:text-lg dark:text-gray-300 animate-fade-up" style={{ animationDelay: '.1s' }}>
            {t('hero_sub')}
          </p>
          <div className="mt-8 flex flex-wrap items-center justify-center gap-3 animate-fade-up" style={{ animationDelay: '.15s' }}>
            <Link to="/report" className="btn-primary !px-7 !py-3.5 !text-base"><Megaphone className="size-5" />{t('report_issue')}</Link>
            <Link to="/reports" className="btn-secondary !px-7 !py-3.5 !text-base">{t('explore')}<ArrowRight className="size-4" /></Link>
          </div>

          {/* STATS */}
          <div className="mx-auto mt-14 grid max-w-4xl grid-cols-2 gap-3 md:grid-cols-4">
            {[
              { label: t('reports_submitted'), v: stats?.reports },
              { label: t('issues_resolved'), v: stats?.resolved },
              { label: t('orgs_notified'), v: stats?.organizations },
              { label: t('reports_routed'), v: stats?.routed },
            ].map((s, i) => (
              <div key={i} className="card p-5 animate-fade-up" style={{ animationDelay: `${0.2 + i * 0.05}s` }}>
                <p className="text-3xl font-extrabold text-brand-700 dark:text-brand-300">{s.v !== undefined ? <Counter value={s.v} /> : '–'}</p>
                <p className="mt-1 text-xs font-medium text-gray-500 dark:text-gray-400">{s.label}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* HOW IT WORKS */}
      <section className="mx-auto max-w-7xl px-4 py-14" id="how">
        <h2 className="text-center text-2xl font-extrabold md:text-3xl">{t('how')}</h2>
        <div className="mt-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {steps.map((s, i) => (
            <div key={i} className="card group relative overflow-hidden p-6 transition hover:-translate-y-1 hover:shadow-xl">
              <span className="absolute right-4 top-3 text-5xl font-black text-gray-100 dark:text-white/5">{i + 1}</span>
              <div className="grid size-11 place-items-center rounded-xl bg-brand-600/10 text-brand-700 dark:text-brand-300">
                <s.icon className="size-5.5" />
              </div>
              <h3 className="mt-4 font-bold">{s.title}</h3>
              <p className="mt-1.5 text-sm text-gray-500 dark:text-gray-400">{s.text}</p>
            </div>
          ))}
        </div>
      </section>

      {/* MAP PREVIEW */}
      <section className="mx-auto max-w-7xl px-4 py-6">
        <div className="card overflow-hidden">
          <div className="flex items-center justify-between px-6 py-4">
            <div>
              <h2 className="text-xl font-extrabold">Live issue map</h2>
              <p className="text-sm text-gray-500 dark:text-gray-400">Reported issues across Ethiopian cities, coloured by severity.</p>
            </div>
            <Link to="/map" className="btn-secondary max-sm:hidden">{t('view_all')}<ArrowRight className="size-4" /></Link>
          </div>
          <IssueMap points={points} className="h-80 md:h-96" />
        </div>
      </section>

      {/* RECENT REPORTS */}
      <section className="mx-auto max-w-7xl px-4 py-12">
        <div className="mb-6 flex items-center justify-between">
          <h2 className="text-2xl font-extrabold">{t('recent_reports')}</h2>
          <Link to="/reports" className="text-sm font-semibold text-brand-700 hover:underline dark:text-brand-300">{t('view_all')} →</Link>
        </div>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {recent === null && Array.from({ length: 6 }).map((_, i) => <CardSkeleton key={i} />)}
          {recent?.map(r => <ReportCard key={r.id} r={r} />)}
        </div>
      </section>

      {/* TRUST */}
      <section className="mx-auto max-w-7xl px-4 pb-16">
        <div className="card relative overflow-hidden bg-gradient-to-br from-brand-700 to-brand-900 p-8 text-white md:p-12">
          <div className="eth-strip absolute inset-x-0 top-0 h-1" />
          <div className="grid items-center gap-8 md:grid-cols-2">
            <div>
              <h2 className="text-2xl font-extrabold md:text-3xl">Built on trust & transparency</h2>
              <ul className="mt-5 space-y-3 text-sm text-brand-100">
                {['Every AI classification shows its confidence and can be corrected by human reviewers.',
                  'Your personal details are never shown publicly — only the issue itself.',
                  'Videos are stored securely on the server and streamed through access-controlled endpoints.',
                  'Works for any Ethiopian city — Addis Ababa, Adama, Bahir Dar, Hawassa, Mekelle and more.'].map((x, i) => (
                  <li key={i} className="flex items-start gap-2.5"><ShieldCheck className="mt-0.5 size-4.5 shrink-0 text-et-yellow" />{x}</li>
                ))}
              </ul>
              <div className="mt-7 flex gap-3">
                <button onClick={() => nav('/report')} className="btn bg-white text-brand-800 hover:bg-brand-50">{t('report_issue')}</button>
                <Link to="/privacy" className="btn border border-white/25 text-white hover:bg-white/10">{t('privacy')}</Link>
              </div>
            </div>
            <div className="card !border-white/15 !bg-white/10 p-5 backdrop-blur">
              <p className="text-xs font-bold uppercase tracking-widest text-et-yellow"><Building2 className="mr-1.5 inline size-4" />Routed to organizations like</p>
              <div className="mt-4 grid grid-cols-2 gap-2.5 text-sm font-semibold">
                {['Ethio telecom', 'City Roads Authority', 'Water & Sewerage Authority', 'Ethiopian Electric Utility', 'Education Bureau', 'City Administration'].map(o => (
                  <div key={o} className="rounded-xl bg-white/10 px-3.5 py-3">{o}</div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </section>
    </div>
  )
}
