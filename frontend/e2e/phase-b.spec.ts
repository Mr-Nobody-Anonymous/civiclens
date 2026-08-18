/* Phase B browser tests: offline-first reporting (REAL network interruption via
   context.setOffline), resolution verification UI, moderation center. */
import { test, expect } from '@playwright/test'
import { execSync } from 'child_process'
import { join, dirname } from 'path'
import { fileURLToPath } from 'url'
import { login, registerCitizen, uniq } from './helpers'
const __dirname = dirname(fileURLToPath(import.meta.url))
const BACKEND = join(__dirname, '..', '..', 'backend')

const id = uniq()

test.describe.serial('offline-first reporting (real network interruption)', () => {
  test('report created offline is queued locally, then auto-synced without duplicates', async ({ browser }) => {
    const ctx = await browser.newContext()
    const page = await ctx.newPage()
    await registerCitizen(page, 'PW Offline', `pw-offline-${id}@test.et`, 'pw-offline-pass1')

    // open the wizard while ONLINE (app shell loads), then cut the network
    await page.goto('/report')
    await expect(page.getByRole('heading', { name: /report an issue/i })).toBeVisible()
    await ctx.setOffline(true)

    // offline indicator appears
    await expect(page.getByText(/offline — reports will be queued/i)).toBeVisible()

    // fill the wizard fully offline (skip evidence + map: use manual city only)
    await page.getByRole('button', { name: /next/i }).click()
    // location step: no geolocation offline — set address manually, skip pin
    await page.getByLabel(/address \/ landmark/i).fill('Offline test street')
    // pos is required to advance; click map is impossible offline (no tiles) but
    // the map div still accepts clicks — Leaflet works without tile downloads
    await page.locator('.leaflet-container').click({ position: { x: 200, y: 150 } })
    await expect(page.getByText(/📍/)).toBeVisible()
    await page.getByRole('button', { name: /next/i }).click()
    await page.getByLabel(/title/i).fill(`Offline queued report ${id}`)
    await page.getByLabel(/description/i).fill('Submitted while completely offline; must sync automatically later.')
    await page.getByRole('button', { name: /next/i }).click()
    await page.getByRole('button', { name: /submit report/i }).click()

    // offline confirmation screen: saved on device
    await expect(page.getByRole('heading', { name: /report saved on your device/i })).toBeVisible({ timeout: 15_000 })
    await expect(page.getByText(/waiting for connection/i)).toBeVisible()

    // report must NOT exist server-side yet
    const before = execSync(
      `python3 -c "from app.db import SessionLocal; from app.models import Report; db=SessionLocal(); print(db.query(Report).filter(Report.title.like('Offline queued report ${id}%')).count()); db.close()"`,
      { cwd: BACKEND }).toString().trim()
    expect(before).toBe('0')

    // reconnect -> auto-sync fires (online event + queue drain)
    await ctx.setOffline(false)
    await expect(page.getByText(/uploaded ✓/i)).toBeVisible({ timeout: 30_000 })

    // exactly ONE report server-side (idempotency key protected the retries)
    const after = execSync(
      `python3 -c "from app.db import SessionLocal; from app.models import Report; db=SessionLocal(); print(db.query(Report).filter(Report.title.like('Offline queued report ${id}%')).count()); db.close()"`,
      { cwd: BACKEND }).toString().trim()
    expect(after).toBe('1')
    await ctx.close()
  })

  test('mid-submit network loss falls back to the offline queue', async ({ browser }) => {
    const ctx = await browser.newContext()
    const page = await ctx.newPage()
    await login(page, `pw-offline-${id}@test.et`, 'pw-offline-pass1')
    await page.goto('/report')
    await page.getByRole('button', { name: /next/i }).click()
    await page.locator('.leaflet-container').click({ position: { x: 220, y: 160 } })
    await expect(page.getByText(/📍/)).toBeVisible()
    await page.getByRole('button', { name: /next/i }).click()
    await page.getByLabel(/title/i).fill(`Midflight drop report ${id}`)
    await page.getByLabel(/description/i).fill('Network dies exactly when the user presses submit on this report.')
    await page.getByRole('button', { name: /next/i }).click()
    // cut the network moments before submit
    await ctx.setOffline(true)
    await page.getByRole('button', { name: /submit report/i }).click()
    await expect(page.getByRole('heading', { name: /report saved on your device/i })).toBeVisible({ timeout: 20_000 })
    await ctx.setOffline(false)
    await expect(page.getByText(/uploaded ✓/i)).toBeVisible({ timeout: 30_000 })
    await ctx.close()
  })
})

