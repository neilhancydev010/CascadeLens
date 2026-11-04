import { defineConfig, devices } from '@playwright/test'

// `real` runs the production build under its offline CSP. `fixture` runs the NISAR path on invented data.
// Needs `npm run build` and `python tests/integration/build_fixture.py` first. Uses the system Edge, so nothing is downloaded.
// Set CL_BASE_URL to test an already-running packaged product instead: then only `real` runs, against that server.
// Set CL_BROWSER_PATH to run in another Chromium browser, such as Brave.
const executablePath = process.env.CL_BROWSER_PATH
const browser = { ...devices['Desktop Edge'], ...(executablePath ? { launchOptions: { executablePath } } : { channel: 'msedge' as const }), viewport: { width: 1440, height: 900 } }
const packaged = process.env.CL_BASE_URL

export default defineConfig({
  testDir: 'e2e',
  fullyParallel: false,
  workers: 1,
  timeout: 45_000,
  reporter: 'list',
  use: { trace: 'off' },
  projects: [
    { name: 'real', testMatch: 'real.spec.ts', use: { ...browser, baseURL: packaged ?? 'http://localhost:4173' } },
    ...(packaged ? [] : [{ name: 'fixture', testMatch: 'fixture.spec.ts', use: { ...browser, baseURL: 'http://localhost:5199' } }]),
  ],
  webServer: packaged ? undefined : [
    { command: 'npm run preview -- --port 4173 --strictPort', port: 4173, reuseExistingServer: true },
    { command: 'npm run dev:fixture', port: 5199, reuseExistingServer: true },
  ],
})
