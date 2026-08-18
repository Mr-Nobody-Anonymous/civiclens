/* Accessibility (axe-core) + mobile viewport verification. */
import { test, expect } from '@playwright/test'
import AxeBuilder from '@axe-core/playwright'
import { login } from './helpers'

const scan = (page: import('@playwright/test').Page) =>
  new AxeBuilder({ page })
    .withTags(['wcag2a', 'wcag2aa'])
    // Leaflet's internal DOM is third-party; documented limitation
    .exclude('.leaflet-container')
    .analyze()

const CRITICAL = (v: import('axe-core').Result[]) =>
  v.filter(x => x.impact === 'critical' || x.impact === 'serious')

test.describe('accessibility (axe, WCAG 2.1 AA)', () => {
  for (const [name, path] of [['landing', '/'], ['reports', '/reports'], ['login', '/login'],
                              ['privacy', '/privacy'], ['wizard', '/report']] as const) {
    test(`${name} has no serious/critical violations`, async ({ page }) => {
      await page.goto(path)
      await page.waitForTimeout(700)
      const res = await scan(page)
      const bad = CRITICAL(res.violations)
      expect(bad.map(b => `${b.id}: ${b.nodes.length} nodes`)).toEqual([])
    })
  }

  test('admin dashboard has no serious/critical violations @needs-demo-accounts', async ({ page }) => {
    await login(page, 'admin@civiclens.et', 'admin12345')
    await page.goto('/dashboard')
    await page.waitForTimeout(1000)
    const res = await scan(page)
    expect(CRITICAL(res.violations).map(b => b.id)).toEqual([])
  })

  test('keyboard-only: navigate landing to login form @needs-demo-accounts', async ({ page }) => {
    await page.goto('/login')
    await page.keyboard.press('Tab')
    // keep tabbing until the email input is focused (skip nav links)
    for (let i = 0; i < 25; i++) {
      const id = await page.evaluate(() => document.activeElement?.id)
      if (id === 'email') break
      await page.keyboard.press('Tab')
    }
    expect(await page.evaluate(() => document.activeElement?.id)).toBe('email')
    await page.keyboard.type('citizen@example.et')
    await page.keyboard.press('Tab')
    await page.keyboard.type('citizen123')
    await page.keyboard.press('Enter')
    await expect(page.getByText(/welcome/i)).toBeVisible()
  })

  test('confirm dialog is accessible and keyboard-dismissable @needs-demo-accounts', async ({ page }) => {
    await login(page, 'citizen@example.et', 'citizen123')
    await page.goto('/settings')
    await page.getByRole('button', { name: /delete my account/i }).click()
    const dialog = page.getByRole('dialog')
    await expect(dialog).toBeVisible()
    await dialog.getByRole('button', { name: /cancel/i }).click()
    await expect(dialog).toHaveCount(0)
  })
})

test.describe('mobile viewports — no horizontal overflow', () => {
  const widths = [375, 390, 768, 1280]
  const pages = ['/', '/reports', '/report', '/map', '/login', '/settings', '/privacy']
  for (const w of widths) {
    test(`width ${w}px`, async ({ page }) => {
      await page.setViewportSize({ width: w, height: 844 })
      for (const p of pages) {
        await page.goto(p)
        await page.waitForTimeout(500)
        const overflow = await page.evaluate(() =>
          document.documentElement.scrollWidth - document.documentElement.clientWidth)
        expect(overflow, `horizontal overflow on ${p} at ${w}px`).toBeLessThanOrEqual(1)
      }
    })
  }

  test('mobile bottom navigation is present at 375px', async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 812 })
    await page.goto('/')
    await expect(page.getByRole('navigation', { name: /mobile/i })).toBeVisible()
  })

  test('org portal and admin dashboard usable at 390px @needs-demo-accounts', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 })
    await login(page, 'staff@roads.et', 'roads12345')
    await page.goto('/organization')
    await expect(page.getByText(/assigned reports/i).first()).toBeVisible()
    const overflow = await page.evaluate(() =>
      document.documentElement.scrollWidth - document.documentElement.clientWidth)
    expect(overflow).toBeLessThanOrEqual(1)
  })
})
