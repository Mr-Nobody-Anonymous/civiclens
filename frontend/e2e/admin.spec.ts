/* Admin journey: dashboards, users, rules, jobs incl. retry, moderation,
   AI correction, audit log. */
import { test, expect } from '@playwright/test'
import { login, openRow } from './helpers'

test.describe.serial('admin journey', () => {
  test('overview KPIs are real data', async ({ page }) => {
    await login(page, 'admin@civiclens.et', 'admin12345')
    await page.goto('/dashboard')
    await expect(page.getByText(/total reports/i)).toBeVisible()
    // KPI is a real number > 0 (seeded data), not a placeholder
    const total = await page.locator('.card', { hasText: 'Total reports' }).locator('p.text-3xl').textContent()
    expect(Number(total)).toBeGreaterThan(0)
    await expect(page.getByText(/severity distribution/i)).toBeVisible()
    await expect(page.getByText(/geographic hotspots/i)).toBeVisible()
  })

  test('users management: change role and back', async ({ page }) => {
    await login(page, 'admin@civiclens.et', 'admin12345')
    await page.goto('/dashboard')
    await page.getByRole('tab', { name: /users/i }).click()
    await expect(page.getByText(/citizen@example\.et/)).toBeVisible()
    const roleSelect = page.getByLabel('Role for citizen@example.et')
    await roleSelect.selectOption('moderator')
    await expect(page.getByText(/role updated/i)).toBeVisible()
    await roleSelect.selectOption('citizen')
    await expect(page.getByText(/role updated/i).first()).toBeVisible()
    // own role selector is disabled (cannot self-demote)
    await expect(page.getByLabel('Role for admin@civiclens.et')).toBeDisabled()
  })

  test('routing rules and audit log are populated', async ({ page }) => {
    await login(page, 'admin@civiclens.et', 'admin12345')
    await page.goto('/dashboard')
    await page.getByRole('tab', { name: /routing rules/i }).click()
    await expect(page.getByRole('cell', { name: 'Telecom', exact: true })).toBeVisible()
    await expect(page.getByText(/ethio telecom/i).first()).toBeVisible()
    await page.getByRole('tab', { name: /audit log/i }).click()
    await expect(page.getByText(/user\.login/).first()).toBeVisible()
  })

  test('jobs tab shows dead job and retry requeues it', async ({ page }) => {
    await login(page, 'admin@civiclens.et', 'admin12345')
    await page.goto('/dashboard')
    await page.getByRole('tab', { name: /jobs/i }).click()
    const deadRow = page.locator('tr', { hasText: 'e2e_dead_job' })
    await expect(deadRow).toBeVisible()
    await expect(deadRow.locator('span', { hasText: /^dead$/ })).toBeVisible()
    await deadRow.getByRole('button', { name: /retry/i }).click()
    await expect(page.getByText(/job requeued/i)).toBeVisible()
  })

  test('moderation: flag hides report from public, unflag restores', async ({ page, browser }) => {
    await login(page, 'admin@civiclens.et', 'admin12345')
    await page.goto('/dashboard')
    await page.getByRole('tab', { name: /needs review/i }).click()
    const row = page.locator('.card', { hasText: 'E2E AI-failed fixture report' }).first()
    await expect(row).toBeVisible()
    await row.getByRole('button', { name: /E2E AI-failed fixture/i }).click()
    await row.getByPlaceholder(/internal note/i).fill('moderation test')
    await row.getByRole('button', { name: /flag as fake\/abuse/i }).click()
    await expect(page.getByText(/flagged & hidden/i)).toBeVisible()

    // public user can no longer find it
    const anon = await browser.newContext()
    const ap = await anon.newPage()
    await ap.goto('/reports?q=E2E AI-failed fixture')
    await expect(ap.getByText(/no reports match/i)).toBeVisible()
    await anon.close()

    // restore via flagged tab
    await page.getByRole('tab', { name: /flagged/i }).click()
    const frow = page.locator('.card', { hasText: 'E2E AI-failed fixture report' }).first()
    await frow.getByRole('button', { name: /E2E AI-failed fixture/i }).click()
    await frow.getByRole('button', { name: /unflag/i }).click()
    await expect(page.getByText(/unflagged/i)).toBeVisible()
  })

  test('AI failure is visible and correction workflow works', async ({ page }) => {
    await login(page, 'admin@civiclens.et', 'admin12345')
    await page.goto('/dashboard')
    await page.getByRole('tab', { name: /needs review/i }).click()
    const row = page.locator('.card', { hasText: 'E2E AI-failed fixture report' }).first()
    await openRow(page, row.getByRole('button', { name: /E2E AI-failed fixture/i }), /apply changes/i)
    // re-run AI analysis button exists for failed analysis
    await expect(row.getByRole('button', { name: /re-run ai analysis/i })).toBeVisible()
    // human correction: set severity + category
    await row.getByLabel(/severity/i).selectOption('4')
    await row.getByLabel(/category \(correct ai\)/i).selectOption('Water')
    await row.getByRole('button', { name: /apply changes/i }).click()
    await expect(page.getByText(/report updated/i)).toBeVisible()
  })
})
