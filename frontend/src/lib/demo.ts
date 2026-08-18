/* Demo-mode authentication.
 *
 * The GitHub Pages build is static-only: there is no FastAPI backend to
 * validate credentials against. So when the API is unreachable, login falls
 * back to these hard-coded demo accounts so the UI can be explored.
 *
 * These accounts mirror backend/seed.py and are DEVELOPMENT-ONLY.
 */
import type { User } from './types'

export interface DemoAccount {
  email: string
  password: string
  user: User
}

export const DEMO_ACCOUNTS: DemoAccount[] = [
  {
    email: 'admin@civiclens.et',
    password: 'admin12345',
    user: { id: 'demo-admin', name: 'Admin User', email: 'admin@civiclens.et', role: 'admin', language: 'en', email_notifications: true },
  },
  {
    email: 'moderator@civiclens.et',
    password: 'moderator123',
    user: { id: 'demo-moderator', name: 'Meron Tadesse', email: 'moderator@civiclens.et', role: 'moderator', language: 'en', email_notifications: true },
  },
  {
    email: 'staff@ethiotelecom.et',
    password: 'telecom123',
    user: { id: 'demo-telecom', name: 'Dawit Bekele', email: 'staff@ethiotelecom.et', role: 'org_staff', language: 'en', email_notifications: true, organization_id: 'demo-telecom-org', organization_name: 'Ethio telecom' },
  },
  {
    email: 'staff@roads.et',
    password: 'roads12345',
    user: { id: 'demo-roads', name: 'Sara Alemu', email: 'staff@roads.et', role: 'org_staff', language: 'en', email_notifications: true, organization_id: 'demo-roads-org', organization_name: 'Addis Ababa City Roads Authority' },
  },
  {
    email: 'citizen@example.et',
    password: 'citizen123',
    user: { id: 'demo-citizen', name: 'Abebe Kebede', email: 'citizen@example.et', role: 'citizen', language: 'en', email_notifications: true, city: 'Addis Ababa' },
  },
]

/** Try demo login; returns the demo User or null if credentials don't match. */
export function loginDemo(email: string, password: string): User | null {
  const acc = DEMO_ACCOUNTS.find(a => a.email === email.toLowerCase() && a.password === password)
  return acc ? { ...acc.user } : null
}

/** True if the given email is a known demo account (used to hint the user). */
export function isDemoEmail(email: string): boolean {
  return DEMO_ACCOUNTS.some(a => a.email === email.toLowerCase())
}