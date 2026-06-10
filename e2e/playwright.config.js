const { defineConfig, devices } = require('@playwright/test')

module.exports = defineConfig({
  testDir: './tests_js',
  testMatch: '**/*.spec.js',
  timeout: 30_000,
  retries: 0,
  reporter: [['line']],
  use: {
    baseURL: 'http://localhost:3000',
    screenshot: 'only-on-failure',
  },
  projects: [
    {
      name: 'chromium',
      use: {
        ...devices['Desktop Chrome'],
        launchOptions: { args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage'] },
      },
    },
  ],
})
