import { Link, NavLink, useLocation } from 'react-router-dom'
import { Bell, Eye, Globe, LayoutDashboard, ListOrdered, LogIn, Map as MapIcon, Megaphone, Moon, Building2, Settings, Sun, Home, FileText } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useApp } from '../lib/store'
import { useI18n, LANGS } from '../lib/i18n'
import { api } from '../lib/api'
import { Toasts } from './ui'

function Logo() {
  return (
    <Link to="/" className="flex items-center gap-2.5 font-extrabold tracking-tight">
      <span className="relative grid size-9 place-items-center overflow-hidden rounded-xl bg-brand-600 text-white shadow-lg shadow-brand-600/30">
        <Eye className="size-5" />
        <span className="eth-strip absolute inset-x-0 bottom-0 h-1" />
      </span>
      <span className="text-lg">CivicLens <span className="text-brand-600 dark:text-brand-400">Ethiopia</span></span>
    </Link>
  )
}

function NotificationBell() {
  const { user } = useApp()
  const [items, setItems] = useState<{ id: string; title: string; body?: string; read: boolean; report_id?: string; created_at: string }[]>([])
  const [open, setOpen] = useState(false)
  useEffect(() => {
    if (!user) return
    const load = () => api.get('/api/notifications').then(setItems).catch(() => {})
    load()
    const iv = setInterval(load, 30000)
    return () => clearInterval(iv)
  }, [user])
  if (!user) return null
  const unread = items.filter(i => !i.read).length
  return (
    <div className="relative">
      <button aria-label="Notifications" onClick={() => { setOpen(o => !o); if (!open && unread) api.post('/api/notifications/read-all').then(() => setItems(i => i.map(x => ({ ...x, read: true })))) }}
        className="relative rounded-xl p-2 hover:bg-gray-100 dark:hover:bg-white/10">
        <Bell className="size-5" />
        {unread > 0 && <span className="absolute -right-0.5 -top-0.5 grid size-4.5 min-w-4 place-items-center rounded-full bg-et-red px-1 text-[10px] font-bold text-white">{unread}</span>}
      </button>
      {open && (
        <div className="absolute right-0 z-50 mt-2 max-h-96 w-80 overflow-auto rounded-2xl border border-gray-200 bg-white p-2 shadow-2xl dark:border-white/10 dark:bg-gray-900 animate-fade-up">
          {items.length === 0 && <p className="p-4 text-sm text-gray-500">No notifications yet.</p>}
          {items.map(n => (
            <Link key={n.id} to={n.report_id ? `/reports/${n.report_id}` : '#'} onClick={() => setOpen(false)}
              className="block rounded-xl p-3 hover:bg-gray-50 dark:hover:bg-white/5">
              <p className="text-sm font-semibold">{n.title}</p>
              {n.body && <p className="mt-0.5 line-clamp-2 text-xs text-gray-500 dark:text-gray-400">{n.body}</p>}
              <p className="mt-1 text-[10px] text-gray-400">{new Date(n.created_at).toLocaleString()}</p>
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
    { to: '/', label: t('home'), icon: Home, show: true },
    { to: '/reports', label: t('reports'), icon: FileText, show: true },
    { to: '/map', label: t('map'), icon: MapIcon, show: true },
    { to: '/priority', label: t('priority'), icon: ListOrdered, show: !!user && ['admin', 'moderator', 'org_staff'].includes(user.role) },
    { to: '/dashboard', label: t('admin'), icon: LayoutDashboard, show: !!user && ['admin', 'moderator'].includes(user.role) },
    { to: '/organization', label: t('organization'), icon: Building2, show: !!user && user.role === 'org_staff' },
  ].filter(n => n.show)

  const logout = async () => {
    await api.post('/api/auth/logout')
    setUser(null)
    toast('info', 'Signed out')
  }

  return (
    <div className="flex min-h-screen flex-col">
      <div className="eth-strip h-1 w-full" aria-hidden />
      <header className="sticky top-0 z-[1000] border-b border-gray-200/70 bg-white/85 backdrop-blur-lg dark:border-white/10 dark:bg-[#0b1210]/85">
        <div className="mx-auto flex h-16 max-w-7xl items-center justify-between gap-3 px-4">
          <Logo />
          <nav className="hidden items-center gap-1 md:flex" aria-label="Main">
            {nav.map(n => (
              <NavLink key={n.to} to={n.to} className={({ isActive }) =>
                `rounded-xl px-3.5 py-2 text-sm font-medium transition ${isActive ? 'bg-brand-600/10 text-brand-700 dark:bg-brand-400/10 dark:text-brand-300' : 'text-gray-600 hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-white/10'}`}>
                {n.label}
              </NavLink>
            ))}
          </nav>
          <div className="flex items-center gap-1.5">
            <button aria-label="Language" onClick={() => setLang(lang === 'en' ? 'am' : 'en')}
              className="flex items-center gap-1.5 rounded-xl px-2.5 py-2 text-sm font-semibold hover:bg-gray-100 dark:hover:bg-white/10">
              <Globe className="size-4" />{LANGS.find(l => l.code !== lang)?.label}
            </button>
            <button aria-label="Toggle dark mode" onClick={toggleDark} className="rounded-xl p-2 hover:bg-gray-100 dark:hover:bg-white/10">
              {dark ? <Sun className="size-5" /> : <Moon className="size-5" />}
            </button>
            <NotificationBell />
            {user ? (
              <div className="flex items-center gap-1.5">
                <Link to="/settings" aria-label={t('settings')} className="rounded-xl p-2 hover:bg-gray-100 dark:hover:bg-white/10"><Settings className="size-5" /></Link>
                <button onClick={logout} className="hidden rounded-xl px-3 py-2 text-sm font-medium text-gray-600 hover:bg-gray-100 sm:block dark:text-gray-300 dark:hover:bg-white/10">{t('logout')}</button>
                <span className="hidden lg:grid size-8 place-items-center rounded-full bg-brand-600 text-xs font-bold text-white" title={user.name}>{user.name.slice(0, 1)}</span>
              </div>
            ) : (
              <Link to="/login" className="btn-secondary !py-2"><LogIn className="size-4" />{t('login')}</Link>
            )}
            <Link to="/report" className="btn-primary !py-2 max-sm:hidden"><Megaphone className="size-4" />{t('report_issue')}</Link>
          </div>
        </div>
      </header>

      <main key={loc.pathname} className="flex-1 pb-24 md:pb-10 animate-fade-in">{children}</main>

      <footer className="hidden border-t border-gray-200 py-8 text-center text-sm text-gray-500 md:block dark:border-white/10 dark:text-gray-400">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-center gap-x-6 gap-y-2 px-4">
          <span>© {new Date().getFullYear()} CivicLens Ethiopia — civic reporting for Ethiopian cities</span>
          <Link to="/privacy" className="font-medium text-brand-700 hover:underline dark:text-brand-300">{t('privacy')}</Link>
          <a href="/docs" target="_blank" rel="noreferrer" className="font-medium text-brand-700 hover:underline dark:text-brand-300">API Docs</a>
        </div>
      </footer>

      {/* Mobile bottom navigation */}
      <nav aria-label="Mobile" className="fixed inset-x-0 bottom-0 z-[1000] border-t border-gray-200 bg-white/95 backdrop-blur-lg md:hidden dark:border-white/10 dark:bg-[#0b1210]/95">
        <div className="grid grid-cols-5">
          {[
            { to: '/', label: t('home'), icon: Home },
            { to: '/reports', label: t('reports'), icon: FileText },
            { to: '/report', label: '', icon: Megaphone, primary: true },
            { to: '/map', label: t('map'), icon: MapIcon },
            user ? { to: '/settings', label: t('settings'), icon: Settings } : { to: '/login', label: t('login'), icon: LogIn },
          ].map((n, i) => n.primary ? (
            <Link key={i} to={n.to} aria-label={t('report_issue')} className="relative -mt-5 flex justify-center">
              <span className="grid size-14 place-items-center rounded-full bg-brand-600 text-white shadow-xl shadow-brand-600/40 transition active:scale-95">
                <Megaphone className="size-6" />
              </span>
            </Link>
          ) : (
            <NavLink key={i} to={n.to} className={({ isActive }) =>
              `flex flex-col items-center gap-0.5 py-2.5 text-[10px] font-medium ${isActive ? 'text-brand-600 dark:text-brand-400' : 'text-gray-500 dark:text-gray-400'}`}>
              <n.icon className="size-5" />{n.label}
            </NavLink>
          ))}
        </div>
      </nav>
      <Toasts />
    </div>
  )
}
