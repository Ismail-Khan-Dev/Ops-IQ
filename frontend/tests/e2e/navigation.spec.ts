import { test, expect } from '@playwright/test'
import { loginAs } from './helpers'

const BASE = process.env.BASE_URL || 'http://localhost:3200'

test.beforeEach(async ({ page }) => {
  await loginAs(page)
})

test.describe('Login Page', () => {
  test('renders login page with OpsIQ branding', async ({ page }) => {
    await page.goto(`${BASE}/login`)
    await expect(page.locator('text=OpsIQ').first()).toBeVisible()
    await expect(page.locator('text=Enter API Key')).toBeVisible()
  })

  test('has API key input and submit button', async ({ page }) => {
    await page.goto(`${BASE}/login`)
    await expect(page.locator('input[type="password"]')).toBeVisible()
    await expect(page.locator('button:has-text("Access Command Center")')).toBeVisible()
  })
})

test.describe('Dashboard', () => {
  test('renders command center dashboard', async ({ page }) => {
    await expect(page.locator('text=Command Center').first()).toBeVisible()
    await expect(page.locator('text=Financial Impact').first()).toBeVisible()
    await expect(page.locator('text=Decisions Made').first()).toBeVisible()
  })

  test('shows pending approvals section', async ({ page }) => {
    await page.goto(`${BASE}/`)
    await expect(page.locator('text=Pending Approvals')).toBeVisible()
  })

  test('shows agent fleet status', async ({ page }) => {
    await page.goto(`${BASE}/`)
    await expect(page.locator('text=Agent Fleet Status')).toBeVisible()
  })
})

test.describe('Navigation', () => {
  test('sidebar links are visible and navigable', async ({ page }) => {
    await page.goto(`${BASE}/`)
    await page.waitForSelector('nav a', { timeout: 10000 })

    await expect(page.getByRole('link', { name: 'Dashboard', exact: true })).toBeVisible()
    await expect(page.getByRole('link', { name: 'Agents', exact: true })).toBeVisible()
    await expect(page.getByRole('link', { name: 'Orders', exact: true })).toBeVisible()
    await expect(page.getByRole('link', { name: 'Analytics', exact: true })).toBeVisible()
  })

  test('navigates to agents page', async ({ page }) => {
    await page.goto(`${BASE}/`)
    await page.waitForSelector('nav a', { timeout: 10000 })
    await page.getByRole('link', { name: 'Agents', exact: true }).click()
    await page.waitForURL('**/agents', { timeout: 10000 })
    await expect(page).toHaveURL(/\/agents/)
    await expect(page.locator('text=Autonomous Agents')).toBeVisible()
  })

  test('navigates to orders page', async ({ page }) => {
    await page.goto(`${BASE}/`)
    await page.waitForSelector('nav a', { timeout: 10000 })
    await page.getByRole('link', { name: 'Orders', exact: true }).click()
    await page.waitForURL('**/orders', { timeout: 10000 })
    await expect(page).toHaveURL(/\/orders/)
  })

  test('navigates to analytics page', async ({ page }) => {
    await page.goto(`${BASE}/`)
    await page.waitForSelector('nav a', { timeout: 10000 })
    await page.getByRole('link', { name: 'Analytics', exact: true }).click()
    await page.waitForURL('**/analytics', { timeout: 10000 })
    await expect(page).toHaveURL(/\/analytics/)
    await expect(page.locator('text=Performance Intelligence')).toBeVisible()
  })

  test('navigates to products page', async ({ page }) => {
    await page.goto(`${BASE}/`)
    await page.waitForSelector('nav a', { timeout: 10000 })
    await page.getByRole('link', { name: 'Products', exact: true }).click()
    await page.waitForURL('**/products', { timeout: 10000 })
    await expect(page).toHaveURL(/\/products/)
    await expect(page.locator('text=Product Catalog')).toBeVisible()
  })

  test('navigates to security page', async ({ page }) => {
    await page.goto(`${BASE}/`)
    await page.waitForSelector('nav a', { timeout: 10000 })
    await page.getByRole('link', { name: 'Security', exact: true }).click()
    await page.waitForURL('**/security', { timeout: 10000 })
    await expect(page).toHaveURL(/\/security/)
    await expect(page.locator('text=Security Operations')).toBeVisible()
  })

  test('navigates to settings page', async ({ page }) => {
    await page.goto(`${BASE}/`)
    await page.waitForSelector('nav a', { timeout: 10000 })
    await page.getByRole('link', { name: 'Settings', exact: true }).click()
    await page.waitForURL('**/settings', { timeout: 10000 })
    await expect(page).toHaveURL(/\/settings/)
    await expect(page.locator('text=System Settings')).toBeVisible()
  })

  test('navigates to cart recovery page', async ({ page }) => {
    await page.goto(`${BASE}/`)
    await page.waitForSelector('nav a', { timeout: 10000 })
    await page.getByRole('link', { name: 'Cart Recovery', exact: true }).click()
    await page.waitForURL('**/cart-recovery', { timeout: 10000 })
    await expect(page).toHaveURL(/\/cart-recovery/)
  })

  test('navigates to support page', async ({ page }) => {
    await page.goto(`${BASE}/`)
    await page.waitForSelector('nav a', { timeout: 10000 })
    await page.getByRole('link', { name: 'Support', exact: true }).click()
    await page.waitForURL('**/support', { timeout: 10000 })
    await expect(page).toHaveURL(/\/support/)
  })

  test('navigates to reviews page', async ({ page }) => {
    await page.goto(`${BASE}/`)
    await page.waitForSelector('nav a', { timeout: 10000 })
    await page.getByRole('link', { name: 'Reviews', exact: true }).click()
    await page.waitForURL('**/reviews', { timeout: 10000 })
    await expect(page).toHaveURL(/\/reviews/)
  })
})

test.describe('404 Page', () => {
  test('shows 404 for unknown routes', async ({ page }) => {
    await page.goto(`${BASE}/nonexistent-page`)
    await expect(page.locator('text=Page Not Found')).toBeVisible()
    await expect(page.locator('text=404')).toBeVisible()
  })
})
