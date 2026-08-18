import { Link, NavLink, useLocation } from 'react-router-dom'
import { Bell, Globe, LogIn, Map as MapIcon, Megaphone, Moon, Settings, Sun, Home, FileText, LogOut } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { useApp } from '../lib/store'
import { useI18n, LANGS } from '../lib/i18n'
import { api, apiUrl } from '../lib/api'
import { Toasts } from './ui'
import CommandPalette from './CommandPalette'
import { LogoLockup } from './Logo'

const KIND_ICON: Record<string, string> = {
  received: '📥', analyzed: '🧠', assigned: '🏢', in_progress: '🔧',
  resolved: '✅', rejected: '📕', reopened: '🔁', duplicate: '🔗', password_reset: '🔑',
}

function NotificationBell() {
  const { user } = useApp()
  const [items, setItems] = useState<{ id: string; kind: string; title: string; body?: string; read: boolean; report_id?: string; created_at: string }[]>([])
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!user) return
    const load = () => api.get('/api/notifications').then(setItems).catch(() => {})
    load()
    // real-time push via SSE; 30s polling stays as fallback
    const es = new EventSource(apiUrl('/api/stream'), { withCredentials: true })
    es.addEventListener('notification', () => load())
    const iv = setInterval(load, 30000)
    return () => { es.close(); clearInterval(iv) }
  }, [user])
  useEffect(() => {
    const onDoc = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false) }
    document.addEventListener('mousedown', onDoc)
    return () => document.removeEventListener('mousedown', onDoc)
  }, [])
  if (!user) return null
  const unread = items.filter(i => !i.read).length
  return (
    <div className="relative" ref={ref}>
      <button aria-label={`Notifications${unread ? ` (${unread} unread)` : ''}`}
        onClick={() => { setOpen(o => !o); if (!open && unread) api.post('/api/notifications/read-all').then(() => setItems(i => i.map(x => ({ ...x, read: true })))) }}
        className="relative rounded-xl p-2 text-ink-600 hover:bg-ink-100 dark:text-ink-300 dark:hover:bg-white/10">
        <Bell className="size-5" />
        {unread > 0 && <span className="absolute -right-0.5 -top-0.5 grid size-4.5 min-w-4 place-items-center rounded-full bg-et-red px-1 text-[10px] font-bold text-white animate-pop">{unread}</span>}
      </button>
      {open && (
        <div className="absolute right-0 z-50 mt-2 max-h-[26rem] w-[21rem] overflow-auto rounded-2xl border border-ink-200 bg-white p-1.5 shadow-2xl dark:border-white/10 dark:bg-ink-900 animate-fade-up">
          <p className="px-3 pb-1 pt-2.5 text-[11px] font-bold uppercase tracking-widest text-ink-500 dark:text-ink-400">Notifications</p>
          {items.length === 0 && (
            <div className="px-4 py-8 text-center">
              <Bell className="mx-auto size-7 text-ink-300" />
              <p className="mt-2 text-sm text-ink-500">You're all caught up.</p>
            </div>
          )}
          {items.map(n => (
            <Link key={n.id} to={n.report_id ? `/reports/${n.report_id}` : '#'} onClick={() => setOpen(false)}
              className={`flex gap-3 rounded-xl px-3 py-2.5 hover:bg-ink-50 dark:hover:bg-white/5 ${!n.read ? 'bg-brand-50/60 dark:bg-brand-400/5' : ''}`}>
              <span className="mt-0.5 text-base" aria-hidden>{KIND_ICON[n.kind] ?? '🔔'}</span>
              <span className="min-w-0">
                <span className="block truncate text-sm font-semibold">{n.title}</span>
                {n.body && <span className="mt-0.5 line-clamp-2 block text-xs text-ink-500 dark:text-ink-400">{n.body}</span>}
                <span className="mt-0.5 block text-[10px] text-ink-500 dark:text-ink-400">{new Date(n.created_at).toLocaleString()}</span>
              </span>
            </Link>
          ))}
        </div>
      )}
    </div>
  )
}

