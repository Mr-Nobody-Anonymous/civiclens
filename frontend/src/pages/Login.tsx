import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Eye, Loader2, LogIn, UserPlus } from 'lucide-react'
import { api, ApiError } from '../lib/api'
import { useApp } from '../lib/store'
import { useI18n } from '../lib/i18n'

export default function Login() {
  const { setUser, toast, meta } = useApp()
  const { t } = useI18n()
  const nav = useNavigate()
  const [mode, setMode] = useState<'login' | 'register'>('login')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [name, setName] = useState('')
  const [city, setCity] = useState('Addis Ababa')
  const [busy, setBusy] = useState(false)

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setBusy(true)
    try {
      const user = mode === 'login'
        ? await api.post('/api/auth/login', { email, password })
        : await api.post('/api/auth/register', { email, password, name, city })
      setUser(user)
      toast('success', `Welcome, ${user.name.split(' ')[0]}!`)
      nav(user.role === 'admin' || user.role === 'moderator' ? '/dashboard' : user.role === 'org_staff' ? '/organization' : '/')
    } catch (err) {
      toast('error', err instanceof ApiError ? err.message : 'Something went wrong')
    } finally { setBusy(false) }
  }

  return (
    <div className="mx-auto grid max-w-md px-4 py-12">
      <div className="card overflow-hidden animate-fade-up">
        <div className="eth-strip h-1" />
        <div className="p-7">
          <div className="mx-auto grid size-12 place-items-center rounded-2xl bg-brand-600 text-white shadow-lg shadow-brand-600/30"><Eye className="size-6" /></div>
          <h1 className="mt-4 text-center text-2xl font-extrabold">{mode === 'login' ? t('login') : t('register')}</h1>
          <p className="mt-1 text-center text-sm text-gray-500 dark:text-gray-400">
            {mode === 'login' ? 'Track your reports and get notified about progress.' : 'One account for reporting, tracking and notifications.'}
          </p>

          <form onSubmit={submit} className="mt-6 space-y-4">
            {mode === 'register' && (
              <>
                <div><label htmlFor="name" className="label">Full name</label>
                  <input id="name" className="input" required minLength={2} value={name} onChange={e => setName(e.target.value)} /></div>
                <div><label htmlFor="city" className="label">City</label>
                  <select id="city" className="input" value={city} onChange={e => setCity(e.target.value)}>
                    {(meta?.cities ?? ['Addis Ababa']).map(c => <option key={c}>{c}</option>)}
                  </select></div>
              </>
            )}
            <div><label htmlFor="email" className="label">Email</label>
              <input id="email" type="email" className="input" required value={email} onChange={e => setEmail(e.target.value)} autoComplete="email" /></div>
            <div><label htmlFor="pw" className="label">Password</label>
              <input id="pw" type="password" className="input" required minLength={8} value={password} onChange={e => setPassword(e.target.value)}
                autoComplete={mode === 'login' ? 'current-password' : 'new-password'} />
              {mode === 'register' && <p className="mt-1 text-xs text-gray-400">At least 8 characters.</p>}</div>
            <button className="btn-primary w-full !py-3" disabled={busy}>
              {busy ? <Loader2 className="size-4 animate-spin" /> : mode === 'login' ? <LogIn className="size-4" /> : <UserPlus className="size-4" />}
              {mode === 'login' ? t('login') : t('register')}
            </button>
          </form>

          <button onClick={() => setMode(m => m === 'login' ? 'register' : 'login')}
            className="mt-4 w-full text-center text-sm font-semibold text-brand-700 hover:underline dark:text-brand-300">
            {mode === 'login' ? "No account yet? Create one" : 'Already have an account? Sign in'}
          </button>

          <div className="mt-6 rounded-xl bg-gray-50 p-4 text-xs leading-relaxed text-gray-500 dark:bg-white/5 dark:text-gray-400">
            <p className="font-bold text-gray-600 dark:text-gray-300">Demo accounts</p>
            <p>admin@civiclens.et / admin12345 · moderator@civiclens.et / moderator123</p>
            <p>staff@ethiotelecom.et / telecom123 · staff@roads.et / roads12345 · citizen@example.et / citizen123</p>
          </div>
          <p className="mt-4 text-center text-xs text-gray-400">By continuing you accept our <Link to="/privacy" className="underline">privacy policy</Link>.</p>
        </div>
      </div>
    </div>
  )
}
