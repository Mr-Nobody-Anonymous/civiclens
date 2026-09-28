/* App-level context: auth session, theme, meta, toasts. */
import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react'
import { api } from './api'
import type { Meta, User } from './types'

interface Toast { id: number; kind: 'success' | 'error' | 'info'; msg: string }

interface AppState {
  user: User | null
  setUser: (u: User | null) => void
  meta: Meta | null
  dark: boolean
  toggleDark: () => void
  toast: (kind: Toast['kind'], msg: string) => void
  toasts: Toast[]
  authLoaded: boolean
}

const Ctx = createContext<AppState>(null as unknown as AppState)
let toastId = 0
const USER_KEY = 'cl_user'

/** Demo session: user was logged in via the static frontend's fallback (no backend). */
function isDemoUser(u: User | null): boolean {
  return !!u && u.id.startsWith('demo-')
}

const DEFAULT_META: Meta = {
  categories: [
    'Roads & Infrastructure',
    'Water & Sanitation',
    'Electricity & Power',
    'Waste Management',
    'Telecom',
    'Public Safety',
    'Traffic & Transport',
    'Environment & Green Spaces',
  ],
  cities: [
    'Addis Ababa',
    'Dire Dawa',
    'Hawassa',
    'Adama',
    'Bahir Dar',
    'Mekelle',
    'Gondar',
    'Jimma',
    'Dessie',
    'Bishoftu',
  ],
  default_center: { lat: 9.0108, lng: 38.7613 },
  statuses: [
    'submitted',
    'ai_analysis',
    'under_review',
    'assigned',
    'in_progress',
    'resolved',
    'rejected',
    'duplicate',
    'reopened',
  ],
  max_video_mb: 25,
  max_image_mb: 10,
}

export function AppProvider({ children }: { children: ReactNode }) {
  const [user, setUserState] = useState<User | null>(() => {
    try { return JSON.parse(localStorage.getItem(USER_KEY) || 'null') } catch { return null }
  })
  const [authLoaded, setAuthLoaded] = useState(false)
  const [meta, setMeta] = useState<Meta | null>(DEFAULT_META)
  const [toasts, setToasts] = useState<Toast[]>([])
  const [dark, setDark] = useState(() =>
    localStorage.getItem('cl_dark') === '1' ||
    (localStorage.getItem('cl_dark') === null && window.matchMedia('(prefers-color-scheme: dark)').matches))

  const setUser = useCallback((u: User | null) => {
    setUserState(u)
    if (u) localStorage.setItem(USER_KEY, JSON.stringify(u))
    else localStorage.removeItem(USER_KEY)
  }, [])

  useEffect(() => {
    document.documentElement.classList.toggle('dark', dark)
    localStorage.setItem('cl_dark', dark ? '1' : '0')
  }, [dark])

  useEffect(() => {
    // If we already have a persisted demo session, keep it — no backend to re-check.
    if (isDemoUser(user)) {
      setAuthLoaded(true)
      return
    }
    api.get('/api/auth/me').then(u => setUser(u)).catch(() => {}).finally(() => setAuthLoaded(true))
    api.get('/api/meta').then(setMeta).catch(() => setMeta(DEFAULT_META))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const toast = useCallback((kind: Toast['kind'], msg: string) => {
    const id = ++toastId
    setToasts(ts => [...ts, { id, kind, msg }])
    setTimeout(() => setToasts(ts => ts.filter(t => t.id !== id)), 4200)
  }, [])

  return (
    <Ctx.Provider value={{ user, setUser, meta, dark, toggleDark: () => setDark(d => !d), toast, toasts, authLoaded }}>
      {children}
    </Ctx.Provider>
  )
}

export const useApp = () => useContext(Ctx)