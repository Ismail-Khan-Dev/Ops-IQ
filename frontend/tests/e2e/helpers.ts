import { expect, type Page } from '@playwright/test'

const API_KEY = process.env.OPSIQ_API_KEY || 'opsiq-dev-key-2024'

/**
 * Log in via the real BFF flow so the HttpOnly `opsiq_session` cookie is
 * issued server-side (same as a real user). Returns true on success.
 */
export async function loginAs(page: Page, apiKey: string = API_KEY): Promise<void> {
  await page.goto('/login')
  await page.locator('input[type="password"]').fill(apiKey)
  await page.locator('button:has-text("Access Command Center")').click()
  await page.waitForURL('**/', { timeout: 15_000 })
  await expect(page.locator('text=Command Center').first()).toBeVisible()
}