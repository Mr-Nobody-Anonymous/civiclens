/* AI outage → report not lost → manual review visible in browser →
   AI restored → admin clicks "Re-run AI analysis" → classification appears.
   The AI service is genuinely stopped/started via its control port. */
import { test, expect } from '@playwright/test'
import { execSync } from 'child_process'
import { join, dirname } from 'path'
import { fileURLToPath } from 'url'
import { login, submitReport, uniq } from './helpers'
const __dirname = dirname(fileURLToPath(import.meta.url))

const id = uniq()

function aiUp(): boolean {
  try { execSync('curl -s --max-time 2 localhost:8090/health', { stdio: 'pipe' }); return true }
  catch { return false }
}
function stopAi() {
  try {
    execSync("for pid in $(ss -tlnp 2>/dev/null | grep ':8090' | grep -oP 'pid=\\K[0-9]+' | sort -u); do kill $pid 2>/dev/null; done; sleep 1",
      { stdio: 'pipe', shell: '/bin/bash' })
  } catch { /* ok */ }
}
function startAi() {
  execSync('cd ../ai-service && (nohup python3 main.py >/tmp/e2e-ai.log 2>&1 &)',
    { cwd: join(__dirname, '..'), stdio: 'pipe', shell: '/bin/bash' })
  // wait until it actually serves /health (blind sleep caused cascade failures
  // in later specs whenever the bind/startup was slow)
  for (let i = 0; i < 30; i++) {
    if (aiUp()) return
    execSync('sleep 0.5', { shell: '/bin/bash' })
  }
  throw new Error('AI service failed to come back up within 15s — check /tmp/e2e-ai.log')
}

test.describe.serial('AI outage and recovery (browser)', () => {
  test.skip(!aiUp(), 'AI service not running at start — cannot exercise outage cycle')

  test('report survives AI outage and is recovered by admin retry', async ({ page }) => {
    stopAi()
    await expect.poll(() => aiUp(), { timeout: 10_000 }).toBe(false)

    // citizen submits while AI is DOWN
    await login(page, 'citizen@example.et', 'citizen123')
    await submitReport(page, {
      title: `AI outage browser test ${id}`,
      description: 'Broken streetlight leaving the whole street dark and unsafe at night.',
      category: '⚡ Electricity',
    })
    await expect(page.getByText(/report submitted/i)).toBeVisible({ timeout: 30_000 })

    // report is NOT lost: it lands in manual review with the failure explained
    await page.getByRole('link', { name: /view report/i }).click()
    await expect(page.getByText(/automatic analysis failed.*manual review/i)).toBeVisible({ timeout: 30_000 })
    await expect(page.getByText(/under review/i).first()).toBeVisible()
    const reportUrl = page.url()

    // restore AI, admin retries from the triage row
    startAi()
    await expect.poll(() => aiUp(), { timeout: 15_000 }).toBe(true)

    await login(page, 'admin@civiclens.et', 'admin12345')
    await page.goto('/dashboard')
    await page.getByRole('tab', { name: /needs review/i }).click()
    const row = page.locator('.card', { hasText: `AI outage browser test ${id}` }).first()
    await expect(row).toBeVisible()
    await row.getByRole('button', { name: new RegExp(`AI outage browser test ${id}`) }).click()
    await row.getByRole('button', { name: /re-run ai analysis/i }).click()
    await expect(page.getByText(/ai analysis requeued/i)).toBeVisible()

    // processing completes: classification + confidence now visible on detail page
    await page.goto(reportUrl)
    await expect.poll(async () => {
      await page.reload()
      return page.getByText(/AI classification/i).isVisible()
    }, { timeout: 40_000, intervals: [3000] }).toBe(true)
    await expect(page.getByText(/Electricity/).first()).toBeVisible()
    await expect(page.getByText(/%/).first()).toBeVisible()
  })
})
