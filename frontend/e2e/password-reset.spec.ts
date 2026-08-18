/* Password reset — full browser E2E:
   forgot → token generated (read from dev DB, standing in for the email) →
   reset form → token validated → password changed → token invalid on reuse →
   previous session revoked → new password works. */
import { test, expect } from '@playwright/test'
import { execSync } from 'child_process'
import { join, dirname } from 'path'
import { fileURLToPath } from 'url'
import { login, registerCitizen, uniq } from './helpers'
const __dirname = dirname(fileURLToPath(import.meta.url))

const BACKEND = process.env.E2E_BACKEND_DIR || join(__dirname, '..', '..', 'backend')
const id = uniq()
const USER = { email: `pw-reset-${id}@test.et`, old: 'old-password-123', neu: 'new-password-456' }

function latestTokenFor(email: string): string {
  const py = `
from app.db import SessionLocal
from app.models import PasswordReset, User
db = SessionLocal()
u = db.query(User).filter_by(email='${email}').first()
pr = db.query(PasswordReset).filter_by(user_id=u.id).order_by(PasswordReset.created_at.desc()).first()
print(pr.token)
db.close()`
  return execSync(`python3 -c "${py.replace(/"/g, '\\"')}"`, { cwd: BACKEND }).toString().trim()
}

test.describe.serial('password reset browser flow', () => {
  test('full reset cycle with session revocation', async ({ page, browser }) => {
    // register, keep a second logged-in session alive
    await registerCitizen(page, 'PW Reset User', USER.email, USER.old)
    const other = await browser.newContext()
    const op = await other.newPage()
    await login(op, USER.email, USER.old)

    // log out and start forgot-password from the UI
    await page.goto('/settings')
    await page.getByRole('button', { name: /sign out of all devices/i }).click()
    await page.goto('/login')
    await page.getByRole('button', { name: /forgot password/i }).click()
    await page.getByLabel('Email').fill(USER.email)
    await page.getByRole('button', { name: /send reset token/i }).click()
    await expect(page.getByText(/reset token was sent/i)).toBeVisible()

    // second session for the OTHER context was already revoked by logout-all;
    // re-login it so we can prove reset revokes sessions too
    await login(op, USER.email, USER.old)
    await expect(op.getByRole('button', { name: /notifications/i })).toBeVisible()

    // token arrives "by email" (dev: console + DB) — enter it in the reset form
    const token = latestTokenFor(USER.email)
    await page.getByLabel(/reset token/i).fill(token)
    await page.getByLabel(/new password/i).fill(USER.neu)
    await page.getByRole('button', { name: /reset password/i }).click()
    await expect(page.getByText(/password reset\. sign in/i)).toBeVisible()

    // old session is dead after reset
    await op.reload()
    await op.goto('/settings')
    await expect(op.getByText(/sign in to manage settings/i)).toBeVisible()
    await other.close()

    // token is single-use
    await page.getByRole('button', { name: /forgot password/i }).click()
    await page.getByRole('button', { name: /already have a token/i }).click()
    await page.getByLabel(/reset token/i).fill(token)
    await page.getByLabel(/new password/i).fill('another-pass-789')
    await page.getByRole('button', { name: /reset password/i }).click()
    await expect(page.getByText(/invalid or already-used/i)).toBeVisible()

    // old password rejected, new password works
    await page.goto('/login')
    await page.getByLabel('Email').fill(USER.email)
    await page.getByLabel('Password', { exact: true }).fill(USER.old)
    await page.getByRole('button', { name: /sign in/i }).click()
    await expect(page.getByText(/invalid email or password/i)).toBeVisible()
    await login(page, USER.email, USER.neu)
  })

  test('unknown email gets the same success message (no enumeration)', async ({ page }) => {
    await page.goto('/login')
    await page.getByRole('button', { name: /forgot password/i }).click()
    await page.getByLabel('Email').fill(`nobody-${id}@nowhere.et`)
    await page.getByRole('button', { name: /send reset token/i }).click()
    await expect(page.getByText(/reset token was sent/i)).toBeVisible()
  })

  test('garbage token is rejected cleanly', async ({ page }) => {
    await page.goto('/login')
    await page.getByRole('button', { name: /forgot password/i }).click()
    await page.getByRole('button', { name: /already have a token/i }).click()
    await page.getByLabel(/reset token/i).fill('totally-invalid-token')
    await page.getByLabel(/new password/i).fill('whatever-pass-1')
    await page.getByRole('button', { name: /reset password/i }).click()
    await expect(page.getByText(/invalid or already-used/i)).toBeVisible()
  })
})
