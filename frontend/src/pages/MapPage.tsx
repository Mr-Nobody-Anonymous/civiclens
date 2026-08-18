import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Flame, MapPin } from 'lucide-react'
import { api } from '../lib/api'
import { SEVERITY } from '../lib/types'
import { useApp } from '../lib/store'
import { useI18n } from '../lib/i18n'
import IssueMap, { type MapPoint } from '../components/IssueMap'

export default function MapPage() {
  const { meta } = useApp()
  const { t } = useI18n()
  const nav = useNavigate()
  const [points, setPoints] = useState<MapPoint[]>([])
  const [category, setCategory] = useState('')
  const [minSev, setMinSev] = useState(0)
  const [heat, setHeat] = useState(false)

  useEffect(() => {
    const usp = new URLSearchParams()
    if (category) usp.set('category', category)
    if (minSev) usp.set('min_severity', String(minSev))
    api.get(`/api/reports/map?${usp}`).then(setPoints).catch(() => {})
  }, [category, minSev])

  const center = useMemo<[number, number]>(() =>
    meta ? [meta.default_center.lat, meta.default_center.lng] : [9.0108, 38.7613], [meta])

  return (
    <div className="mx-auto max-w-7xl px-4 py-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-extrabold"><MapPin className="size-6 text-brand-600" />{t('map')}</h1>
          <p className="text-sm text-ink-500 dark:text-ink-400">{points.length} issue(s) shown · markers coloured by severity</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <select aria-label="Category" className="input !w-auto" value={category} onChange={e => setCategory(e.target.value)}>
            <option value="">{t('all_categories')}</option>
            {(meta?.categories ?? []).map(c => <option key={c}>{c}</option>)}
          </select>
          <select aria-label="Minimum severity" className="input !w-auto" value={minSev} onChange={e => setMinSev(Number(e.target.value))}>
            <option value={0}>{t('all_severities')}</option>
            {[3, 4, 5].map(s => <option key={s} value={s}>≥ {s} — {SEVERITY[s as 3].label}</option>)}
          </select>
          <button onClick={() => setHeat(h => !h)} className={`btn-secondary ${heat ? '!border-orange-400 !text-orange-600 dark:!text-orange-300' : ''}`}>
            <Flame className="size-4" />{heat ? t('markers') : t('heatmap')}
          </button>
        </div>
      </div>

      <div className="card mt-4 overflow-hidden">
        <IssueMap points={points} center={center} heatmap={heat} onMarkerClick={id => nav(`/reports/${id}`)}
          className="h-[70vh] min-h-96" />
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-x-5 gap-y-2 text-xs text-ink-500 dark:text-ink-400">
        <span className="font-semibold">Legend:</span>
        {Object.entries(SEVERITY).map(([k, v]) => (
          <span key={k} className="inline-flex items-center gap-1.5">
            <span className="size-3 rounded-full" style={{ background: v.color }} />{k} — {v.label}
          </span>
        ))}
      </div>
    </div>
  )
}