test.describe.serial('resolution verification UI', () => {
  let reportUrl = ''

  test('citizen sees confirm banner on resolved report and can dispute', async ({ page, browser }) => {
    // citizen submits
    const citizen = await browser.newContext()
    const cp = await citizen.newPage()
    await registerCitizen(cp, 'PW Resolver', `pw-resolve-${id}@test.et`, 'pw-resolve-pass1')
    await cp.goto('/report')
    await cp.getByRole('button', { name: /next/i }).click()
    await cp.locator('.leaflet-container').click({ position: { x: 250, y: 160 } })
    await cp.getByRole('button', { name: /next/i }).click()
    await cp.getByLabel(/title/i).fill(`Resolution verify test ${id}`)
    await cp.getByLabel(/description/i).fill('Testing the citizen confirmation flow end to end in the browser.')
    await cp.getByRole('button', { name: '📋 Other' }).click()   // Other: no evidence gate
    await cp.getByRole('button', { name: /next/i }).click()
    await cp.getByRole('button', { name: /submit report/i }).click()
    await expect(cp.getByText(/report submitted/i)).toBeVisible({ timeout: 30_000 })
    await cp.getByRole('link', { name: /view report/i }).click()
    reportUrl = cp.url()

    // admin resolves it (Other category → no evidence requirement)
    await login(page, 'admin@civiclens.et', 'admin12345')
    await page.goto('/priority')
    const row = page.getByRole('button', { name: new RegExp(`Resolution verify test ${id}`) })
    await expect(row).toBeVisible({ timeout: 20_000 })
    await row.click()
    await page.getByRole('button', { name: /mark resolved/i }).click()
    await expect(page.getByText(/marked resolved/i)).toBeVisible()

    // citizen sees the banner and disputes
    await cp.goto(reportUrl)
    await expect(cp.getByText(/is this issue actually fixed/i)).toBeVisible()
    await cp.getByRole('button', { name: /still a problem/i }).click()
    await expect(cp.getByText(/report reopened/i)).toBeVisible()
    await expect(cp.getByText(/reopened/i).first()).toBeVisible()
    await citizen.close()
  })
})

test.describe.serial('moderation center', () => {
  test('unified queue shows flagged content; hide is reversible', async ({ page }) => {
    await login(page, 'admin@civiclens.et', 'admin12345')
    // create + flag a comment through the UI
    await page.goto('/reports')
    await page.getByRole('link', { name: /pothole|streetlight|water/i }).first().click()
    await page.getByPlaceholder(/add a comment/i).fill(`Moderation target comment ${id}`)
    await page.getByRole('button', { name: /post/i }).click()
    await expect(page.getByText(`Moderation target comment ${id}`)).toBeVisible()
    await page.getByRole('button', { name: /report comment/i }).last().click()
    await expect(page.getByText(/comment reported/i)).toBeVisible()

    // moderation center shows it
    await page.goto('/dashboard')
    await page.getByRole('tab', { name: /^moderation$/i }).click()
    await expect(page.getByText(/reported comment/i).first()).toBeVisible()
    const item = page.locator('.card', { hasText: `Moderation target comment ${id}` }).first()
    await expect(item).toBeVisible()
    await item.getByRole('button', { name: /hide/i }).click()
    await expect(page.getByText(/comment hidden \(reversible\)/i)).toBeVisible()

    // history records the action
    await page.getByRole('button', { name: /show moderation history/i }).click()
    await expect(page.getByText(/comment\.hide/).first()).toBeVisible()
  })
})
