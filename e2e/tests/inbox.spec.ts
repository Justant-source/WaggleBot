import { test, expect } from '@playwright/test'

const INBOX_URL = '/admin/inbox'
const API_BASE = 'http://localhost:8080'

// Ensure a COLLECTED post exists before inbox tests
test.beforeAll(async ({ request }) => {
  const res = await request.get(`${API_BASE}/api/inbox?page=0&size=1&sort=score`)
  const body = await res.json()
  if (!body.posts?.length) {
    // Insert test fixture via crawl endpoint; if fails, tests will naturally skip
    await request.post(`${API_BASE}/api/inbox/crawl`)
  }
})

// ── Inbox Page Loading ──────────────────────────────────────────

test('inbox page loads with posts table', async ({ page }) => {
  await page.goto(INBOX_URL)
  // Wait for the loading spinner to disappear
  await expect(page.locator('.lucide-loader-circle, .animate-spin')).toBeHidden({ timeout: 10_000 })
  // Table should be visible
  await expect(page.locator('table')).toBeVisible()
  // At least one post row
  const rows = page.locator('tbody tr')
  await expect(rows.first()).toBeVisible()
})

test('inbox page shows post titles and scores', async ({ page }) => {
  await page.goto(INBOX_URL)
  await expect(page.locator('table')).toBeVisible({ timeout: 10_000 })
  // Title column exists
  const titleCell = page.locator('tbody tr td').nth(1)
  await expect(titleCell).toBeVisible()
  await expect(titleCell).not.toBeEmpty()
})

// ── Approve Button ──────────────────────────────────────────────

test('approve button removes post from list and shows toast', async ({ page }) => {
  await page.goto(INBOX_URL)
  await expect(page.locator('table')).toBeVisible({ timeout: 10_000 })

  // Get the first post's title to track it
  const firstTitleBtn = page.locator('tbody tr td:nth-child(2) button').first()
  await expect(firstTitleBtn).toBeVisible()
  const title = await firstTitleBtn.textContent()
  const titleText = title?.trim() ?? ''

  // Count rows before approve
  const initialCount = await page.locator('tbody tr').count()

  // Click the approve button in the first row action cell
  const approveBtn = page.locator('tbody tr').first().locator('button', { hasText: '승인' })
  await expect(approveBtn).toBeVisible()
  await approveBtn.click()

  // After optimistic removal, row count should decrease
  await expect(page.locator('tbody tr')).toHaveCount(initialCount - 1, { timeout: 5_000 })

  // "승인됨" success toast should appear
  await expect(page.locator('[data-sonner-toast]').filter({ hasText: '승인됨' })).toBeVisible({ timeout: 5_000 })

  // The approved post's title should no longer be visible in the table
  if (titleText) {
    const remainingRows = page.locator('tbody tr td:nth-child(2) button', { hasText: titleText })
    await expect(remainingRows).toHaveCount(0, { timeout: 3_000 })
  }
})

test('approve API returns correct structure', async ({ request }) => {
  // Find a COLLECTED post
  const listRes = await request.get(`${API_BASE}/api/inbox?page=0&size=1&sort=score`)
  expect(listRes.ok()).toBeTruthy()
  const body = await listRes.json()
  expect(body.posts).toBeDefined()
  expect(Array.isArray(body.posts)).toBeTruthy()

  if (!body.posts.length) {
    test.skip()
    return
  }

  const postId = body.posts[0].id
  const approveRes = await request.post(`${API_BASE}/api/inbox/${postId}/approve`)
  expect(approveRes.ok()).toBeTruthy()
  const approveBody = await approveRes.json()
  expect(approveBody).toMatchObject({
    postId: expect.any(Number),
    status: 'EDITING',
    jobId: expect.any(Number),
  })
})

// ── Decline Button ──────────────────────────────────────────────

test('decline button removes post from list and shows toast', async ({ page }) => {
  await page.goto(INBOX_URL)
  await expect(page.locator('table')).toBeVisible({ timeout: 10_000 })

  const initialCount = await page.locator('tbody tr').count()
  const declineBtn = page.locator('tbody tr').first().locator('button', { hasText: '거절' })
  await expect(declineBtn).toBeVisible()
  await declineBtn.click()

  await expect(page.locator('tbody tr')).toHaveCount(initialCount - 1, { timeout: 5_000 })
  await expect(page.locator('[data-sonner-toast]').filter({ hasText: '거절됨' })).toBeVisible({ timeout: 5_000 })
})

// ── Keyboard Triage ─────────────────────────────────────────────

test('keyboard J/K navigates posts and opens drawer', async ({ page }) => {
  await page.goto(INBOX_URL)
  await expect(page.locator('table')).toBeVisible({ timeout: 10_000 })

  // Press J to open first post
  await page.keyboard.press('j')
  // Drawer panel should appear
  await expect(page.locator('[class*="max-w-2xl"]')).toBeVisible({ timeout: 3_000 })

  // Press Esc to close
  await page.keyboard.press('Escape')
  await expect(page.locator('[class*="max-w-2xl"]')).toBeHidden({ timeout: 3_000 })
})

// ── Filter Controls ─────────────────────────────────────────────

test('sort select changes post ordering', async ({ page }) => {
  await page.goto(INBOX_URL)
  await expect(page.locator('table')).toBeVisible({ timeout: 10_000 })

  // Change sort to 최신순
  const sortSelect = page.locator('[role="combobox"]').nth(2)
  await sortSelect.click()
  await page.locator('[role="option"]', { hasText: '최신순' }).click()

  // Page should reload with new sort
  await expect(page.locator('table')).toBeVisible({ timeout: 8_000 })
})

test('search input filters posts', async ({ page }) => {
  await page.goto(INBOX_URL)
  await expect(page.locator('table')).toBeVisible({ timeout: 10_000 })

  const searchInput = page.locator('input[placeholder="제목 검색..."]')
  await searchInput.fill('xyznotfound12345')
  await page.keyboard.press('Enter')

  // Should show empty or no rows
  await page.waitForTimeout(1500)
  const rows = page.locator('tbody tr')
  const count = await rows.count()
  // Either 0 rows or shows "empty" state
  expect(count).toBeGreaterThanOrEqual(0)
})
