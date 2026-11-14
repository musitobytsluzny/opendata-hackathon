import { defineConfig } from '@playwright/test'

export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  workers: 1,
  use: {
    baseURL: 'http://127.0.0.1:4173',
    viewport: { width: 1440, height: 1000 },
    actionTimeout: 8000,
    screenshot: 'only-on-failure',
    reducedMotion: 'reduce',
    launchOptions: {
      executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH || undefined,
      args: ['--enable-webgl', '--use-gl=angle', '--use-angle=swiftshader'],
    },
  },
  webServer: {
    command: 'npm run preview -- --host 127.0.0.1 --port 4173 --strictPort',
    url: 'http://127.0.0.1:4173',
    reuseExistingServer: !process.env.CI,
  },
})
