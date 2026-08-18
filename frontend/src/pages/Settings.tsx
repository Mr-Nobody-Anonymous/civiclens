import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Bell, BellRing, Globe, Save, Trash2, UserRound } from 'lucide-react'
import { api } from '../lib/api'
import { useApp } from '../lib/store'
import { useI18n, LANGS } from '../lib/i18n'
import { ConfirmDialog } from '../components/ui'
import { getPushState, subscribePush, unsubscribePush, sendTestPush, type PushState } from '../lib/push'

function PushToggle() {
  const { toast } = useApp()
  const [state, setState] = useState<PushState | 'loading'>('loading')
  const [busy, setBusy] = useState(false)
  useEffect(() => { getPushState().then(setState).catch(() => setState('unsupported')) }, [])

  if (state === 'loading') return <div className="skeleton h-12" />
  if (state === 'unsupported') return (
    <p className="text-sm text-ink-500 dark:text-ink-400">Push notifications are not supported by this browser.</p>)
  if (state === 'server-disabled') return (
    <p className="text-sm text-ink-500 dark:text-ink-400">Push notifications are not configured on this server (administrator: set CL_VAPID_* keys).</p>)
  if (state === 'denied') return (
    <p className="text-sm text-ink-500 dark:text-ink-400">Notifications are blocked in your browser settings for this site.</p>)

  const on = state === 'subscribed'
  return (
    <div className="space-y-2">
      <label className="flex items-center justify-between gap-3 rounded-xl border border-ink-200 px-4 py-3.5 dark:border-white/10">
        <span className="flex items-center gap-2.5 text-sm font-medium">
          <BellRing className="size-4.5 text-brand-600" />Push notifications on this device
        </span>
        <input type="checkbox" checked={on} disabled={busy} className="size-5 accent-brand-600"
          aria-label="Push notifications on this device"
          onChange={async e => {
            setBusy(true)
            try {
              if (e.target.checked) { await subscribePush(); setState('subscribed'); toast('success', 'Push notifications enabled on this device') }
              else { await unsubscribePush(); setState('unsubscribed'); toast('info', 'Push notifications disabled') }
            } catch (err) { toast('error', (err as Error).message || 'Could not update push subscription') }
            finally { setBusy(false) }
          }} />
      </label>
      {on && (
        <button className="btn-ghost !py-1.5 !text-xs" disabled={busy} onClick={async () => {
          setBusy(true)
          try { const n = await sendTestPush(); toast(n > 0 ? 'success' : 'info', n > 0 ? `Test sent to ${n} device${n > 1 ? 's' : ''}` : 'No deliveries — try re-enabling') }
          catch (err) { toast('error', (err as Error).message) }
          finally { setBusy(false) }
        }}>Send a test notification</button>
      )}
    </div>
  )
}

function NotifPrefs() {
  const { toast } = useApp()
  const [prefs, setPrefs] = useState<Record<string, boolean> | null>(null)
  useEffect(() => { api.get('/api/notification-preferences').then(setPrefs).catch(() => {}) }, [])
  if (!prefs) return <div className="skeleton h-24" />
  const LABELS: Record<string, string> = {
    status_changes: 'Report status changes', organization_response: 'Organization responses',
    resolution: 'Resolutions', reopened: 'Reopened reports',
    followed_updates: 'Updates on things I follow', email_important: 'Email for important updates',
  }
  return (
    <div className="space-y-2">
      {Object.entries(LABELS).map(([k, label]) => (
        <label key={k} className="flex items-center justify-between gap-3 rounded-xl border border-ink-200 px-4 py-2.5 text-sm dark:border-white/10">
          {label}
          <input type="checkbox" className="size-4.5 accent-brand-600" checked={prefs[k] ?? true}
            onChange={async e => {
              const next = { ...prefs, [k]: e.target.checked }
              setPrefs(next)
              try { await api.put('/api/notification-preferences', { prefs: next }) }
              catch { toast('error', 'Could not save preference') }
            }} />
        </label>
      ))}
    </div>
  )
}

