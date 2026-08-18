import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Eye, EyeOff, Loader2, LogIn, UserPlus } from 'lucide-react'
import { api, ApiError } from '../lib/api'
import { useApp } from '../lib/store'
import { useI18n } from '../lib/i18n'
import { LogoMark } from '../components/Logo'

export default function Login() {
  const { setUser, toast, meta } = useApp()
  const { t } = useI18n()
  const nav = useNavigate()
  const [mode, setMode] = useState<'login' | 'register' | 'forgot' | 'reset'>('login')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [name, setName] = useState('')
  const [city, setCity] = useState('Addis Ababa')
  const [resetToken, setResetToken] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [busy, setBusy] = useState(false)

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setBusy(true)
    try {
      if (mode === 'forgot') {
        await api.post('/api/auth/forgot-password', { email })
        toast('success', 'If that email has an account, a reset token was sent to it.')
        setMode('reset')
        return
      }
      if (mode === 'reset') {
        await api.post('/api/auth/reset-password', { token: resetToken.trim(), new_password: password })
        toast('success', 'Password reset. Sign in with your new password.')
        setPassword('')
        setMode('login')
        return
      }
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
    <div className="mx-auto grid max-w-4xl gap-0 px-4 py-10 lg:grid-cols-[1fr_1.1fr] lg:py-16">
      {/* brand panel */}
      <div className="relative hidden overflow-hidden rounded-l-3xl bg-gradient-to-br from-brand-800 via-brand-900 to-brand-950 p-10 text-white lg:flex lg:flex-col lg:justify-between">
        <div className="eth-dots absolute inset-0 opacity-30" aria-hidden />
        <div className="relative">
          <LogoMark size={56} variant="dark" />
          <h2 className="mt-6 text-2xl font-extrabold leading-snug tracking-tight">
            See it.<br />Report it.<br /><span className="text-gold-400">Improve it.</span>
          </h2>
          <p className="mt-4 max-w-xs text-sm leading-relaxed text-brand-100/75">
            One account to report civic issues, follow their progress and get notified when your city fixes them.
          </p>
        </div>
        <ul className="relative space-y-2 text-xs text-brand-100/70">
          <li>✓ Your identity is never shown publicly</li>
          <li>✓ AI-assisted triage, human-reviewed</li>
          <li>✓ English · አማርኛ</li>
        </ul>
      </div>

      <div className="card overflow-hidden !rounded-3xl lg:!rounded-l-none animate-fade-up">
        <div className="eth-strip h-1 lg:hidden" />
        <div className="p-7 md:p-9">
          <div className="mx-auto w-fit lg:hidden"><LogoMark size={44} /></div>
          <h1 className="mt-4 text-center text-2xl font-extrabold">
            {mode === 'login' ? t('login') : mode === 'register' ? t('register')
              : mode === 'forgot' ? t('forgot_password') : t('reset_password')}
          </h1>
          <p className="mt-1 text-center text-sm text-ink-500 dark:text-ink-400">
            {mode === 'login' ? 'Track your reports and get notified about progress.'
              : mode === 'register' ? 'One account for reporting, tracking and notifications.'
              : mode === 'forgot' ? 'Enter your email and we will send a reset token (check the console in development).'
              : 'Paste the reset token from your email and choose a new password.'}
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
            {mode !== 'reset' && (
              <div><label htmlFor="email" className="label">Email</label>
                <input id="email" type="email" className="input" required value={email} onChange={e => setEmail(e.target.value)} autoComplete="email" /></div>
            )}
            {mode === 'reset' && (
              <div><label htmlFor="token" className="label">Reset token</label>
                <input id="token" className="input font-mono" required value={resetToken} onChange={e => setResetToken(e.target.value)}
                  placeholder="Paste the token from the email" /></div>
            )}
            {mode !== 'forgot' && (
              <div>
                <label htmlFor="pw" className="label">{mode === 'reset' ? 'New password' : 'Password'}</label>
                <div className="relative">
                  <input id="pw" type={showPassword ? 'text' : 'password'} className="input pr-10" required
                    minLength={mode === 'login' ? 1 : 8} value={password} onChange={e => setPassword(e.target.value)}
                    autoComplete={mode === 'login' ? 'current-password' : 'new-password'} />
                  <button type="button" onClick={() => setShowPassword(s => !s)} aria-label={showPassword ? 'Hide password' : 'Show password'}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-ink-400 hover:text-ink-600 dark:text-ink-500 dark:hover:text-ink-300">
                    {showPassword ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
                  </button>
                </div>
                {(mode === 'register' || mode === 'reset') && <p className="mt-1 text-xs text-ink-500 dark:text-ink-400">At least 8 characters.</p>}
              </div>
            )}
            <button className="btn-primary w-full !py-3" disabled={busy}>
              {busy ? <Loader2 className="size-4 animate-spin" /> : mode === 'register' ? <UserPlus className="size-4" /> : <LogIn className="size-4" />}
              {mode === 'login' ? t('login') : mode === 'register' ? t('register')
                : mode === 'forgot' ? 'Send reset token' : t('reset_password')}
            </button>
          </form>

          {mode === 'login' && (
            <button onClick={() => setMode('forgot')}
              className="mt-3 w-full text-center text-sm font-medium text-ink-500 hover:underline dark:text-ink-400">
              {t('forgot_password')}
            </button>
          )}
          <button onClick={() => setMode(m => m === 'login' ? 'register' : 'login')}
            className="mt-2 w-full text-center text-sm font-semibold text-brand-700 hover:underline dark:text-brand-300">
            {mode === 'login' ? 'No account yet? Create one' : 'Back to sign in'}
          </button>
          {mode === 'forgot' && (
            <button onClick={() => setMode('reset')}
              className="mt-2 w-full text-center text-xs text-ink-500 hover:underline dark:text-ink-400">
              Already have a token? Enter it
            </button>
          )}

          <div className="mt-6 rounded-xl bg-ink-50 p-4 text-xs leading-relaxed text-ink-500 dark:bg-white/5 dark:text-ink-400">
            <p className="font-bold text-ink-600 dark:text-ink-300">Demo accounts</p>
            <p>admin@civiclens.et / admin12345 · moderator@civiclens.et / moderator123</p>
            <p>staff@ethiotelecom.et / telecom123 · staff@roads.et / roads12345 · citizen@example.et / citizen123</p>
          </div>
          <p className="mt-4 text-center text-xs text-ink-500 dark:text-ink-400">By continuing you accept our <Link to="/privacy" className="underline">privacy policy</Link>.</p>
        </div>
      </div>
    </div>
  )
}