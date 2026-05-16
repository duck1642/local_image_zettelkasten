import { defineConfig, devices } from '@playwright/test';

const viteCommand = 'node ./node_modules/vite/bin/vite.js --host 127.0.0.1 --port 5173';
const webServer = process.env.PW_SKIP_WEBSERVER ? undefined : {
  command: viteCommand,
  url: 'http://127.0.0.1:5173',
  reuseExistingServer: !process.env.CI,
  timeout: 120_000,
  gracefulShutdown: { signal: 'SIGINT' as const, timeout: 5000 }
};

export default defineConfig({
  testDir: '../tests/frontend',
  timeout: 60_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  reporter: [['list']],
  use: {
    baseURL: 'http://127.0.0.1:5173',
    trace: 'on-first-retry'
  },
  webServer,
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] }
    }
  ]
});
