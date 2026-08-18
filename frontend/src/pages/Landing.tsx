import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { ArrowRight, BrainCircuit, Building2, CheckCircle2, Clapperboard, MapPin, Megaphone, Route, ShieldCheck, Users } from 'lucide-react'
import { api } from '../lib/api'
import type { Report } from '../lib/types'
import { useI18n } from '../lib/i18n'
import IssueMap, { type MapPoint } from '../components/IssueMap'
import ReportCard from '../components/ReportCard'
import { CardSkeleton } from '../components/ui'
import { LogoMark } from '../components/Logo'

function Counter({ value }: { value: number }) {
  const [n, setN] = useState(0)
  useEffect(() => {
    let raf = 0; const start = performance.now()
    const tick = (t: number) => {
      const p = Math.min(1, (t - start) / 1100)
      setN(Math.round(value * (1 - Math.pow(1 - p, 3))))
      if (p < 1) raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [value])
  return <span className="tabular-nums">{n.toLocaleString()}</span>
}

export default function Landing() {
  const { t, lang } = useI18n()
  const [stats, setStats] = useState<{ reports: number; resolved: number; organizations: number; routed: number } | null>(null)
  const [recent, setRecent] = useState<Report[] | null>(null)
  const [points, setPoints] = useState<MapPoint[]>([])

  useEffect(() => {
    api.get('/api/dashboard/public-stats').then(setStats).catch(() => {})
    api.get('/api/reports?page_size=6').then(d => setRecent(d.items)).catch(() => setRecent([]))
    api.get('/api/reports/map').then(setPoints).catch(() => {})
  }, [])

  const steps = [
    { icon: Clapperboard, n: '01', title: lang === 'am' ? 'ቅረጽ' : 'Report', text: lang === 'am' ? 'ችግሩን በቪዲዮ ወይም ፎቶ ይቅረጹ እና ቦታውን ያመልክቱ።' : 'Capture the problem with video or photo and pin the location.' },
    { icon: BrainCircuit, n: '02', title: lang === 'am' ? 'AI ይተነትናል' : 'AI analyzes', text: lang === 'am' ? 'አካባቢያዊ AI ምድብ፣ ክብደት እና ኃላፊውን ተቋም ይመክራል።' : 'Local AI recommends a category, severity and the responsible organization.' },
    { icon: Route, n: '03', title: lang === 'am' ? 'ተቋም ይመልሳል' : 'Organization responds', text: lang === 'am' ? 'ሪፖርቱ ለትክክለኛው ተቋም ይመራል፤ ባለሙያዎች ስራውን ይጀምራሉ።' : 'The report is routed to the right bureau or utility and work begins.' },
    { icon: Users, n: '04', title: lang === 'am' ? 'ማህበረሰቡ ያያል' : 'Community sees progress', text: lang === 'am' ? 'ሁሉም ሰው ሁኔታውን፣ ማስረጃውን እና መፍትሄውን ይከታተላል።' : 'Everyone can follow status changes, evidence and the final resolution.' },
  ]

  return (
    <div>
      {/* ============ HERO ============ */}
      <section className="relative overflow-hidden w-full max-w-full">
        <div className="hero-grid pointer-events-none absolute inset-0" aria-hidden />
        <div className="pointer-events-none absolute -top-40 left-1/2 size-[520px] -translate-x-1/2 rounded-full bg-brand-500/10 blur-3xl" aria-hidden />
        <div className="mx-auto grid max-w-7xl items-center gap-10 px-4 pb-16 pt-14 lg:grid-cols-2 lg:pt-24">
          <div>
            <span className="chip border border-brand-200 bg-brand-50 text-brand-800 dark:border-brand-400/20 dark:bg-brand-400/10 dark:text-brand-200 animate-fade-up">
              <LogoMark size={15} /> {lang === 'am' ? 'የዜጎች ሪፖርት · በአካባቢያዊ AI' : 'Civic reporting · powered by local AI'}
            </span>
            <h1 className="mt-5 font-display text-[2.6rem] font-extrabold leading-[1.06] tracking-tight md:text-6xl animate-fade-up" style={{ animationDelay: '.05s' }}>
              {lang === 'am' ? (<>ይዩት። <span className="text-brand-600 dark:text-brand-400">ሪፖርት ያድርጉት።</span><br />ያሻሽሉት።</>)
                : (<>See it. <span className="text-brand-600 dark:text-brand-400">Report it.</span><br />Improve it.</>)}
            </h1>
            <p className="mt-5 max-w-xl text-base leading-relaxed text-ink-600 md:text-lg dark:text-ink-300 animate-fade-up" style={{ animationDelay: '.1s' }}>
              {t('hero_sub')}
            </p>
            <div className="mt-8 flex flex-wrap items-center gap-3 animate-fade-up" style={{ animationDelay: '.15s' }}>
              <Link to="/report" className="btn-primary !px-7 !py-3.5 !text-base"><Megaphone className="size-5" />{t('report_issue')}</Link>
              <Link to="/reports" className="btn-secondary !px-7 !py-3.5 !text-base">{t('explore')}<ArrowRight className="size-4" /></Link>
            </div>
            <p className="mt-5 flex items-center gap-2 text-xs text-ink-500 dark:text-ink-400 animate-fade-up" style={{ animationDelay: '.2s' }}>
              <ShieldCheck className="size-4 text-brand-600 dark:text-brand-400" />
              {lang === 'am' ? 'ማንነትዎ በይፋ አይታይም · AI ምክሮች በሰዎች ይገመገማሉ' : 'Your identity stays private · AI recommendations are reviewed by humans'}
            </p>
          </div>

          {/* hero visual: live map in a device-style frame */}
          <div className="relative animate-fade-up" style={{ animationDelay: '.15s' }}>
            <div className="card overflow-hidden !rounded-3xl border-2 !border-brand-900/10 dark:!border-white/10" style={{ boxShadow: 'var(--shadow-pop)' }}>
              <div className="flex items-center justify-between border-b border-ink-100 px-4 py-2.5 dark:border-white/10">
                <span className="flex items-center gap-2 text-xs font-semibold text-ink-600 dark:text-ink-300"><MapPin className="size-3.5 text-brand-600" />{lang === 'am' ? 'የቀጥታ የችግር ካርታ' : 'Live issue map'}</span>
                <span className="flex items-center gap-1.5 text-[11px] font-medium text-ink-400"><span className="size-1.5 animate-pulse rounded-full bg-brand-500" />{points.length} {lang === 'am' ? 'ሪፖርቶች' : 'reports'}</span>
              </div>
              <IssueMap points={points} className="h-[320px] md:h-[400px]" />
            </div>
            <div className="pointer-events-none absolute -bottom-7 left-6 z-[500] hidden md:block animate-fade-up" style={{ animationDelay: '.4s' }}>
              <div className="card flex items-center gap-3 !rounded-2xl !bg-white px-4 py-3 dark:!bg-ink-900" style={{ boxShadow: 'var(--shadow-pop)' }}>
                <span className="grid size-9 place-items-center rounded-xl bg-brand-50 dark:bg-brand-400/10"><BrainCircuit className="size-5 text-brand-600 dark:text-brand-300" /></span>
                <div>
                  <p className="text-xs font-bold">{lang === 'am' ? 'AI ምደባ' : 'AI classification'}</p>
                  <p className="text-[11px] text-ink-500 dark:text-ink-400">{lang === 'am' ? 'መንገድ · ክብደት 4/5 · 91%' : 'Roads · severity 4/5 · 91% conf.'}</p>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ============ IMPACT STATS ============ */}
      <section className="border-y border-ink-200/60 bg-white dark:border-white/10 dark:bg-white/[0.02]">
        <div className="mx-auto grid max-w-7xl grid-cols-2 gap-px overflow-hidden px-4 py-10 md:grid-cols-4">
          {[
            { label: t('reports_submitted'), v: stats?.reports, icon: Megaphone },
            { label: t('issues_resolved'), v: stats?.resolved, icon: CheckCircle2 },
            { label: t('orgs_notified'), v: stats?.organizations, icon: Building2 },
            { label: t('reports_routed'), v: stats?.routed, icon: Route },
          ].map((s, i) => (
            <div key={i} className="flex flex-col items-center gap-1 py-4 text-center">
              <s.icon className="size-5 text-brand-600 dark:text-brand-400" aria-hidden />
              <p className="text-3xl font-extrabold tabular-nums md:text-4xl">{s.v !== undefined ? <Counter value={s.v} /> : '—'}</p>
              <p className="text-xs font-medium text-ink-500 dark:text-ink-400">{s.label}</p>
            </div>
          ))}
        </div>
      </section>

      {/* ============ HOW IT WORKS ============ */}
      <section className="mx-auto max-w-7xl px-4 py-16" id="how">
        <p className="overline text-center">{lang === 'am' ? 'እንዴት ይሰራል' : 'How CivicLens works'}</p>
        <h2 className="mt-2 text-center text-3xl font-extrabold tracking-tight md:text-4xl">
          {lang === 'am' ? 'ከሪፖርት እስከ መፍትሄ' : 'From report to resolution'}
        </h2>
        <div className="relative mt-10 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {steps.map((s, i) => (
            <div key={i} className="card card-lift relative p-6">
              <span className="absolute right-5 top-4 text-4xl font-black tracking-tight text-ink-100 dark:text-white/5" aria-hidden>{s.n}</span>
              <div className="grid size-11 place-items-center rounded-xl bg-brand-600/10 text-brand-700 dark:bg-brand-400/10 dark:text-brand-300">
                <s.icon className="size-5.5" />
              </div>
              <h3 className="mt-4 text-lg font-bold">{s.title}</h3>
              <p className="mt-1.5 text-sm leading-relaxed text-ink-500 dark:text-ink-400">{s.text}</p>
            </div>
          ))}
        </div>
      </section>

      {/* ============ AI TRANSPARENCY ============ */}
      <section className="mx-auto max-w-7xl px-4 pb-16">
        <div className="card overflow-hidden !rounded-3xl">
          <div className="grid items-stretch lg:grid-cols-2">
            <div className="p-8 md:p-12">
              <p className="overline">{lang === 'am' ? 'ግልጽ AI' : 'Transparent AI'}</p>
              <h2 className="mt-2 text-2xl font-extrabold tracking-tight md:text-3xl">
                {lang === 'am' ? 'AI ይመክራል፤ ሰዎች ይወስናሉ።' : 'AI recommends. Humans decide.'}
              </h2>
              <p className="mt-4 max-w-lg text-sm leading-relaxed text-ink-600 dark:text-ink-300">
                {lang === 'am'
                  ? 'እያንዳንዱ ሪፖርት በአካባቢያዊ AI ይተነትናል — ቪዲዮ ፍሬሞች፣ ፎቶዎች እና መግለጫው። ውጤቱ ሁልጊዜ ከእርግጠኝነት መጠን ጋር እንደ ምክር ይቀርባል፤ የሰው ገምጋሚዎች ማንኛውንም ምደባ ማስተካከል ይችላሉ።'
                  : 'Every report is analyzed on locally-hosted models — video frames, photos and the description. Results always come with a confidence score, are clearly labelled as recommendations, and human reviewers can correct any classification.'}
              </p>
              <ul className="mt-6 space-y-2.5 text-sm">
                {(lang === 'am'
                  ? ['ምድብ + የክብደት ደረጃ 1–5', 'የእርግጠኝነት መጠን በእያንዳንዱ ውጤት', 'ኃላፊው ተቋም በሚስተካከሉ ህጎች ይመረጣል', 'AI በማይገኝበት ጊዜ ሪፖርቶች ወደ ሰው ግምገማ ይሄዳሉ']
                  : ['Category + severity scale 1–5', 'Confidence score on every result', 'Responsible organization picked by editable routing rules', 'If AI is unavailable, reports go to human review — never lost']
                ).map((x, i) => (
                  <li key={i} className="flex items-start gap-2.5"><CheckCircle2 className="mt-0.5 size-4.5 shrink-0 text-brand-600 dark:text-brand-400" />{x}</li>
                ))}
              </ul>
            </div>
            <div className="relative flex items-center justify-center bg-gradient-to-br from-brand-900 to-brand-950 p-10">
              <div className="eth-dots absolute inset-0 opacity-40" aria-hidden />
              <div className="relative w-full max-w-xs rounded-2xl border border-white/10 bg-white/5 p-5 backdrop-blur animate-fade-up">
                <p className="flex items-center gap-2 text-[11px] font-bold uppercase tracking-widest text-gold-400"><BrainCircuit className="size-4" />{t('ai_classification')}</p>
                <dl className="mt-4 space-y-3 text-sm text-white">
                  <div className="flex justify-between"><dt className="text-white/60">Category</dt><dd className="font-semibold">Roads &amp; Transportation</dd></div>
                  <div className="flex justify-between"><dt className="text-white/60">Issue</dt><dd className="font-semibold">Pothole</dd></div>
                  <div className="flex justify-between"><dt className="text-white/60">{t('severity')}</dt><dd><span className="chip bg-orange-400/20 text-orange-300">4 · Serious</span></dd></div>
                  <div className="flex justify-between"><dt className="text-white/60">{t('confidence')}</dt><dd className="font-bold">91%</dd></div>
                </dl>
                <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-white/10" role="presentation"><div className="h-full w-[91%] rounded-full bg-gradient-to-r from-brand-400 to-gold-400" /></div>
                <p className="mt-4 rounded-lg bg-gold-400/10 px-3 py-2 text-[11px] leading-snug text-gold-300">{t('ai_disclaimer')}</p>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ============ RECENT REPORTS ============ */}
      <section className="mx-auto max-w-7xl px-4 pb-16">
        <div className="mb-6 flex items-end justify-between">
          <div>
            <p className="overline">{lang === 'am' ? 'የቀጥታ የከተማ እይታ' : 'Live civic impact'}</p>
            <h2 className="mt-1 text-2xl font-extrabold tracking-tight md:text-3xl">{t('recent_reports')}</h2>
          </div>
          <Link to="/reports" className="btn-secondary max-sm:!px-3">{t('view_all')}<ArrowRight className="size-4" /></Link>
        </div>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {recent === null && Array.from({ length: 6 }).map((_, i) => <CardSkeleton key={i} />)}
          {recent?.map(r => <ReportCard key={r.id} r={r} />)}
        </div>
      </section>

      {/* ============ CTA ============ */}
      <section className="mx-auto max-w-7xl px-4 pb-20">
        <div className="relative overflow-hidden rounded-3xl bg-gradient-to-br from-brand-800 via-brand-900 to-brand-950 px-8 py-14 text-center text-white md:py-16">
          <div className="eth-strip absolute inset-x-0 top-0 h-1" aria-hidden />
          <LogoMark size={52} variant="dark" className="mx-auto" />
          <h2 className="mx-auto mt-5 max-w-xl text-3xl font-extrabold tracking-tight md:text-4xl">
            {lang === 'am' ? 'ከተማዎን ለማሻሻል ዛሬ ይጀምሩ' : 'Your city gets better when you speak up'}
          </h2>
          <p className="mx-auto mt-3 max-w-md text-sm text-brand-100/80">
            {lang === 'am' ? 'ሪፖርት ማድረግ ከሁለት ደቂቃ በታች ይፈጃል። መለያ እንኳን አያስፈልግም።' : 'Reporting takes under two minutes. You don\u2019t even need an account.'}
          </p>
          <div className="mt-7 flex flex-wrap justify-center gap-3">
            <Link to="/report" className="btn-gold !px-7 !py-3.5 !text-base"><Megaphone className="size-5" />{t('report_issue')}</Link>
            <Link to="/privacy" className="btn !border !border-white/25 !text-white hover:!bg-white/10">{t('privacy')}</Link>
          </div>
        </div>
      </section>
    </div>
  )
}
