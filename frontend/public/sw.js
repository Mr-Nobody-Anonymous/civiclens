/* CivicLens Ethiopia — service worker.
 *
 * 1. PWA app-shell caching: precache the SPA entry, serve navigations
 *    cache-first-then-network so the app opens offline (the in-app offline
 *    queue in lib/offline.ts handles report submission).
 * 2. Runtime caching: hashed /assets/* are cached forever (immutable names);
 *    API responses are NEVER cached (auth/privacy).
 * 3. Web Push: shows notifications and focuses/opens the right report page.
 */
const VERSION = 'cl-v1'
const SHELL = ['/', '/index.html', '/manifest.webmanifest', '/favicon.svg']

self.addEventListener('install', (e) => {
  e.waitUntil(caches.open(VERSION).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()))
})

self.addEventListener('activate', (e) => {
  e.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== VERSION).map((k) => caches.delete(k))))
      .then(() => self.clients.claim()),
  )
})

self.addEventListener('fetch', (e) => {
  const url = new URL(e.request.url)
  if (e.request.method !== 'GET') return                 // never touch mutations
  if (url.pathname.startsWith('/api/')) return           // never cache API (auth/privacy)

  // Immutable hashed assets: cache-first
  if (url.pathname.startsWith('/assets/')) {
    e.respondWith(
      caches.match(e.request).then((hit) => hit || fetch(e.request).then((res) => {
        const copy = res.clone()
        caches.open(VERSION).then((c) => c.put(e.request, copy))
        return res
      })),
    )
    return
  }

  // SPA navigations: network-first, fall back to cached shell when offline
  if (e.request.mode === 'navigate') {
    e.respondWith(
      fetch(e.request)
        .then((res) => {
          const copy = res.clone()
          caches.open(VERSION).then((c) => c.put('/index.html', copy))
          return res
        })
        .catch(() => caches.match('/index.html')),
    )
  }
})

// ---- Web Push ----
self.addEventListener('push', (e) => {
  let data = {}
  try { data = e.data ? e.data.json() : {} } catch { /* noop */ }
  const title = data.title || 'CivicLens'
  e.waitUntil(self.registration.showNotification(title, {
    body: data.body || '',
    icon: '/brand/mark.svg',
    badge: '/favicon.svg',
    tag: data.report_id || 'civiclens',
    data: { url: data.url || '/notifications' },
  }))
})

self.addEventListener('notificationclick', (e) => {
  e.notification.close()
  const target = (e.notification.data && e.notification.data.url) || '/'
  e.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true }).then((list) => {
      for (const c of list) {
        if ('focus' in c) { c.navigate(target); return c.focus() }
      }
      return clients.openWindow(target)
    }),
  )
})
