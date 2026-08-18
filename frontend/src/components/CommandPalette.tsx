/* Ctrl/Cmd+K command palette — staff navigation without hunting through tabs. */
import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Search } from 'lucide-react'
import { useApp } from '../lib/store'

interface Cmd { label: string; hint?: string; to: string; roles?: string[] }

const COMMANDS: Cmd[] = [
  { label: 'Report an issue', to: '/report' },
  { label: 'Explore reports', to: '/reports' },
  { label: 'Issue map', to: '/map' },
  { label: 'Transparency portal', to: '/transparency' },
  { label: 'My settings', to: '/settings' },
  { label: 'Priority queue', to: '/priority', roles: ['admin', 'moderator', 'org_staff'] },
  { label: 'Organization portal', to: '/organization', roles: ['org_staff'] },
  { label: 'Admin: overview', to: '/dashboard', roles: ['admin', 'moderator'] },
  { label: 'Admin: Civic Briefing', hint: 'City Intelligence', to: '/dashboard?tab=intelligence', roles: ['admin', 'moderator'] },
  { label: 'Admin: AI review queue', to: '/dashboard?tab=aireview', roles: ['admin', 'moderator'] },
  { label: 'Admin: moderation center', to: '/dashboard?tab=moderation', roles: ['admin', 'moderator'] },
  { label: 'Admin: users', to: '/dashboard?tab=users', roles: ['admin', 'moderator'] },
  { label: 'Admin: background jobs', to: '/dashboard?tab=jobs', roles: ['admin', 'moderator'] },
  { label: 'Admin: audit log', to: '/dashboard?tab=audit', roles: ['admin', 'moderator'] },
]

export default function CommandPalette() {
  const { user } = useApp()
  const nav = useNavigate()
  const [open, setOpen] = useState(false)
  const [q, setQ] = useState('')
  const [sel, setSel] = useState(0)
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault()
        setOpen(o => !o); setQ(''); setSel(0)
      }
      if (e.key === 'Escape') setOpen(false)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])
  useEffect(() => { if (open) setTimeout(() => inputRef.current?.focus(), 50) }, [open])

  const items = useMemo(() => COMMANDS
    .filter(c => !c.roles || (user && c.roles.includes(user.role)))
    .filter(c => !q || c.label.toLowerCase().includes(q.toLowerCase())), [q, user])

  if (!open) return null
  return (
    <div className="fixed inset-0 z-[1300] bg-brand-950/40 p-4 pt-[12vh] backdrop-blur-sm animate-fade-in"
      onClick={() => setOpen(false)} role="dialog" aria-modal="true" aria-label="Command palette">
      <div className="mx-auto w-full max-w-lg overflow-hidden rounded-2xl border border-ink-200 bg-white shadow-2xl dark:border-white/10 dark:bg-ink-900 animate-pop"
        onClick={e => e.stopPropagation()}>
        <div className="flex items-center gap-2.5 border-b border-ink-100 px-4 dark:border-white/10">
          <Search className="size-4 text-ink-400" />
          <input ref={inputRef} value={q}
            onChange={e => { setQ(e.target.value); setSel(0) }}
            onKeyDown={e => {
              if (e.key === 'ArrowDown') { e.preventDefault(); setSel(s => Math.min(s + 1, items.length - 1)) }
              if (e.key === 'ArrowUp') { e.preventDefault(); setSel(s => Math.max(s - 1, 0)) }
              if (e.key === 'Enter' && items[sel]) { nav(items[sel].to); setOpen(false) }
            }}
            placeholder="Where to? (↑↓ + Enter)" aria-label="Command search"
            className="w-full bg-transparent py-3.5 text-sm outline-none placeholder:text-ink-400" />
          <kbd className="rounded border border-ink-200 px-1.5 py-0.5 text-[10px] text-ink-400 dark:border-white/15">esc</kbd>
        </div>
        <ul className="max-h-72 overflow-auto p-1.5" role="listbox">
          {items.length === 0 && <li className="px-3 py-6 text-center text-sm text-ink-400">Nothing matches.</li>}
          {items.map((c, i) => (
            <li key={c.to + c.label} role="option" aria-selected={i === sel}>
              <button onClick={() => { nav(c.to); setOpen(false) }} onMouseEnter={() => setSel(i)}
                className={`flex w-full items-center justify-between rounded-xl px-3 py-2.5 text-left text-sm ${i === sel ? 'bg-brand-50 text-brand-800 dark:bg-brand-400/10 dark:text-brand-200' : ''}`}>
                <span className="font-medium">{c.label}</span>
                {c.hint && <span className="text-xs text-ink-400">{c.hint}</span>}
              </button>
            </li>
          ))}
        </ul>
      </div>
    </div>
  )
}
