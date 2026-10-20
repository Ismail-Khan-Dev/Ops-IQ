import { test, expect } from '@playwright/test'
import { loginAs } from './helpers'

const BASE = process.env.BASE_URL || 'http://localhost:3200'

test.beforeEach(async ({ page }) => {
  await loginAs(page)
})

test.describe('Agents Page', () => {
  test('renders agent fleet with all agent types', async ({ page }) => {
    await page.goto(`${BASE}/agents`)
    await expect(page.locator('text=Autonomous Agents')).toBeVisible()

    const agents = [
      'Fraud Detection',
      'Inventory',
      'Price Optimizer',
      'Review Moderator',
      'Marketing',
      'Cart Recovery',
      'Customer Support',
    ]

    for (const agent of agents) {
      await expect(page.locator(`text=${agent}`).first()).toBeVisible()
    }
  })
})

test.describe('Analytics Page', () => {
  test('renders analytics dashboard', async ({ page }) => {
    await page.goto(`${BASE}/analytics`)
    await expect(page.locator('text=Performance Intelligence')).toBeVisible()
  })
})

test.describe('Settings Page', () => {
  test('renders settings panel', async ({ page }) => {
    await page.goto(`${BASE}/settings`)
    await expect(page.locator('text=System Settings')).toBeVisible()
  })
})

test.describe('Error Boundaries', () => {
  test('login page handles invalid input gracefully', async ({ page }) => {
    await page.goto(`${BASE}/login`)
    const submit = page.locator('button:has-text("Access Command Center")')
    await submit.click()
    await expect(page.locator('input[type="password"]')).toBeVisible()
  })
})
