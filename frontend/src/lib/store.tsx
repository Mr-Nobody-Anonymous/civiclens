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

export function AppProvider({ children }: { children: ReactNode }) {
  const [user, setUserState] = useState<User | null>(() => {
    try { return JSON.parse(localStorage.getItem(USER_KEY) || 'null') } catch { return null }
  })
  const [authLoaded, setAuthLoaded] = useState(false)
  const [meta, setMeta] = useState<Meta | null>(null)
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
    api.get('/api/meta').then(setMeta).catch(() => {})
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