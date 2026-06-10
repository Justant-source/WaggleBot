import { test, expect } from '@playwright/test'

// ── Hamburger / Mobile Sidebar ──────────────────────────────────

test('hamburger button shows on mobile viewport', async ({ page }) => {
  // Use mobile viewport
  await page.setViewportSize({ width: 375, height: 667 })
  await page.goto('/admin/inbox')

  // Hamburger button should be visible on mobile
  const hamburger = page.locator('header button').filter({ has: page.locator('svg.lucide-menu') })
  await expect(hamburger).toBeVisible({ timeout: 5_000 })
})

test('hamburger button opens mobile sidebar', async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 667 })
  await page.goto('/admin/inbox')

  // Mobile overlay should not exist initially
  await expect(page.getByTestId('mobile-sidebar-overlay')).toHaveCount(0)

  // Click hamburger
  const hamburger = page.locator('header button').filter({ has: page.locator('svg.lucide-menu') })
  await hamburger.click()

  // Mobile overlay should now be visible
  await expect(page.getByTestId('mobile-sidebar-overlay')).toBeVisible({ timeout: 3_000 })
  await expect(page.getByTestId('mobile-sidebar-overlay').locator('aside')).toBeVisible({ timeout: 2_000 })
})

test('mobile sidebar closes when clicking backdrop', async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 667 })
  await page.goto('/admin/inbox')

  // Open the sidebar
  const hamburger = page.locator('header button').filter({ has: page.locator('svg.lucide-menu') })
  await hamburger.click()
  await expect(page.getByTestId('mobile-sidebar-overlay')).toBeVisible({ timeout: 3_000 })

  // Click the backdrop area (right side outside the 256px sidebar)
  await page.mouse.click(360, 200)
  await expect(page.getByTestId('mobile-sidebar-overlay')).toHaveCount(0, { timeout: 3_000 })
})

test('desktop sidebar is visible and has nav links', async ({ page }) => {
  // Desktop viewport
  await page.setViewportSize({ width: 1280, height: 800 })
  await page.goto('/admin/inbox')

  const sidebar = page.locator('aside').first()
  await expect(sidebar).toBeVisible()

  // Check nav links exist
  await expect(sidebar.locator('a[href="/admin/inbox"]')).toBeVisible()
  await expect(sidebar.locator('a[href="/admin/overview"]')).toBeVisible()
})

test('desktop sidebar collapse button works', async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 })
  await page.goto('/admin/inbox')

  const sidebar = page.locator('aside').first()
  await expect(sidebar).toBeVisible()

  // Sidebar should start expanded (w-64)
  await expect(sidebar).toHaveClass(/w-64/)

  // Click the collapse toggle (circle button with chevron icon)
  const collapseBtn = sidebar.locator('button').first()
  await collapseBtn.click()

  // Should collapse to w-16
  await expect(sidebar).toHaveClass(/w-16/, { timeout: 2_000 })
})

// ── Navigation ─────────────────────────────────────────────────

test('clicking overview nav link navigates to overview', async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 })
  await page.goto('/admin/inbox')

  await page.locator('a[href="/admin/overview"]').first().click()
  await expect(page).toHaveURL(/\/admin\/overview/, { timeout: 5_000 })
})

test('root path redirects to /admin/overview', async ({ page }) => {
  await page.goto('/')
  await expect(page).toHaveURL(/\/admin\/overview/, { timeout: 5_000 })
})
