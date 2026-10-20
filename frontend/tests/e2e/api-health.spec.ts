import { test, expect } from '@playwright/test'
import { loginAs } from './helpers'

const BASE = process.env.BASE_URL || 'http://localhost:3200'

test.describe('API Health', () => {
  test('health endpoint returns 200', async ({ request }) => {
    const resp = await request.get(`${BASE}/api/v1/health`)
    expect(resp.ok()).toBeTruthy()
  })

  test('health response includes status field', async ({ request }) => {
    const resp = await request.get(`${BASE}/api/v1/health`)
    const body = await resp.json()
    expect(body).toHaveProperty('status')
    expect(body).toHaveProperty('dependencies')
  })
})

test.describe('Dashboard Metrics', () => {
  test.beforeEach(async ({ page }) => {
    await loginAs(page)
  })

  test('dashboard renders KPI cards', async ({ page }) => {
    await expect(page.locator('text=Financial Impact').first()).toBeVisible()
    await expect(page.locator('text=Decisions Made').first()).toBeVisible()
    await expect(page.locator('text=Pending Reviews').first()).toBeVisible()
    await expect(page.locator('text=Flagged Orders').first()).toBeVisible()
  })

  test('dashboard shows live agent status', async ({ page }) => {
    await expect(page.locator('text=Agent Fleet Status')).toBeVisible()
  })
})

test.describe('Accessibility', () => {
  test.beforeEach(async ({ page }) => {
    await loginAs(page)
  })

  test('page has no duplicate IDs on dashboard', async ({ page }) => {
    await page.waitForSelector('main', { timeout: 10000 })

    const ids = await page.evaluate(() => {
      const els = document.querySelectorAll('[id]')
      return Array.from(els).map(el => el.id)
    })
    const dupes = ids.filter((id, i) => ids.indexOf(id) !== i)
    expect(dupes).toEqual([])
  })
})
