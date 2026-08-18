import { Page, expect } from '@playwright/test'
import { join, dirname } from 'path'
import { fileURLToPath } from 'url'
const __dirname = dirname(fileURLToPath(import.meta.url))

export const ASSETS = join(__dirname, 'assets')
export const uniq = () => `${Date.now()}${Math.floor(Math.random() * 1e4)}`

export async function login(page: Page, email: string, password: string) {
  await page.goto('/login')
  await page.getByLabel('Email').fill(email)
  const respPromise = page.waitForResponse(r => r.url().includes('/api/auth/login'))
  await page.getByLabel('Password', { exact: true }).fill(password)
  await page.getByRole('button', { name: /sign in/i }).click()
  const resp = await respPromise
  expect(resp.status(), `login as ${email}`).toBe(200)
  // wait until the app has left /login (role-based redirect happened)
  await expect(page).not.toHaveURL(/\/login/)
}

export async function logout(page: Page) {
  const btn = page.getByRole('button', { name: /sign out/i })
  if (await btn.count()) await btn.click()
}

export async function registerCitizen(page: Page, name: string, email: string, password: string) {
  await page.goto('/login')
  await page.getByRole('button', { name: /no account yet/i }).click()
  await page.getByLabel('Full name').fill(name)
  await page.getByLabel('Email').fill(email)
  await page.getByLabel('Password', { exact: true }).fill(password)
  await page.getByRole('button', { name: /create account/i }).click()
  await expect(page.getByText(new RegExp(`welcome`, 'i'))).toBeVisible()
}

/** Fill the report wizard through all four steps. Returns after clicking Submit. */
export async function submitReport(page: Page, opts: {
  title: string; description: string; category?: string
  videoPath?: string; imagePath?: string
}) {
  await page.goto('/report')
  // Step 1 — evidence
  if (opts.videoPath) {
    await page.locator('input[accept*="video"]').setInputFiles(opts.videoPath)
    await expect(page.locator('video, img').first()).toBeVisible()
  }
  if (opts.imagePath) {
    await page.locator('input[accept*="image"]').setInputFiles(opts.imagePath)
  }
  await page.getByRole('button', { name: /next/i }).click()
  // Step 2 — location: click the map center
  const map = page.locator('.leaflet-container')
  await expect(map).toBeVisible()
  await page.waitForTimeout(800)   // tiles + map ready
  await map.click({ position: { x: 300, y: 150 } })
  await expect(page.getByText(/📍/)).toBeVisible()
  await page.getByRole('button', { name: /next/i }).click()
  // Step 3 — describe
  await page.getByLabel(/title/i).fill(opts.title)
  await page.getByLabel(/description/i).fill(opts.description)
  if (opts.category) await page.getByRole('button', { name: opts.category }).click()
  await page.getByRole('button', { name: /next/i }).click()
  // Step 4 — review & submit
  await expect(page.getByText(/review & submit/i)).toBeVisible()
  await page.getByRole('button', { name: /submit report/i }).click()
}

/** Open a collapsible ReportRow and wait until its action panel is really
    visible — retries because row lists refetch/re-render after actions. */
export async function openRow(page: Page, row: import('@playwright/test').Locator,
                              panelButton: RegExp) {
  for (let i = 0; i < 6; i++) {
    await row.click()
    const target = page.getByRole('button', { name: panelButton }).first()
    try {
      await target.waitFor({ state: 'visible', timeout: 2500 })
      return target
    } catch { /* row re-rendered collapsed; retry */ }
  }
  throw new Error(`Row panel button ${panelButton} never became visible`)
}
