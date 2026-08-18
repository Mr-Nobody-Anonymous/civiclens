/* Organization journey + cross-org isolation, exercised through the real UI. */
import { test, expect } from '@playwright/test'
import { join, dirname } from 'path'
import { fileURLToPath } from 'url'
const __dirname = dirname(fileURLToPath(import.meta.url))
import { ASSETS, login, openRow, uniq } from './helpers'

const id = uniq()

test.describe.serial('organization journey', () => {
  test('roads staff: see only own org, accept, progress, resolution evidence, resolve', async ({ page, browser }) => {
    // citizen (anonymous) creates a roads report that routes to Roads Authority
    const anon = await browser.newContext()
    const ap = await anon.newPage()
    await ap.goto('/report')
    await ap.getByRole('button', { name: /next/i }).click()
    const map = ap.locator('.leaflet-container')
    await ap.waitForTimeout(800)
    await map.click({ position: { x: 300, y: 150 } })
    await ap.getByRole('button', { name: /next/i }).click()
    await ap.getByLabel(/title/i).fill(`PW org-flow pothole ${id}`)
    await ap.getByLabel(/description/i).fill('Deep pothole on the asphalt road near the market, urgent risk for cars.')
    await ap.getByRole('button', { name: '🛣️ Roads & Transportation' }).click()
    // anonymous captcha
    const q = await ap.getByText(/what is \d+ \+ \d+/i).textContent()
    const [a, b] = q!.match(/\d+/g)!.map(Number)
    await ap.getByLabel(/what is/i).fill(String(a + b))
    await ap.getByRole('button', { name: /next/i }).click()
    await ap.getByRole('button', { name: /submit report/i }).click()
    await expect(ap.getByText(/report submitted/i)).toBeVisible({ timeout: 30_000 })
    await expect(ap.getByText(/AI classification/i)).toBeVisible({ timeout: 30_000 })
    await anon.close()

    // roads staff logs in
    await login(page, 'staff@roads.et', 'roads12345')
    await page.goto('/organization')
    await expect(page.getByRole('heading', { name: /roads authority/i })).toBeVisible()
    // sees ONLY roads reports (spot check: no telecom items in list)
    await expect(page.getByText(new RegExp(`PW org-flow pothole ${id}`))).toBeVisible({ timeout: 20_000 })
    await expect(page.getByText(/no mobile network in gerji/i)).toHaveCount(0)

    // open the report row and work it
    const row = page.getByRole('button', { name: new RegExp(`PW org-flow pothole ${id}`) })
    await row.click()
    // view evidence securely: open report detail in same session
    await page.getByRole('link', { name: /open/i }).first().click()
    await expect(page.getByRole('heading', { name: new RegExp(`PW org-flow pothole ${id}`) })).toBeVisible()
    await page.goBack()

    const accept = await openRow(page, row, /accept assignment/i)
    await accept.click()
    await expect(page.getByText(/assignment accepted/i)).toBeVisible()
    const start = await openRow(page, row, /start work/i)
    await start.click()
    await expect(page.getByText(/marked in progress/i)).toBeVisible()

    // resolution evidence upload
    await page.getByRole('button', { name: /upload resolution evidence/i }).first().click()
    await page.locator('input[type="file"]').setInputFiles(join(ASSETS, 'evidence.png'))
    await expect(page.getByText(/resolution evidence uploaded/i)).toBeVisible({ timeout: 20_000 })

    const resolve = await openRow(page, row, /mark resolved/i)
    await resolve.click()
    await expect(page.getByText(/marked resolved/i)).toBeVisible()
  })

  test('telecom staff cannot see or manage the roads report', async ({ page }) => {
    await login(page, 'staff@ethiotelecom.et', 'telecom123')
    await page.goto('/organization')
    await expect(page.getByRole('heading', { name: /ethio telecom/i })).toBeVisible()
    // the roads report never appears in telecom's portal or priority queue
    await expect(page.getByText(new RegExp(`PW org-flow pothole ${id}`))).toHaveCount(0)
    await page.goto('/priority')
    await expect(page.getByText(new RegExp(`PW org-flow pothole ${id}`))).toHaveCount(0)
  })
})
