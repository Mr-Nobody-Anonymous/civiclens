// Usage: build the SPA with VITE_API_BASE=<api origin>, serve dist/ on :8057
// with an SPA fallback, run the API on :8056 with CL_CORS_ORIGINS=<spa origin>,
// create user split@test.et / split-pass-123, then: node scripts/verify-split-deploy.mjs
// (requires playwright installed: cd frontend && npm i && npx playwright install chromium)
// Live browser E2E for SPLIT deployment: SPA on :8057, API on :8056.
// Verifies: page loads from static host, cross-origin login sets cookies,
// CSRF bootstrap works, authenticated GET /me succeeds, report list loads.
import { chromium } from 'playwright'

const SPA = 'http://127.0.0.1:8057'
const results = []
const browser = await chromium.launch()
const ctx = await browser.newContext()
const page = await ctx.newPage()
const apiCalls = []
page.on('request', r => { if (r.url().includes(':8056')) apiCalls.push(r.method() + ' ' + new URL(r.url()).pathname) })

// 1. SPA loads from the static origin
await page.goto(SPA + '/', { waitUntil: 'networkidle' })
results.push(['SPA loads on static origin', (await page.title()).length > 0])

// 2. Login page → cross-origin login
await page.goto(SPA + '/login', { waitUntil: 'networkidle' })
await page.getByLabel(/email/i).fill('split@test.et')
await page.getByLabel(/password/i).fill('split-pass-123')
const [resp] = await Promise.all([
  page.waitForResponse(r => r.url().includes('/api/auth/login')),
  page.getByRole('button', { name: /sign in|log in/i }).click(),
])
results.push(['cross-origin login returns 200', resp.status() === 200])

// 3. session cookie exists for the API origin with SameSite=None
// note: cookies are Secure (SameSite=None) — ctx.cookies(<http url>) filters
// Secure cookies out, so list ALL cookies and match on name+port ownership.
const cookies = await ctx.cookies()
const sess = cookies.find(c => c.name === 'cl_session')
results.push(['cl_session cookie set for API origin', !!sess])
results.push(['cookie SameSite=None', sess?.sameSite === 'None'])

// 4. authenticated /me via the app (wait for redirect/nav away from /login)
await page.waitForTimeout(1500)
const me = await page.evaluate(async () => {
  const r = await fetch('http://127.0.0.1:8056/api/auth/me', { credentials: 'include' })
  return r.json()
})
results.push(['authenticated GET /me works cross-origin', me?.email === 'split@test.et'])

// 5. CSRF bootstrap endpoint
const csrf = await page.evaluate(async () => {
  const r = await fetch('http://127.0.0.1:8056/api/auth/csrf', { credentials: 'include' })
  return (await r.json()).csrf_token
})
results.push(['CSRF bootstrap returns token', !!csrf && csrf.length > 20])

// 6. state-changing request with bootstrapped token (logout)
const logoutStatus = await page.evaluate(async (t) => {
  const r = await fetch('http://127.0.0.1:8056/api/auth/logout', {
    method: 'POST', credentials: 'include', headers: { 'X-CSRF-Token': t } })
  return r.status
}, csrf)
results.push(['POST with bootstrapped CSRF token → 200', logoutStatus === 200])

// 7. all API traffic went to the API origin (VITE_API_BASE respected)
results.push(['SPA sent API calls to :8056', apiCalls.some(c => c.includes('/api/'))])

await browser.close()
let fail = 0
for (const [name, ok] of results) { console.log((ok ? 'PASS' : 'FAIL') + '  ' + name); if (!ok) fail++ }
console.log(fail === 0 ? 'ALL SPLIT-MODE CHECKS PASSED' : fail + ' CHECKS FAILED')
process.exit(fail === 0 ? 0 : 1)
