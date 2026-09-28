/* Demo-mode authentication and data.
 *
 * The GitHub Pages build is static-only: there is no FastAPI backend to
 * validate credentials against. So when the API is unreachable, login falls
 * back to these hard-coded demo accounts so the UI can be explored.
 *
 * These accounts mirror backend/seed.py and are DEVELOPMENT-ONLY.
 */
import type { Report, User } from './types'

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

export const DEMO_REPORTS: Report[] = [
  {
    id: 'demo-report-1',
    public_code: 'ET-AA-2026-001',
    title: 'Damaged Asphalt & Deep Pothole on Bole Road',
    description: 'Large crater near Edna Mall intersection causing vehicle damage and major traffic backup.',
    category: 'Roads & Infrastructure',
    issue_type: 'Pothole',
    severity: 4,
    status: 'assigned',
    city: 'Addis Ababa',
    latitude: 8.9984,
    longitude: 38.7865,
    address: 'Cameroon St, Bole, Addis Ababa',
    organization_name: 'Addis Ababa City Roads Authority',
    is_demo: true,
    created_at: '2026-09-28T08:30:00Z',
    media: [],
    ai: {
      category: 'Roads & Infrastructure',
      issue_type: 'Pothole',
      severity: 4,
      confidence: 0.94,
      confidence_band: 'high',
      urgency: 'high',
      responsible_organization: 'Addis Ababa City Roads Authority',
      reasoning: 'Video evidence shows deep asphalt depression disrupting multi-lane traffic.',
      model_name: 'CivicLens AI Vision',
      corrected: false,
    },
    history: [
      { to_status: 'submitted', note: 'Report submitted by citizen', created_at: '2026-09-28T08:30:00Z' },
      { to_status: 'ai_analysis', note: 'AI classified as Roads & Infrastructure (severity 4)', created_at: '2026-09-28T08:31:00Z' },
      { to_status: 'assigned', note: 'Dispatched to AACRA District 3 maintenance team', created_at: '2026-09-28T09:15:00Z' },
    ],
  },
  {
    id: 'demo-report-2',
    public_code: 'ET-AA-2026-002',
    title: 'Main Water Line Burst & Flooding',
    description: 'Clean drinking water gushing onto the street from a cracked municipal supply pipe.',
    category: 'Water & Sanitation',
    issue_type: 'Water Leak',
    severity: 5,
    status: 'in_progress',
    city: 'Addis Ababa',
    latitude: 9.0182,
    longitude: 38.7678,
    address: 'Kazanchis, Kirkos, Addis Ababa',
    organization_name: 'Addis Ababa Water and Sewerage Authority',
    is_demo: true,
    created_at: '2026-09-28T07:10:00Z',
    media: [],
    ai: {
      category: 'Water & Sanitation',
      issue_type: 'Pipe Burst',
      severity: 5,
      confidence: 0.96,
      confidence_band: 'high',
      urgency: 'critical',
      responsible_organization: 'Addis Ababa Water and Sewerage Authority',
      reasoning: 'High volume pressurized water loss threatening surrounding residences.',
      model_name: 'CivicLens AI Vision',
      corrected: false,
    },
    history: [
      { to_status: 'submitted', note: 'Report submitted by citizen', created_at: '2026-09-28T07:10:00Z' },
      { to_status: 'in_progress', note: 'Emergency repair crew dispatched to isolate valve', created_at: '2026-09-28T07:45:00Z' },
    ],
  },
  {
    id: 'demo-report-3',
    public_code: 'ET-AA-2026-003',
    title: 'Fallen Telecommunication Cable Over Pedestrian Walkway',
    description: 'Severed overhead fiber lines sagging dangerously low across the pedestrian sidewalk.',
    category: 'Telecom',
    issue_type: 'Downed Line',
    severity: 3,
    status: 'resolved',
    city: 'Addis Ababa',
    latitude: 9.0321,
    longitude: 38.7523,
    address: 'Churchill Ave, Piassa, Addis Ababa',
    organization_name: 'Ethio telecom',
    is_demo: true,
    created_at: '2026-09-27T14:20:00Z',
    resolved_at: '2026-09-28T10:00:00Z',
    media: [],
    ai: {
      category: 'Telecom',
      issue_type: 'Downed Line',
      severity: 3,
      confidence: 0.91,
      confidence_band: 'high',
      urgency: 'medium',
      responsible_organization: 'Ethio telecom',
      reasoning: 'Non-energized communication cables obstructing pedestrian walkway.',
      model_name: 'CivicLens AI Vision',
      corrected: false,
    },
    history: [
      { to_status: 'submitted', note: 'Report submitted by citizen', created_at: '2026-09-27T14:20:00Z' },
      { to_status: 'assigned', note: 'Assigned to North Addis Maintenance Team', created_at: '2026-09-27T15:00:00Z' },
      { to_status: 'resolved', note: 'Line re-anchored and spliced. Walkway clear.', created_at: '2026-09-28T10:00:00Z' },
    ],
  },
]
