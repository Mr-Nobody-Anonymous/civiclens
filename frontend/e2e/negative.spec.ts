/* Negative browser tests: authz walls, invalid/failed uploads, AI failure UX,
   invalid transitions, expired session, CSRF failure. */
import { test, expect } from '@playwright/test'
import { join, dirname } from 'path'
import { fileURLToPath } from 'url'
const __dirname = dirname(fileURLToPath(import.meta.url))
import { ASSETS, login } from './helpers'

test('unauthenticated users hit auth walls, not blank pages', async ({ page }) => {
  await page.goto('/dashboard')
  await expect(page.getByText(/staff access required/i)).toBeVisible()
  await page.goto('/organization')
  await expect(page.getByText(/organization access required/i)).toBeVisible()
  await page.goto('/priority')
  await expect(page.getByText(/authorized users only/i)).toBeVisible()
  await page.goto('/settings')
  await expect(page.getByText(/sign in to manage settings/i)).toBeVisible()
})

test('citizen role cannot use admin dashboard', async ({ page }) => {
  await login(page, 'citizen@example.et', 'citizen123')
  await page.goto('/dashboard')
  await expect(page.getByText(/staff access required/i)).toBeVisible()
  await page.goto('/organization')
  await expect(page.getByText(/organization access required/i)).toBeVisible()
})

test('invalid upload types are rejected with clear errors', async ({ page }) => {
  await login(page, 'citizen@example.et', 'citizen123')
  await page.goto('/report')
  // client-side: text file rejected immediately
  await page.locator('input[accept*="video"]').setInputFiles(join(ASSETS, 'note.txt'))
  await expect(page.getByText(/unsupported file type/i)).toBeVisible()
})

test('server-side rejects fake mp4 during submit; user can retry', async ({ page }) => {
  await login(page, 'citizen@example.et', 'citizen123')
  await page.goto('/report')
  await page.locator('input[accept*="video"]').setInputFiles(join(ASSETS, 'fake.mp4'))
  await page.getByRole('button', { name: /next/i }).click()
  const map = page.locator('.leaflet-container')
  await expect(map).toBeVisible()
  await page.waitForTimeout(1000)
  await map.click({ position: { x: 300, y: 150 } })
  await expect(page.getByText(/📍/)).toBeVisible()      // wait for pin before proceeding
  await page.getByRole('button', { name: /next/i }).click()
  await page.getByLabel(/title/i).fill('Fake video rejection test')
  await page.getByLabel(/description/i).fill('This submission carries an invalid video file on purpose.')
  await page.getByRole('button', { name: /next/i }).click()
  await page.getByRole('button', { name: /submit report/i }).click()
  // upload fails server-side (magic bytes), wizard stays recoverable
  await expect(page.getByText(/does not match its declared type|press submit again/i).first())
    .toBeVisible({ timeout: 30_000 })
  await expect(page.getByRole('button', { name: /submit report/i })).toBeEnabled()
})

test('AI-failure state is visible with manual-review message', async ({ page }) => {
  await login(page, 'admin@civiclens.et', 'admin12345')
  await page.goto('/reports?q=E2E AI-failed fixture')
  await page.getByRole('link', { name: /E2E AI-failed fixture/i }).first().click()
  await expect(page.getByText(/automatic analysis failed.*manual review/i)).toBeVisible()
})

test('invalid state transition surfaces a clear error toast', async ({ page }) => {
  await login(page, 'admin@civiclens.et', 'admin12345')
  await page.goto('/dashboard')
  await page.getByRole('tab', { name: /needs review/i }).click()
  const row = page.locator('.card', { hasText: 'E2E AI-failed fixture report' }).first()
  await row.getByRole('button', { name: /E2E AI-failed fixture/i }).click()
  // under_review -> submitted is not a legal transition
  await row.getByLabel(/status/i).selectOption('submitted')
  await row.getByRole('button', { name: /apply changes/i }).click()
  await expect(page.getByText(/invalid status transition/i)).toBeVisible()
})

test('expired/invalid session degrades to logged-out state', async ({ page, context }) => {
  await login(page, 'citizen@example.et', 'citizen123')
  // corrupt the session cookie (simulates expiry/revocation)
  const cookies = await context.cookies()
  const sess = cookies.find(c => c.name === 'cl_session')
  expect(sess).toBeTruthy()
  await context.clearCookies()
  await context.addCookies([{
    name: 'cl_session', value: 'expired-or-revoked-token',
    domain: sess!.domain, path: sess!.path,
  }])
  await page.goto('/settings')
  await expect(page.getByText(/sign in to manage settings/i)).toBeVisible()
})

test('CSRF failure: mutation without token is blocked by the server', async ({ page }) => {
  await login(page, 'citizen@example.et', 'citizen123')
  // fire a fetch that skips the client's CSRF header — must be rejected with 403
  const status = await page.evaluate(async () => {
    const r = await fetch('/api/reports/nonexistent/flag', {
      method: 'POST', credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ reason: 'csrf test' }),
    })
    return r.status
  })
  expect(status).toBe(403)
})
