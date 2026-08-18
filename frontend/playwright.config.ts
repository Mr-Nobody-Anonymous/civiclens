import { defineConfig } from '@playwright/test'

export default defineConfig({
  testDir: './e2e',
  timeout: 60_000,
  expect: { timeout: 15_000 },
  workers: 1,                 // tests share one backend; run sequentially
  retries: 1,
  reporter: [['list']],
  globalSetup: './e2e/global-setup.ts',
  use: {
    baseURL: process.env.E2E_BASE_URL || 'http://localhost:5173',
    ignoreHTTPSErrors: true,  // production smoke run uses a self-signed cert
    permissions: ['geolocation'],
    geolocation: { latitude: 9.0108, longitude: 38.7613 },  // Addis Ababa
    locale: 'en-US',
    video: 'off',
    trace: 'retain-on-failure',
  },
})