export default function Layout({ children }: { children: React.ReactNode }) {
  const { user, setUser, dark, toggleDark, toast } = useApp()
  const { t, lang, setLang } = useI18n()
  const loc = useLocation()

  const nav = [
    { to: '/reports', label: t('reports'), show: true },
    { to: '/map', label: t('map'), show: true },
    { to: '/priority', label: t('priority'), show: !!user && ['admin', 'moderator', 'org_staff'].includes(user.role) },
    { to: '/dashboard', label: t('admin'), show: !!user && ['admin', 'moderator'].includes(user.role) },
    { to: '/organization', label: t('organization'), show: !!user && user.role === 'org_staff' },
  ].filter(n => n.show)

  const logout = async () => {
    await api.post('/api/auth/logout')
    setUser(null)
    toast('info', 'Signed out')
  }

  return (
    <div className="flex min-h-screen flex-col" data-lang={lang}>
      <div className="eth-strip h-[3px] w-full" aria-hidden />
      <header className="sticky top-0 z-[1000] border-b border-ink-200/60 bg-white/85 backdrop-blur-xl dark:border-white/10 dark:bg-ink-950/85">
        <div className="mx-auto flex h-16 max-w-7xl items-center justify-between gap-3 px-4">
          <Link to="/" aria-label="CivicLens Ethiopia home" className="shrink-0"><LogoLockup /></Link>

          <nav className="hidden items-center gap-0.5 md:flex" aria-label="Main">
            {nav.map(n => (
              <NavLink key={n.to} to={n.to} className={({ isActive }) =>
                `rounded-xl px-3.5 py-2 text-sm font-medium transition ${isActive
                  ? 'bg-brand-600/10 text-brand-700 dark:bg-brand-400/15 dark:text-brand-300'
                  : 'text-ink-600 hover:bg-ink-100 hover:text-ink-900 dark:text-ink-300 dark:hover:bg-white/10 dark:hover:text-white'}`}>
                {n.label}
              </NavLink>
            ))}
          </nav>

          <div className="flex items-center gap-1">
            <button aria-label={`Switch language to ${LANGS.find(l => l.code !== lang)?.label}`} onClick={() => setLang(lang === 'en' ? 'am' : 'en')}
              className="flex items-center gap-1.5 rounded-xl px-2.5 py-2 text-sm font-semibold text-ink-600 hover:bg-ink-100 dark:text-ink-300 dark:hover:bg-white/10">
              <Globe className="size-4" /><span className="max-[420px]:hidden">{LANGS.find(l => l.code !== lang)?.label}</span>
            </button>
            <button aria-label="Toggle dark mode" onClick={toggleDark} className="rounded-xl p-2 text-ink-600 hover:bg-ink-100 dark:text-ink-300 dark:hover:bg-white/10">
              {dark ? <Sun className="size-5" /> : <Moon className="size-5" />}
            </button>
            <NotificationBell />
            {user ? (
              <div className="flex items-center gap-1">
                <Link to="/settings" aria-label={t('settings')} className="rounded-xl p-2 text-ink-600 hover:bg-ink-100 max-sm:hidden dark:text-ink-300 dark:hover:bg-white/10"><Settings className="size-5" /></Link>
                <button onClick={logout} aria-label={t('logout')} className="hidden items-center gap-1.5 rounded-xl px-3 py-2 text-sm font-medium text-ink-600 hover:bg-ink-100 sm:flex dark:text-ink-300 dark:hover:bg-white/10"><LogOut className="size-4" /></button>
                <span className="hidden lg:grid size-8 shrink-0 place-items-center rounded-full bg-gradient-to-br from-brand-500 to-brand-700 text-xs font-bold text-white" title={user.name}>{user.name.slice(0, 1)}</span>
              </div>
            ) : (
              <Link to="/login" className="btn-secondary !py-2 max-sm:hidden"><LogIn className="size-4" />{t('login')}</Link>
            )}
            <Link to="/report" className="btn-primary !py-2 max-sm:hidden"><Megaphone className="size-4" />{t('report_issue')}</Link>
          </div>
        </div>
      </header>

      <main key={loc.pathname} className="flex-1 pb-24 md:pb-10 animate-fade-in">{children}</main>

      <footer className="hidden border-t border-ink-200/60 bg-white py-10 md:block dark:border-white/10 dark:bg-transparent">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-4 px-4">
          <LogoLockup size={30} />
          <div className="flex flex-wrap items-center gap-x-6 gap-y-2 text-sm text-ink-500 dark:text-ink-400">
            <Link to="/reports" className="hover:text-brand-700 dark:hover:text-brand-300">{t('reports')}</Link>
            <Link to="/map" className="hover:text-brand-700 dark:hover:text-brand-300">{t('map')}</Link>
            <Link to="/transparency" className="hover:text-brand-700 dark:hover:text-brand-300">Transparency</Link>
            <Link to="/privacy" className="hover:text-brand-700 dark:hover:text-brand-300">{t('privacy')}</Link>
            <a href="/docs" target="_blank" rel="noreferrer" className="hover:text-brand-700 dark:hover:text-brand-300">API</a>
            <span className="text-ink-500 dark:text-ink-400">© {new Date().getFullYear()} CivicLens Ethiopia</span>
          </div>
        </div>
      </footer>

      {/* Mobile bottom navigation */}
      <nav aria-label="Mobile" className="fixed inset-x-0 bottom-0 z-[1000] border-t border-ink-200/70 bg-white/95 backdrop-blur-xl md:hidden dark:border-white/10 dark:bg-ink-950/95">
        <div className="grid grid-cols-5">
          {[
            { to: '/', label: t('home'), icon: Home },
            { to: '/reports', label: t('reports'), icon: FileText },
            { to: '/report', label: '', icon: Megaphone, primary: true },
            { to: '/map', label: t('map'), icon: MapIcon },
            user ? { to: '/settings', label: t('settings'), icon: Settings } : { to: '/login', label: t('login'), icon: LogIn },
          ].map((n, i) => n.primary ? (
            <Link key={i} to={n.to} aria-label={t('report_issue')} className="relative -mt-6 flex justify-center">
              <span className="grid size-14 place-items-center rounded-full bg-gradient-to-br from-brand-500 to-brand-700 text-white shadow-pop transition active:scale-95" style={{ boxShadow: '0 8px 24px -6px rgb(12 125 72 / .55)' }}>
                <Megaphone className="size-6" />
              </span>
            </Link>
          ) : (
            <NavLink key={i} to={n.to} className={({ isActive }) =>
              `flex flex-col items-center gap-0.5 py-2.5 text-[10px] font-medium ${isActive ? 'text-brand-600 dark:text-brand-400' : 'text-ink-500 dark:text-ink-400'}`}>
              <n.icon className="size-5" />{n.label}
            </NavLink>
          ))}
        </div>
      </nav>
      <CommandPalette />
      <Toasts />
    </div>
  )
}
