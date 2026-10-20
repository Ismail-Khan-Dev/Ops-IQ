import { test, expect } from '@playwright/test'
import { loginAs } from './helpers'

const BASE = process.env.BASE_URL || 'http://localhost:3200'

test.describe('Smoke: Health', () => {
  test('BFF health proxy returns real backend status', async ({ request }) => {
    const resp = await request.get(`${BASE}/api/v1/health`)
    expect(resp.ok()).toBeTruthy()
    const body = await resp.json()
    expect(body).toHaveProperty('status')
    expect(body).toHaveProperty('dependencies')
    expect(body).toHaveProperty('version_number')
  })
})

test.describe('Smoke: Login flow', () => {
  test('login page renders and validates input', async ({ page }) => {
    await page.goto(`${BASE}/login`)
    await expect(page.locator('text=OpsIQ').first()).toBeVisible()
    await expect(page.locator('input[type="password"]')).toBeVisible()
    const submit = page.locator('button:has-text("Access Command Center")')
    await expect(submit).toBeDisabled()

    await page.locator('input[type="password"]').fill('x')
    await expect(submit).toBeEnabled()
  })

  test('unauthenticated visitors are redirected to login', async ({ page }) => {
    await page.goto(`${BASE}/`)
    await page.waitForURL('**/login', { timeout: 10_000 })
  })

  test('login succeeds with a valid API key and reaches dashboard', async ({ page }) => {
    await loginAs(page)
  })
})

test.describe('Smoke: Dashboard', () => {
  test.beforeEach(async ({ page }) => {
    await loginAs(page)
  })

  test('renders Command Center with real metric labels', async ({ page }) => {
    await expect(page.locator('text=Command Center').first()).toBeVisible()
    await expect(page.locator('text=Financial Impact').first()).toBeVisible()
    await expect(page.locator('text=Decisions Made').first()).toBeVisible()
  })

  test('renders pending approvals and agent fleet sections', async ({ page }) => {
    await expect(page.locator('text=Pending Approvals')).toBeVisible()
    await expect(page.locator('text=Agent Fleet Status')).toBeVisible()
  })

  test('shows backend health card status', async ({ page }) => {
    await expect(page.locator('text=System Health')).toBeVisible()
  })
})