export default function Settings() {
  const { user, setUser, meta, toast } = useApp()
  const { setLang } = useI18n()
  const nav = useNavigate()
  const [name, setName] = useState(user?.name ?? '')
  const [city, setCity] = useState(user?.city ?? 'Addis Ababa')
  const [language, setLanguage] = useState(user?.language ?? 'en')
  const [emailNotif, setEmailNotif] = useState(user?.email_notifications ?? true)
  const [delOpen, setDelOpen] = useState(false)
  const [curPw, setCurPw] = useState('')
  const [newPw, setNewPw] = useState('')

  if (!user) return (
    <div className="mx-auto max-w-md px-4 py-20 text-center">
      <UserRound className="mx-auto size-10 text-ink-300" />
      <h1 className="mt-3 text-xl font-bold">Sign in to manage settings</h1>
      <Link to="/login" className="btn-primary mt-5">Sign in</Link>
    </div>
  )

  const save = async () => {
    try {
      const u = await api.patch('/api/auth/settings', { name, city, language, email_notifications: emailNotif })
      setUser(u); setLang(language)
      toast('success', 'Settings saved')
    } catch (e) { toast('error', (e as Error).message) }
  }

  return (
    <div className="mx-auto max-w-xl px-4 py-8">
      <h1 className="text-2xl font-extrabold">Settings</h1>
      <p className="mt-1 text-sm text-ink-500">{user.email} · role: <b>{user.role}</b>{user.organization_name ? ` · ${user.organization_name}` : ''}</p>

      <div className="card mt-6 space-y-5 p-6">
        <div><label className="label" htmlFor="name">Full name</label>
          <input id="name" className="input" value={name} onChange={e => setName(e.target.value)} /></div>
        <div><label className="label" htmlFor="city">City</label>
          <select id="city" className="input" value={city} onChange={e => setCity(e.target.value)}>
            {(meta?.cities ?? ['Addis Ababa']).map(c => <option key={c}>{c}</option>)}
          </select></div>
        <div><label className="label" htmlFor="lang"><Globe className="mr-1 inline size-4" />Language</label>
          <select id="lang" className="input" value={language} onChange={e => setLanguage(e.target.value)}>
            {LANGS.map(l => <option key={l.code} value={l.code}>{l.label}</option>)}
          </select></div>
        <label className="flex items-center justify-between gap-3 rounded-xl border border-ink-200 px-4 py-3.5 dark:border-white/10">
          <span className="flex items-center gap-2.5 text-sm font-medium"><Bell className="size-4.5 text-brand-600" />Email notifications about my reports</span>
          <input type="checkbox" checked={emailNotif} onChange={e => setEmailNotif(e.target.checked)} className="size-5 accent-brand-600" />
        </label>
        <button className="btn-primary w-full" onClick={save}><Save className="size-4" />Save changes</button>
      </div>

      <div className="card mt-5 space-y-3 p-6">
        <h2 className="font-bold">Notification preferences</h2>
        <NotifPrefs />
        <PushToggle />
      </div>

      <div className="card mt-5 space-y-4 p-6">
        <h2 className="font-bold">Security</h2>
        <div className="grid gap-3 sm:grid-cols-2">
          <div><label className="label" htmlFor="curpw">Current password</label>
            <input id="curpw" type="password" className="input" value={curPw} onChange={e => setCurPw(e.target.value)} autoComplete="current-password" /></div>
          <div><label className="label" htmlFor="newpw">New password</label>
            <input id="newpw" type="password" className="input" value={newPw} onChange={e => setNewPw(e.target.value)} autoComplete="new-password" minLength={8} /></div>
        </div>
        <div className="flex flex-wrap gap-2">
          <button className="btn-primary" disabled={!curPw || newPw.length < 8} onClick={async () => {
            try {
              await api.post('/api/auth/change-password', { current_password: curPw, new_password: newPw })
              setCurPw(''); setNewPw('')
              toast('success', 'Password changed. Other sessions were signed out.')
            } catch (e) { toast('error', (e as Error).message) }
          }}>Change password</button>
          <button className="btn-secondary" onClick={async () => {
            try { await api.post('/api/auth/logout-all'); setUser(null); toast('info', 'Signed out everywhere.'); nav('/login') }
            catch (e) { toast('error', (e as Error).message) }
          }}>Sign out of all devices</button>
        </div>
      </div>

      <div className="card mt-5 border-red-200 p-6 dark:border-red-500/30">
        <h2 className="font-bold text-et-red">Danger zone</h2>
        <p className="mt-1 text-sm text-ink-500">Deleting your account anonymises your reports and removes your personal data. This cannot be undone.</p>
        <button className="btn-danger mt-4" onClick={() => setDelOpen(true)}><Trash2 className="size-4" />Delete my account</button>
      </div>

      <ConfirmDialog open={delOpen} onClose={() => setDelOpen(false)} danger title="Delete account?"
        body="Your personal data will be removed and your reports anonymised. This action is permanent."
        confirmLabel="Delete forever"
        onConfirm={async () => {
          try { await api.delete('/api/auth/me'); setUser(null); toast('info', 'Account deleted.'); nav('/') }
          catch (e) { toast('error', (e as Error).message) }
        }} />
    </div>
  )
}
