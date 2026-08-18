export interface User {
  id: string; name: string; email: string; role: string; language: string
  city?: string | null; email_notifications: boolean
  organization_id?: string | null; organization_name?: string | null
}

export interface MediaItem {
  id: string; kind: string; content_type?: string; size_bytes?: number
  duration_s?: number; has_thumb: boolean; created_at: string
}

export interface AIAnalysis {
  category?: string; issue_type?: string; severity?: number; confidence?: number
  confidence_band?: 'high' | 'medium' | 'low'
  urgency?: string; responsible_organization?: string; organization_type?: string
  reasoning?: string; model_name?: string; model_version?: string
  analyzer?: string; input_kind?: string; duration_ms?: number; success?: boolean
  frames_analyzed?: number; corrected: boolean; created_at?: string
}

export interface Report {
  id: string; public_code: string; title: string; description: string
  category?: string; issue_type?: string; severity?: number; status: string
  city?: string; latitude?: number; longitude?: number; address?: string
  organization_name?: string; is_demo: boolean; created_at: string
  resolved_at?: string; media: MediaItem[]; ai?: AIAnalysis | null
  duplicate_of_code?: string | null; possible_duplicate?: boolean
  reporter_name?: string; reporter_email?: string; comments?: string
  is_flagged?: boolean; flag_reason?: string; user_category?: string
  history?: { to_status: string; note?: string | null; created_at: string }[]
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  comments_list?: any[]
}

export interface Meta {
  categories: string[]; cities: string[]
  default_center: { lat: number; lng: number }
  statuses: string[]; max_video_mb: number; max_image_mb: number
}

export const SEVERITY = {
  1: { label: 'Minor', label_am: 'ጥቃቅን', color: '#6b7280', bg: 'bg-ink-100 text-ink-700 dark:bg-ink-500/15 dark:text-ink-300' },
  2: { label: 'Low', label_am: 'ዝቅተኛ', color: '#3b82f6', bg: 'bg-blue-100 text-blue-700 dark:bg-blue-500/15 dark:text-blue-300' },
  3: { label: 'Moderate', label_am: 'መካከለኛ', color: '#eab308', bg: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-500/15 dark:text-yellow-300' },
  4: { label: 'Serious', label_am: 'ከባድ', color: '#f97316', bg: 'bg-orange-100 text-orange-700 dark:bg-orange-500/15 dark:text-orange-300' },
  5: { label: 'Critical', label_am: 'እጅግ አሳሳቢ', color: '#dc2626', bg: 'bg-red-100 text-red-700 dark:bg-red-500/15 dark:text-red-300' },
} as const

export const STATUS_META: Record<string, { label: string; label_am: string; cls: string }> = {
  submitted: { label: 'Submitted', label_am: 'ገብቷል', cls: 'bg-ink-100 text-ink-700 dark:bg-ink-500/15 dark:text-ink-300' },
  ai_analysis: { label: 'AI Analysis', label_am: 'AI ትንተና', cls: 'bg-violet-100 text-violet-700 dark:bg-violet-500/15 dark:text-violet-300' },
  under_review: { label: 'Under Review', label_am: 'በግምገማ ላይ', cls: 'bg-amber-100 text-amber-800 dark:bg-amber-500/15 dark:text-amber-300' },
  assigned: { label: 'Assigned', label_am: 'ተመድቧል', cls: 'bg-sky-100 text-sky-700 dark:bg-sky-500/15 dark:text-sky-300' },
  in_progress: { label: 'In Progress', label_am: 'በሂደት ላይ', cls: 'bg-indigo-100 text-indigo-700 dark:bg-indigo-500/15 dark:text-indigo-300' },
  resolved: { label: 'Resolved', label_am: 'ተፈትቷል', cls: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-300' },
  rejected: { label: 'Rejected', label_am: 'ውድቅ ተደርጓል', cls: 'bg-rose-100 text-rose-700 dark:bg-rose-500/15 dark:text-rose-300' },
  duplicate: { label: 'Duplicate', label_am: 'ተደጋጋሚ', cls: 'bg-ink-100 text-ink-500 dark:bg-ink-500/15 dark:text-ink-400' },
  reopened: { label: 'Reopened', label_am: 'እንደገና ተከፍቷል', cls: 'bg-amber-100 text-amber-800 dark:bg-amber-500/15 dark:text-amber-300' },
}

export const CATEGORY_ICONS: Record<string, string> = {
  'Roads & Transportation': '🛣️', 'Garbage & Sanitation': '🗑️', Water: '💧',
  Electricity: '⚡', Telecom: '📡', Education: '🏫', 'Public Buildings': '🏛️',
  Safety: '⚠️', Environment: '🌿', Other: '📋',
}
