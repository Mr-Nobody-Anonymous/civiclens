import { Link } from 'react-router-dom'
import { Building2, Calendar, MapPin, PlayCircle } from 'lucide-react'
import type { Report } from '../lib/types'
import { apiUrl } from '../lib/api'
import { CATEGORY_ICONS } from '../lib/types'
import { DemoBadge, SeverityBadge, StatusBadge } from './ui'

export default function ReportCard({ r }: { r: Report }) {
  const video = r.media.find(m => m.kind === 'video' && m.has_thumb)
  const image = r.media.find(m => m.kind === 'image' && m.has_thumb)
  const thumb = video ?? image
  return (
    <Link to={`/reports/${r.id}`} className="card group flex h-full flex-col overflow-hidden transition-all duration-200 hover:-translate-y-1 focus-visible:outline-2 focus-visible:outline-brand-600" style={{ boxShadow: undefined }}>
      {thumb && (
        <div className="relative h-40 overflow-hidden bg-ink-100 dark:bg-white/5">
          <img src={apiUrl(`/api/reports/${r.id}/media/${thumb.id}/thumb`)} alt="" loading="lazy"
            className="h-full w-full object-cover transition-transform duration-300 group-hover:scale-105" />
          {video && <PlayCircle className="absolute inset-0 m-auto size-11 text-white drop-shadow-lg" />}
        </div>
      )}
      <div className="flex flex-1 flex-col p-5">
        <div className="flex items-center justify-between gap-2">
          <span className="inline-flex items-center gap-1.5 text-xs font-semibold text-ink-500 dark:text-ink-400">
            <span aria-hidden>{CATEGORY_ICONS[r.category ?? 'Other'] ?? '📋'}</span>{r.category ?? 'Uncategorised'}
          </span>
          <div className="flex items-center gap-1.5">{r.is_demo && <DemoBadge />}<SeverityBadge sev={r.severity} /></div>
        </div>
        <h3 className="mt-2 line-clamp-2 font-bold leading-snug group-hover:text-brand-700 dark:group-hover:text-brand-300">{r.title}</h3>
        <p className="mt-1.5 line-clamp-2 text-sm text-ink-500 dark:text-ink-400">{r.description}</p>
        <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1.5 text-xs text-ink-500 dark:text-ink-400">
          {(r.address || r.city) && <span className="inline-flex items-center gap-1"><MapPin className="size-3.5" />{r.address ? `${r.address.split(',')[0]}, ${r.city ?? ''}` : r.city}</span>}
          <span className="inline-flex items-center gap-1"><Calendar className="size-3.5" />{new Date(r.created_at).toLocaleDateString()}</span>
          {r.organization_name && <span className="inline-flex items-center gap-1"><Building2 className="size-3.5" />{r.organization_name}</span>}
        </div>
        <div className="mt-auto flex items-center justify-between pt-3">
          <StatusBadge status={r.status} />
          <span className="font-mono text-[11px] text-ink-500 dark:text-ink-400">{r.public_code}</span>
        </div>
      </div>
    </Link>
  )
}
