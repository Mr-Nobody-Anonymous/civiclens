/* Citizen journey: register → language switch → wizard → video upload →
   AI analysis → routing → comment → notifications → (org resolves) → reopen. */
import { test, expect } from '@playwright/test'
import { join, dirname } from 'path'
import { fileURLToPath } from 'url'
const __dirname = dirname(fileURLToPath(import.meta.url))
import { ASSETS, login, openRow, registerCitizen, submitReport, uniq } from './helpers'

const id = uniq()
const CIT = { name: 'PW Citizen', email: `pw-citizen-${id}@test.et`, pw: 'pw-citizen-pass1' }
let reportUrl = ''

test.describe.serial('citizen journey', () => {
  test('register, switch language EN→AM→EN', async ({ page }) => {
    await registerCitizen(page, CIT.name, CIT.email, CIT.pw)
    await page.goto('/')
    // EN → AM
    await page.getByRole('button', { name: /language/i }).click()
    await expect(page.getByRole('heading', { name: /ሪፖርት ያድርጉት/ })).toBeVisible()
    await expect(page.getByRole('link', { name: /ችግር ሪፖርት ያድርጉ/ }).first()).toBeVisible()
    // AM → EN
    await page.getByRole('button', { name: /language/i }).click()
    await expect(page.getByRole('heading', { name: /report it/i })).toBeVisible()
  })

  test('submit report with real video, see progress, AI result appears', async ({ page }) => {
    await login(page, CIT.email, CIT.pw)
    await submitReport(page, {
      title: `PW pothole on Africa Avenue ${id}`,
      description: 'Deep dangerous pothole near the bus stop, many cars and pedestrians affected daily. Urgent!',
      category: '🛣️ Roads & Transportation',
      videoPath: join(ASSETS, 'test.mp4'),
    })
    // upload progress bar rendered during submit
    // confirmation screen
    await expect(page.getByText(/report submitted/i)).toBeVisible({ timeout: 30_000 })
    await expect(page.getByText(/CL-[0-9A-F]{6}/).first()).toBeVisible()
    // AI analysis progress animation, then result via polling
    await expect(page.getByText(/AI classification/i)).toBeVisible({ timeout: 30_000 })
    await expect(page.getByText(/Roads & Transportation/).first()).toBeVisible()
    await expect(page.getByText(/%/).first()).toBeVisible()          // confidence shown
    await expect(page.getByText(/human review may change/i)).toBeVisible()

    await page.getByRole('link', { name: /view report/i }).click()
    await expect(page.getByRole('heading', { name: new RegExp(`PW pothole.*${id}`) })).toBeVisible()
    reportUrl = page.url()
    // routing/organization info + confidence band + model transparency
    await expect(page.getByText(/roads authority/i).first()).toBeVisible({ timeout: 20_000 })
    await expect(page.getByText(/confidence/i).first()).toBeVisible()
    await expect(page.getByText(/model:/i)).toBeVisible()
    // evidence video is playable (poster/thumb present)
    await expect(page.locator('video[src*="/media/"]')).toBeVisible()
  })

  test('add a comment and see notifications', async ({ page }) => {
    await login(page, CIT.email, CIT.pw)
    await page.goto(reportUrl)
    await page.getByPlaceholder(/add a comment/i).fill('Please fix before the rainy season.')
    await page.getByRole('button', { name: /post/i }).click()
    await expect(page.getByText('Please fix before the rainy season.')).toBeVisible()
    // notification bell shows items
    await page.getByRole('button', { name: /notifications/i }).click()
    await expect(page.getByText(/AI analysis complete/i).first()).toBeVisible()
  })

  test('citizen sees resolution after organization workflow, then reopens', async ({ page, browser }) => {
    // --- staff resolves it in a separate session ---
    const staff = await browser.newContext()
    const sp = await staff.newPage()
    await login(sp, 'admin@civiclens.et', 'admin12345')
    // priority queue lists all open reports and keeps them visible across
    // status changes (unlike the "needs review" filter)
    await sp.goto('/priority')
    const row = sp.getByRole('button', { name: new RegExp(`PW pothole.*${id}`) })
    await expect(row).toBeVisible()
    const start = await openRow(sp, row, /start work/i)
    await start.click()
    await expect(sp.getByText(/marked in progress/i)).toBeVisible()
    const resolve = await openRow(sp, row, /mark resolved/i)
    await resolve.click()
    await expect(sp.getByText(/marked resolved/i)).toBeVisible()
    await staff.close()

    // --- citizen sees resolution + notification, disputes it ---
    await login(page, CIT.email, CIT.pw)
    await page.goto(reportUrl)
    await expect(page.getByText(/resolved/i).first()).toBeVisible()
    await page.getByRole('button', { name: /notifications/i }).click()
    await expect(page.getByText(/resolved/i).first()).toBeVisible()
    await page.getByRole('button', { name: /notifications/i }).click()  // close dropdown

    page.on('dialog', d => d.accept('The hole is still half open'))
    await page.getByRole('button', { name: /reopen|dispute/i }).click()
    await expect(page.getByText(/reopened/i).first()).toBeVisible({ timeout: 15_000 })
  })
})
