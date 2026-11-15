import { readFileSync, writeFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { pathToFileURL } from 'node:url'
import AxeBuilder from '@axe-core/playwright'
import { expect, test, type ConsoleMessage, type Page } from '@playwright/test'

// The production build with its real data, served under a CSP that blocks every request off this origin.
// Screenshots go to the gitignored test-results folder. To refresh the documentation pictures on purpose, run with
// CL_SCREENSHOTS_DIR=../docs/screenshots, look at them, and commit them as a change of their own.
const SHOTS = process.env.CL_SCREENSHOTS_DIR ?? 'test-results/screenshots'
const TSHO = '/?case=tsho-rolpa-2026'
declare global { interface Window { __clMap: import('maplibre-gl').Map } }

async function open(page: Page, path = '/') {
  await page.goto(path)
  await expect(page.locator('.map-state')).toHaveText('Map ready')
}

const inspector = (page: Page) => page.locator('.inspector')

async function inspect(page: Page, bookmark: string) {
  await page.getByRole('button', { name: bookmark }).click()
  await page.getByRole('tab', { name: 'Inspector' }).click()
  await expect(inspector(page)).toContainText(bookmark)
  await expect(inspector(page)).not.toHaveAttribute('data-state', 'loading')
}

test('opening index.html directly explains what to do, instead of a blank page', async ({ page }) => {
  await page.goto(pathToFileURL(resolve('dist/index.html')).href)
  await expect(page.getByRole('heading', { name: 'GAIA CascadeLens has not started' })).toBeVisible()
  await expect(page.getByText('Start CascadeLens.bat')).toBeVisible()
  await expect(page.getByText('http://localhost:8765')).toBeVisible()
})

test('a normal start never shows that message', async ({ page }) => {
  await open(page)
  await page.waitForTimeout(2300)
  await expect(page.getByRole('heading', { name: 'GAIA CascadeLens has not started' })).toHaveCount(0)
})

test('on a web address, a slow start says it is loading and never points to Start CascadeLens.bat', async ({ page }) => {
  await page.route(/\/assets\/index-[^/]+\.js$/, (r) => r.abort()) // The app's script never arrives, as on a stalled connection
  await page.goto('/')
  await expect(page.getByRole('heading', { name: 'Loading GAIA CascadeLens…' })).toBeVisible()
  await page.waitForTimeout(2300)
  await expect(page.getByText('Start CascadeLens.bat')).toHaveCount(0)
  await expect(page.getByRole('heading', { name: 'GAIA CascadeLens has not started' })).toHaveCount(0)
})

test('the page has a real icon', async ({ page, request }) => {
  await open(page)
  const href = await page.locator('link[rel="icon"]').getAttribute('href')
  expect(href).toBe('./favicon.svg')
  expect((await request.get('/favicon.svg')).headers()['content-type']).toContain('svg')
})

test('About explains the project and names its NASA data with evidence classes', async ({ page }) => {
  await open(page)
  await page.getByRole('button', { name: 'Project & NASA data' }).first().click()
  const about = page.getByRole('dialog', { name: 'About CascadeLens and its NASA data' })
  await expect(about).toContainText('NISAR GUNW and GOFF')
  await expect(about).toContainText('GPM IMERG')
  await expect(about).toContainText('Claude, an AI assistant made by Anthropic')
  await expect(about).toContainText('not a warning system')
  await expect(about).not.toContainText(/early warning|proves/i)
  await expect(about.locator('.evidence').first()).toHaveText('Observed')
  expect((await new AxeBuilder({ page }).include('.about-project').analyze()).violations).toEqual([])
  await page.keyboard.press('Escape')
  await expect(about).toHaveCount(0)
})

test('opens on Rasuwa with real NISAR measurements', async ({ page }) => {
  const tiles: string[] = []
  page.on('response', (r) => { if (r.url().includes('/tiles/pair-a/')) tiles.push(`${r.status()}`) })
  await open(page)
  await expect(page.getByRole('heading', { name: 'Rasuwa–Bhote Koshi–Trishuli, Nepal' })).toBeVisible()
  await expect(page.getByRole('radio', { name: /Unwrapped phase/ })).toBeChecked()
  await expect(page.locator('.fixture-banner')).toHaveCount(0)
  await expect.poll(() => tiles.length).toBeGreaterThan(3)
  expect(tiles.filter((s) => s !== '200' && s !== '404')).toEqual([])
  await expect(page.locator('.source')).toContainText('Provisional (P05023)')
  await expect(page.locator('.legend-title').first()).toContainText('relative to frame median')
  await page.waitForTimeout(600)
  await page.screenshot({ path: `${SHOTS}/overview.png` })
})

test('every product has an honest status', async ({ page }) => {
  await open(page)
  await expect(page.getByRole('radio', { name: /19–31 August 2026/ })).toBeEnabled()
  await page.getByRole('tab', { name: 'Snapshots' }).click()
  // Four GCOV snapshots are downloaded and readable; 31 August is only listed in the catalogue, so it cannot be picked
  await expect(page.getByRole('radio', { name: /16 August 2026/ })).toBeChecked()
  await expect(page.getByRole('radio', { name: /Gamma-0 backscatter/ })).toBeEnabled()
  await expect(page.getByRole('radio', { name: /31 August 2026/ })).toBeDisabled()
  await expect(page.locator('label', { has: page.getByRole('radio', { name: /31 August 2026/ }) })).toContainText('Not validated yet')
})

test('the inspector reads real NISAR values and refuses the swath gap', async ({ page }) => {
  await open(page)
  await page.getByRole('radio', { name: /Coherence magnitude/ }).check()
  await inspect(page, 'Bhote Koshi corridor')
  await expect(inspector(page)).toHaveAttribute('data-state', 'valid')
  await expect(page.locator('.value')).toContainText('0.21492')
  await expect(inspector(page)).toContainText('at Shyaphru Bensi')
  await page.waitForTimeout(1500)
  await page.screenshot({ path: `${SHOTS}/corridor-coherence.png` })
  await inspect(page, 'Mountain source area')
  await expect(inspector(page)).toHaveAttribute('data-state', 'masked')
  await expect(page.locator('.sample')).toContainText('Masked measurement')
})

test('Pair B reaches the source that Pair A cannot', async ({ page }) => {
  await open(page)
  await page.getByRole('tab', { name: 'Pixel offsets' }).click()
  await page.getByRole('radio', { name: /19–31 August 2026/ }).check()
  await page.getByRole('radio', { name: /Correlation surface peak/ }).check()
  await inspect(page, 'Mountain source area')
  await expect(inspector(page)).toHaveAttribute('data-state', 'valid')
  await expect(inspector(page)).toContainText('ascending, Track 98, frame 16')
})

test('Track 98 coherence reaches the source, and each viewing direction is judged on its own', async ({ page }) => {
  await open(page)
  await page.getByRole('radio', { name: /19–31 August 2026/ }).check()
  await page.getByRole('radio', { name: /Coherence magnitude/ }).check()
  await inspect(page, 'Mountain source area')
  await expect(inspector(page)).toHaveAttribute('data-state', 'valid')
  await expect(inspector(page)).toContainText('Track 98')
  const views = page.locator('.obs-at .obs-view')
  await expect(views).toHaveCount(2)
  await expect(views.nth(0).locator('h4')).toHaveText('Track 48, descending, frames 74 and 75')
  await expect(views.nth(1).locator('h4')).toHaveText('Track 98, ascending, frame 16')
  for (const v of [views.nth(0), views.nth(1)]) await expect(v.locator('.obs-tasks li')).toHaveCount(2)
  await expect(page.locator('.obs-at')).toContainText('Each viewing direction is judged on its own')
})

test('the explanations read Track 98 where Track 48 cannot see, and label each check with its track', async ({ page }) => {
  await open(page)
  await page.getByRole('button', { name: 'Mountain source area' }).click()
  await page.getByRole('tab', { name: 'Inspector' }).click()
  const panel = page.locator('.hypotheses')
  await expect(panel.locator('.hyp').first()).toBeVisible({ timeout: 20000 })
  await expect(panel).not.toContainText('No NISAR explanation')
  await expect(panel.locator('.hyp-views')).toContainText('Track 48 (descending): cannot judge this spot')
  await expect(panel.locator('.hyp-views')).toContainText('Track 98 (ascending): coherence')
  await expect(panel.locator('.hyp-measured')).toContainText('Coherence, Track 98 (ascending)')
})

test('completes the story with the outside world blocked', async ({ page }) => {
  const errors: string[] = []
  const external: string[] = []
  const onConsole = (m: ConsoleMessage) => { if (m.type() === 'error' && !m.text().includes('404')) errors.push(m.text()) }
  page.on('console', onConsole)
  page.on('pageerror', (e) => errors.push(e.message))
  page.on('request', (r) => { if (new URL(r.url()).hostname !== 'localhost') external.push(r.url()) })
  await open(page)
  await page.getByRole('button', { name: 'Start the guided story' }).click()
  await expect(page.locator('.story')).toContainText('quality mask flags it there')
  await expect(page.locator('.story')).toContainText('at the detachment zone against')
  await page.getByRole('button', { name: 'Next' }).click()
  await expect(page.locator('.story')).toContainText('much lower than on the terrain beside it')
  await page.getByRole('button', { name: 'Next' }).click()
  await expect(page.getByRole('heading', { name: '3. Can the radar see it?' })).toBeVisible()
  await page.getByRole('button', { name: 'Next' }).click()
  await expect(page.getByRole('heading', { name: '4. The downstream corridor' })).toBeVisible()
  await page.getByRole('button', { name: 'Next' }).click()
  await expect(page.locator('.story')).toContainText('No displacement is calculated')
  await expect(page.locator('.story')).toContainText('from the ionosphere')
  await page.getByRole('button', { name: 'Explore the map' }).click()
  await page.getByRole('button', { name: 'Bhote Koshi corridor' }).click()
  await page.getByRole('tab', { name: 'Inspector' }).click()
  await expect(inspector(page)).toHaveAttribute('data-state', /valid|masked/) // Ionosphere-removed phase at this pixel did not unwrap reliably
  expect(external).toEqual([])
  expect(errors).toEqual([])
  const probe = await page.evaluate(() => fetch('https://example.com/', { mode: 'no-cors' }).then(() => 'reached', () => 'blocked'))
  expect(probe).toBe('blocked')
})

test('all three simulations run and stay labelled as illustrations', async ({ page }) => {
  const errors: string[] = []
  page.on('pageerror', (e) => errors.push(e.message))
  await open(page)
  await page.getByRole('button', { name: 'Simulate' }).click()
  const panel = page.locator('.sim-panel')
  await expect(panel).toContainText('Illustration only')
  await expect(page.locator('.sim-head')).toBeVisible()
  await panel.getByRole('button', { name: 'Play' }).click()
  await expect(panel).toContainText(/[1-9]\d* of 198 km/)
  await panel.getByRole('button', { name: 'Pause' }).click()
  await panel.getByRole('tab', { name: 'What-if flood' }).click()
  await expect(panel).toContainText('not a forecast')
  await expect(panel).toContainText('Places below the water')
  await page.waitForTimeout(1500) // The tab's content fades in: wait so the picture shows it
  // The pointer is still on the tab it just clicked, and the tab's label must stay readable there
  const tab = panel.getByRole('tab', { name: 'What-if flood' })
  expect(await tab.evaluate((e) => { const s = getComputedStyle(e); return s.color !== s.backgroundColor })).toBe(true)
  await page.screenshot({ path: `${SHOTS}/simulate-whatif.png` })
  await panel.getByRole('tab', { name: 'Radar explainer' }).click()
  await expect(panel).toContainText('This model')
  await expect(page.locator('.sim-head')).toHaveCount(0)
  await page.getByRole('button', { name: 'Exit simulation' }).click()
  await expect(panel).toHaveCount(0)
  await expect(page.getByRole('tab', { name: 'Interpretation' })).toBeVisible()
  expect(errors).toEqual([])
})

test('a bookmark selects a named place and reads its real elevation', async ({ page }) => {
  await open(page)
  await page.getByRole('radio', { name: /Terrain elevation/ }).check()
  await inspect(page, 'Bhote Koshi corridor')
  await expect(page.locator('.place-chip')).toHaveText('Bhote Koshi corridor')
  await expect(page.locator('.value')).toHaveText('1446 m') // NASADEM heights are whole metres; rasterio reads 1446 at this pixel
})

test('Sentinel-1 layers stay separate from NISAR and cannot be sampled', async ({ page }) => {
  await open(page)
  await page.getByRole('button', { name: 'Bhote Koshi corridor' }).click()
  const tile = page.waitForResponse((r) => r.url().includes('/tiles/context/eos_dpm/') && r.status() === 200)
  await page.getByRole('checkbox', { name: /damage proxy/ }).check()
  await tile
  await expect(page.locator('.legend')).toContainText('More change')
  await page.getByRole('button', { name: /About Sentinel-1 damage proxy/ }).click()
  await expect(page.getByRole('heading', { name: /damage proxy map/i })).toBeVisible()
  await expect(page.locator('.limits')).toContainText('Not NISAR')
  await expect(page.locator('.limits')).toContainText('cannot sample it')
  await expect(page.locator('.credits summary')).toContainText('Sentinel-1')
  await page.getByRole('button', { name: /^Back to/ }).click()
  await expect(page.getByRole('heading', { name: 'Unwrapped phase' })).toBeVisible()
})

test('source details are reachable for every reference layer', async ({ page }) => {
  await open(page)
  const about = page.getByRole('button', { name: /^About / })
  const n = await about.count()
  expect(n).toBeGreaterThan(10)
  for (let i = 0; i < n; i++) {
    await about.nth(i).click()
    await expect(page.locator('.attribution').first()).not.toBeEmpty()
    await expect(page.locator('.limits li').first()).toBeVisible()
  }
})

test('has no serious accessibility violations', async ({ page }) => {
  const scan = async () => {
    const { violations } = await new AxeBuilder({ page }).exclude('.maplibregl-canvas-container').analyze()
    return violations.filter((v) => v.impact === 'serious' || v.impact === 'critical').map((v) => `${v.id}: ${v.nodes.map((n) => n.target).join(', ')}`)
  }
  await open(page)
  expect(await scan()).toEqual([])
  await page.getByRole('button', { name: 'Start the guided story' }).click()
  expect(await scan()).toEqual([])
  await open(page, TSHO)
  expect(await scan()).toEqual([])
})

test('every control can be reached and used from the keyboard', async ({ page }) => {
  await open(page)
  const b = page.getByRole('button', { name: 'Mountain source area' })
  await b.focus()
  await page.keyboard.press('Enter')
  await expect(b).toHaveAttribute('aria-pressed', 'true')
  const box = page.getByRole('checkbox', { name: /barrier lakes/ })
  await box.focus()
  await page.keyboard.press('Space')
  await expect(box).toBeChecked()
})

test('switching case moves between Tsho Rolpa and Rasuwa', async ({ page }) => {
  await open(page, TSHO)
  await expect(page.getByRole('heading', { name: /Tsho Rolpa/ }).first()).toBeVisible()
  await page.waitForTimeout(1500)
  await page.screenshot({ path: `${SHOTS}/tsho-rolpa.png` })
  await page.getByLabel('Case study').selectOption('rasuwa-2026')
  await expect(page.getByRole('heading', { name: 'Rasuwa–Bhote Koshi–Trishuli, Nepal' })).toBeVisible()
})

test.describe('phone', () => {
  test.use({ viewport: { width: 375, height: 812 }, hasTouch: true, isMobile: false })

  test('stays usable with collapsed panels', async ({ page }) => {
    await open(page)
    await expect(page.locator('.left')).toBeHidden()
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    await page.getByRole('button', { name: 'Layers' }).click()
    await expect(page.locator('.left')).toBeVisible()
    // The top bar's case menu and status button do not fit on a phone, so the sheet carries them
    await expect(page.getByLabel('Change case')).toBeVisible()
    await expect(page.locator('.left').getByRole('button', { name: 'What is real here?' })).toBeVisible()
    await page.getByRole('button', { name: 'Start the guided story' }).click()
    await expect(page.locator('.left')).toBeHidden()
    await expect(page.locator('.story')).toBeVisible()
    await expect(page.locator('.story')).toContainText('The source')
    await page.waitForTimeout(1500)
    // The step describes the detachment zone, so its marker must sit in the strip of map the sheet leaves free.
    const marker = await page.locator('.point-marker').boundingBox()
    const sheet = await page.locator('.story').boundingBox()
    expect(marker!.y + marker!.height).toBeLessThan(sheet!.y)
    expect(marker!.y).toBeGreaterThan(64)
    await page.screenshot({ path: `${SHOTS}/phone-story.png` })
    for (const b of await page.locator('.top-actions button, .story button').all()) {
      if (!(await b.isVisible())) continue // hidden at phone width, so not a tap target
      const h = (await b.boundingBox())?.height ?? 0
      if (await b.evaluate((e) => !e.classList.contains('link'))) expect(h).toBeGreaterThanOrEqual(32)
    }
  })
})

test('records performance', async ({ page }) => {
  await page.goto('/')
  const started = Date.now()
  await expect(page.locator('.map-state')).toHaveText('Map ready')
  const mapReady = Date.now() - started
  await page.getByRole('radio', { name: /Coherence magnitude/ }).check()
  const t1 = Date.now()
  await page.getByRole('button', { name: 'Bhote Koshi corridor' }).click()
  await page.getByRole('tab', { name: 'Inspector' }).click()
  await expect(inspector(page)).toHaveAttribute('data-state', 'valid')
  const firstSample = Date.now() - t1
  const t2 = Date.now()
  await page.getByRole('button', { name: 'Mountain source area' }).click()
  await expect(inspector(page)).toContainText('detachment zone')
  await expect(inspector(page)).toHaveAttribute('data-state', 'masked')
  const nextSample = Date.now() - t2
  const metrics = await page.evaluate(() => {
    const nav = performance.getEntriesByType('navigation')[0] as PerformanceNavigationTiming
    const res = performance.getEntriesByType('resource') as PerformanceResourceTiming[]
    const mem = (performance as unknown as { memory?: { usedJSHeapSize: number } }).memory
    return { domInteractiveMs: Math.round(nav.domInteractive), loadMs: Math.round(nav.loadEventEnd), requests: res.length, transferredMB: +(res.reduce((a, r) => a + r.encodedBodySize, 0) / 1e6).toFixed(1), heapMB: mem ? +(mem.usedJSHeapSize / 1e6).toFixed(0) : null }
  })
  const report = { mapReadyMs: mapReady, firstSampleMs: firstSample, nextSampleMs: nextSample, ...metrics }
  console.log(JSON.stringify(report))
  writeFileSync('e2e/performance.json', JSON.stringify(report, null, 2))
  // A shared CI machine draws the map in software on borrowed cores: CL_PERF_SLACK widens the limits there without loosening them here.
  const slack = Number(process.env.CL_PERF_SLACK ?? 1)
  expect(mapReady).toBeLessThan(8000 * slack)
  expect(firstSample).toBeLessThan(5000 * slack)
})

test('a clicked spot gets ranked explanations and a downloadable evidence report', async ({ page }) => {
  await open(page)
  await page.getByRole('button', { name: 'Bhote Koshi corridor' }).click()
  await page.getByRole('tab', { name: 'Inspector' }).click()
  const panel = page.locator('.hypotheses')
  await expect(panel.locator('.hyp').first()).toContainText('ground surface was disturbed', { timeout: 20000 })
  await expect(panel).toContainText('it is not a probability')
  const [csv] = await Promise.all([page.waitForEvent('download'), page.getByRole('button', { name: 'CSV', exact: true }).click()])
  expect(csv.suggestedFilename()).toMatch(/^cascadelens-rasuwa-2026-.*\.csv$/)
})

test('the printable report prints under the offline policy', async ({ page, context }) => {
  await open(page)
  await page.getByRole('button', { name: 'Bhote Koshi corridor' }).click()
  await page.getByRole('tab', { name: 'Inspector' }).click()
  const [report] = await Promise.all([context.waitForEvent('page'), page.getByRole('button', { name: 'Printable / PDF' }).click()])
  const refused: string[] = []
  report.on('console', (m) => { if (/Content Security Policy/.test(m.text())) refused.push(m.text()) })
  await expect(report.getByRole('heading', { level: 1 })).toContainText('CascadeLens evidence report', { timeout: 20000 })
  // The new window inherits the policy that blocks a script written into the page, so the button must be wired from the app.
  await report.evaluate(() => { window.print = () => { document.title = 'printed' } })
  await report.getByRole('button', { name: 'Print or save as PDF' }).click()
  await expect(report).toHaveTitle('printed')
  expect(refused).toEqual([])
})

test('the first minute leads with the finding and an honest status list', async ({ page }) => {
  await page.addInitScript(() => localStorage.removeItem('cascadelens.finding.seen'))
  await open(page)
  const card = page.getByRole('dialog', { name: 'The key finding' })
  await expect(card).toContainText('beyond the radar frames checked')
  await expect(card).toContainText('Provisional products')
  await card.getByRole('button', { name: 'What is real here?' }).click()
  const status = page.getByRole('dialog', { name: 'What is real here?' })
  await expect(status).toContainText('blocked by data')
  await expect(status).toContainText('experimental')
  await expect(status).toContainText('Flood and landslide outlooks: what the data allows')
  await expect(status.locator('.readiness li')).toHaveCount(12)
  await expect(status.locator('.readiness')).toContainText('not available')
  await expect(status.locator('.readiness')).toContainText('Next: B2: DHM discharge')
  // The rainfall threshold ran on real data and missed its criterion: shown as model work, never as a warning
  await expect(status.locator('.readiness-model')).toContainText('Ran, and missed its criterion')
  await page.getByRole('button', { name: 'Close' }).click()
  await card.getByRole('button', { name: 'Walk through the evidence' }).click()
  await expect(page.locator('.story')).toContainText('The source')
  await expect(card).toHaveCount(0)
})

test('the access screen names places that lose their road path, and what closed it', async ({ page }) => {
  await open(page)
  await page.getByText('Road access to health care').click()
  const panel = page.locator('.access-panel')
  await expect(panel).toContainText('No road path in this network', { timeout: 20000 })
  await expect(panel).toContainText('Trishuli')
  await expect(panel).toContainText('Closed on those routes')
  await expect(panel).toContainText('Furke Khola Bridge')
  await expect(panel).not.toContainText(/isolated|cut off/i)
  await panel.getByRole('checkbox', { name: 'Show road and bridge states' }).check()
  await expect(page.locator('.legend')).toContainText('Closed: mapped destroyed or reported washed out')
})

test('hazard screens explain a road stretch and say whether the radar could watch it', async ({ page }) => {
  await open(page)
  await page.getByRole('radio', { name: /Landslide-prone terrain/ }).check()
  await page.getByRole('checkbox', { name: 'Show road exposure' }).check()
  await page.getByRole('button', { name: 'Trishuli downstream corridor' }).click()
  await page.getByRole('tab', { name: 'Inspector' }).click()
  const hz = page.locator('.hazard-at')
  await expect(hz).toContainText('Experimental')
  await expect(hz).toContainText('exposure', { timeout: 20000 })
  await expect(hz).toContainText(/Radar (can|cannot) watch|Partly watchable/)
  await expect(page.locator('.legend')).toContainText('High exposure')
  // P0.3: the stretch's own evidence, and the exported report carries the same stretch
  await hz.getByText('Evidence for this stretch').click()
  const ev = hz.locator('.road-evidence')
  await expect(ev).toContainText(/way\/\d+:\d+/)
  await expect(ev).toContainText('NISAR_L2_PR_GUNW_028_048_D_074')
  await expect(ev).toContainText('What to verify')
  const id = (await ev.locator('dd.mono').first().textContent())!.trim()
  const [json] = await Promise.all([page.waitForEvent('download'), page.getByRole('button', { name: 'JSON', exact: true }).click()])
  const saved = JSON.parse(readFileSync((await json.path())!, 'utf8'))
  expect(saved.hazards.road.id).toBe(id)
})

// The flat map is locked: only the View controls move it, and they never leave the study envelope.
const camera = (page: Page) => page.evaluate(() => { const m = window.__clMap; const c = m.getCenter(); return { lng: c.lng, lat: c.lat, zoom: m.getZoom(), bearing: m.getBearing() } })
const viewBox = (page: Page) => page.evaluate(() => {
  const m = window.__clMap
  const b = m.getBounds()
  const env = (m.getStyle().sources['study-envelope'] as unknown as { data: { geometry: { coordinates: number[][][] } } }).data.geometry.coordinates[0]
  return { view: [b.getWest(), b.getSouth(), b.getEast(), b.getNorth()], env: [env[0][0], env[0][1], env[2][0], env[2][1]] }
})
const settle = (page: Page) => page.evaluate(() => new Promise<void>((r) => { const m = window.__clMap; if (!m.isMoving()) r(); else m.once('moveend', () => r()) }))

for (const [name, path] of [['Rasuwa', '/'], ['Tsho Rolpa', TSHO]] as const) {
  test(`${name}: the map drags and zooms freely, stops zooming out past the study area, and the View controls still work`, async ({ page }) => {
    await open(page, path)
    await page.waitForFunction(() => window.__clMap?.isStyleLoaded())
    await page.getByRole('button', { name: 'Explore', exact: true }).click() // Tsho Rolpa opens in its story, which moves the map itself
    const finding = page.getByRole('button', { name: 'Explore the map' }) // Rasuwa opens with its key-finding card over the map
    if (await finding.isVisible()) await finding.click()
    await settle(page)
    await page.waitForTimeout(1000)
    await settle(page)
    const controls = page.getByTestId('view-controls')
    await expect(controls).toBeVisible()
    await expect(controls).toContainText('Whole study area')
    const start = await camera(page)
    // The wheel zooms in, over open map clear of the side panels
    await page.mouse.move(720, 470)
    await page.mouse.wheel(0, -600)
    await page.waitForTimeout(600)
    await settle(page)
    const zoomed = await camera(page)
    expect(zoomed.zoom).toBeGreaterThan(start.zoom + 0.2)
    // A drag moves it, and it stays north-up
    await page.mouse.move(720, 470)
    await page.mouse.down()
    await page.mouse.move(820, 560, { steps: 8 })
    await page.mouse.up()
    await settle(page)
    const dragged = await camera(page)
    expect(Math.abs(dragged.lng - zoomed.lng) + Math.abs(dragged.lat - zoomed.lat)).toBeGreaterThan(1e-4)
    expect(dragged.bearing).toBeCloseTo(0, 6)
    // Zooming far out stops a little beyond the whole study area
    for (let i = 0; i < 12; i++) await page.mouse.wheel(0, 1200)
    await page.waitForTimeout(800)
    await settle(page)
    const out = await camera(page)
    expect(out.zoom).toBeGreaterThanOrEqual(start.zoom - 0.76)
    expect(out.zoom).toBeLessThanOrEqual(start.zoom + 1e-6)
    // Back to the whole area with the View controls
    await controls.getByRole('button', { name: 'Whole area' }).click()
    await settle(page)
    await expect(controls).toContainText('Whole study area')
    // At the whole-area view there is nothing to pan
    await expect(controls.getByLabel('Move the view west or east')).toBeDisabled()
    await expect(controls.getByLabel('Move the view south or north')).toBeDisabled()
    // The zoom slider zooms
    const zoom = controls.getByLabel(/^Zoom/)
    const max = Number(await zoom.getAttribute('max'))
    await zoom.fill(String(max))
    await settle(page)
    expect((await camera(page)).zoom).toBeCloseTo(max, 1)
    // The pan sliders reach both ends and never show ground outside the envelope
    for (const [label, value] of [['Move the view west or east', '0'], ['Move the view west or east', '1000'], ['Move the view south or north', '0'], ['Move the view south or north', '1000']] as const) {
      await expect(controls.getByLabel(label)).toBeEnabled()
      await controls.getByLabel(label).fill(value)
      await settle(page)
      const { view, env } = await viewBox(page)
      const eps = 1e-6
      expect(view[0]).toBeGreaterThanOrEqual(env[0] - eps)
      expect(view[1]).toBeGreaterThanOrEqual(env[1] - eps)
      expect(view[2]).toBeLessThanOrEqual(env[2] + eps)
      expect(view[3]).toBeLessThanOrEqual(env[3] + eps)
    }
    await page.screenshot({ path: `${SHOTS}/map-${name === 'Rasuwa' ? 'rasuwa' : 'tsho-rolpa'}.png` })
    await controls.getByRole('button', { name: 'Whole area' }).click()
    await settle(page)
    await expect(controls).toContainText('Whole study area')
    await expect(controls.getByLabel('Move the view west or east')).toBeDisabled()
    // A click still inspects a spot
    await page.mouse.click(720, 470)
    await expect(inspector(page)).toBeVisible()
    await expect(inspector(page)).not.toHaveAttribute('data-state', 'loading')
    // A story step still moves the map, and the sliders follow it
    const before = await camera(page)
    await page.getByRole('button', { name: 'Guided story', exact: true }).click()
    await page.getByRole('button', { name: 'Next' }).click()
    await expect.poll(async () => { const c = await camera(page); return Math.abs(c.lng - before.lng) + Math.abs(c.lat - before.lat) + Math.abs(c.zoom - before.zoom) }, { timeout: 8000 }).toBeGreaterThan(1e-4)
  })
}

test('Compare zoom keeps the before and after pictures aligned', async ({ page }) => {
  await open(page, TSHO)
  await page.getByRole('button', { name: 'Compare', exact: true }).click()
  const panel = page.locator('.compare-panel')
  const wrap = panel.getByTestId('swipe-zoom')
  await expect(wrap.locator('img')).toHaveCount(2)
  await expect(panel.getByLabel('Move both pictures west or east')).toBeDisabled()
  await panel.getByLabel('Zoom into both pictures together').fill('2')
  await panel.getByLabel('Move both pictures west or east').fill('900')
  await panel.getByLabel('Move both pictures south or north').fill('200')
  // Both pictures and the edge drawing sit inside one transformed wrapper: they share one transform, and none has its own
  expect(await wrap.evaluate((e) => getComputedStyle(e).transform)).not.toBe('none')
  const own = await wrap.evaluate((e) => [...e.querySelectorAll('img, svg')].map((c) => getComputedStyle(c).transform))
  expect(own.every((t) => t === 'none')).toBe(true)
  const boxes = await wrap.evaluate((e) => [...e.querySelectorAll('img')].map((c) => { const r = c.getBoundingClientRect(); return [r.x, r.y, r.width, r.height] }))
  expect(boxes[0]).toEqual(boxes[1])
  // The divider and the date tags stay fixed to the frame
  expect(await panel.locator('.swipe-line').evaluate((e) => e.parentElement?.classList.contains('swipe-frame'))).toBe(true)
  await page.waitForTimeout(400)
  await panel.locator('.swipe').screenshot({ path: `${SHOTS}/compare-zoom.png` })
  await panel.getByRole('button', { name: 'Whole picture' }).click()
  await expect(panel.getByLabel('Move both pictures west or east')).toBeDisabled()
})

// The steepest-slope line must read as the same water as the lake. Pixels are found by difference: the line by drawing it
// and not, the lake fill by showing it and not. Teal edge pixels (green above blue) are the measured outline, not water.
test('in 3D the steepest-slope line is the same colour as the lake', async ({ page, context }) => {
  test.setTimeout(120_000)
  await page.setViewportSize({ width: 1440, height: 900 })
  await open(page, TSHO)
  await page.getByRole('button', { name: '3D', exact: true }).click()
  const panel = page.locator('.terrain-panel')
  let k = 0
  // The camera eases to rest after it opens, so each picture waits for it to settle
  const shot = async () => {
    await page.waitForTimeout(5000)
    return (await page.locator('.terrain-canvas').screenshot({ path: `${SHOTS}/3d-colour-step${k++}.png` })).toString('base64')
  }
  // The lake toggle lives on the Look tab. The camera does not move between tabs.
  const lakeBox = panel.getByLabel(/Show the lake in blue/)
  await expect(lakeBox).toBeChecked()
  const withLake = await shot()
  await lakeBox.uncheck()
  const noLake = await shot()
  await lakeBox.check()
  await panel.getByRole('tab', { name: 'Steepest slope' }).click()
  const distance = panel.getByLabel(/Distance from the lake/)
  await distance.fill('0')
  const noLine = await shot()
  await distance.fill('1')
  const withLine = await shot()
  await page.screenshot({ path: `${SHOTS}/3d-water-colour.png` })
  const scratch = await context.newPage() // The app's offline policy blocks data: URLs, so the pixels are read on a blank page
  const averages = await scratch.evaluate(async ([l1, l0, r0, r1]) => {
    const pixels = async (b64: string) => {
      const bmp = await createImageBitmap(await (await fetch(`data:image/png;base64,${b64}`)).blob())
      const cv = new OffscreenCanvas(bmp.width, bmp.height)
      const g = cv.getContext('2d')!
      g.drawImage(bmp, 0, 0)
      return g.getImageData(0, 0, bmp.width, bmp.height).data
    }
    const [L1, L0, R0, R1] = await Promise.all([pixels(l1), pixels(l0), pixels(r0), pixels(r1)])
    const W = (await createImageBitmap(await (await fetch(`data:image/png;base64,${l1}`)).blob())).width
    // Only pixels whose four neighbours also qualify: edge pixels are blended with the terrain beside them and would say nothing about the water
    const mean = (on: (i: number) => boolean, src: Uint8ClampedArray) => {
      const s = [0, 0, 0]; let n = 0
      // The canvas fills the screen: keep to the model, clear of the top bar and the side panel, whose buttons change on hover
      const scene = (i: number) => { const x = (i / 4) % W, y = Math.floor(i / 4 / W); return y > 100 && x < W - 400 }
      const core = (i: number) => scene(i) && on(i) && on(i - 4) && on(i + 4) && on(i - 4 * W) && on(i + 4 * W)
      for (let i = 4 * W; i < src.length - 4 * W; i += 4) if (core(i)) { s[0] += src[i]; s[1] += src[i + 1]; s[2] += src[i + 2]; n++ }
      return { rgb: s.map((v) => Math.round(v / Math.max(1, n))), n }
    }
    const diff = (x: Uint8ClampedArray, y: Uint8ClampedArray, i: number) => Math.abs(x[i] - y[i]) + Math.abs(x[i + 1] - y[i + 1]) + Math.abs(x[i + 2] - y[i + 2]) > 30
    // The lake: changed when the fill is shown, and not the teal edge (green at or above blue)
    const lake = mean((i) => diff(L1, L0, i) && L1[i + 2] > L1[i + 1], L1)
    // The line: changed when it is drawn, and not the pale marker
    const line = mean((i) => diff(R0, R1, i) && R1[i] + R1[i + 1] + R1[i + 2] < 450, R1)
    return { line, lake }
  }, [withLake, noLake, noLine, withLine])
  await scratch.close()
  console.log(`3D water colour: lake ${averages.lake.rgb.join(', ')} (${averages.lake.n} px); line ${averages.line.rgb.join(', ')} (${averages.line.n} px)`)
  expect(averages.lake.n).toBeGreaterThan(200)
  expect(averages.line.n).toBeGreaterThan(100)
  for (let k = 0; k < 3; k++) expect(Math.abs(averages.lake.rgb[k] - averages.line.rgb[k])).toBeLessThanOrEqual(10)
  await expect(panel).toContainText('Not a flood model.')
})

test('the scenario and the What-if flood show their working, with the tables to check them', async ({ page }) => {
  await open(page, TSHO)
  await page.getByRole('button', { name: 'What if', exact: true }).click()
  const panel = page.locator('.scenario-panel')
  await panel.getByRole('tab', { name: '20 m breach' }).click()
  await panel.getByText('Show the working').click()
  const working = panel.locator('details.working')
  await expect(working).toContainText('32,120,000 m³')
  await expect(working).toContainText('25,545 m³/s')
  await expect(working).toContainText('2,794 m³/s')
  await expect(working).toContainText('33,180 m³/s')
  await expect(working).toContainText('1.495')
  await expect(working.getByRole('link', { name: /Every cross-section/ })).toHaveAttribute('href', /tsho-rolpa-2026-scenario-sections\.csv$/)
  const csv = await page.request.get(await working.getByRole('link', { name: /Every cross-section/ }).getAttribute('href') ?? '')
  expect(csv.status()).toBe(200)
  await expect(panel).toContainText('Sensitivity, not the default')
  await working.scrollIntoViewIfNeeded()
  await page.waitForTimeout(500)
  await page.screenshot({ path: `${SHOTS}/show-the-working.png` })
  await open(page)
  await page.getByRole('button', { name: 'Simulate' }).click()
  const sim = page.locator('.sim-panel')
  await sim.getByRole('tab', { name: 'What-if flood' }).click()
  await sim.getByText('Show the working').click()
  await expect(sim.locator('details.working')).toContainText('km ≤ 198')
  await expect(sim.locator('details.working')).toContainText('3,274')
  const xlsx = await page.request.get(await sim.getByRole('link', { name: /Spreadsheet/ }).getAttribute('href') ?? '')
  expect(xlsx.status()).toBe(200)
})

test('the cliff-impact tab is a labelled hypothesis with candidate sites on the map', async ({ page }) => {
  await open(page)
  await page.getByRole('button', { name: 'Simulate' }).click()
  const sim = page.locator('.sim-panel')
  await sim.getByRole('tab', { name: 'Cliff impact (hypothesis)' }).click()
  await expect(sim).toContainText("A mentor's account with no location or figures. CascadeLens tests where it could have happened. It does not confirm that it did.")
  await expect(sim.locator('.evidence').first()).toHaveText('Hypothesis')
  await expect(sim).toContainText('2.0×10⁸ N')
  await expect(sim).toContainText('no site stands out clearly')
  await page.waitForFunction(() => Boolean(window.__clMap.getLayer('impact-dots')))
  const n = await page.evaluate(() => window.__clMap.querySourceFeatures('impact-sites').length)
  expect(n).toBeGreaterThan(0)
  await sim.getByLabel('Candidate site').selectOption('S1')
  await expect(sim).toContainText('Data do not show it')
  await expect(page.locator('.sim-head')).toHaveCount(0)
  await page.waitForTimeout(800)
  await page.screenshot({ path: `${SHOTS}/cliff-impact.png` })
})

test('a road stretch becomes a field-check record, keeps the satellite record apart from the field report, and exports', async ({ page }) => {
  // Clear the list once per test, not on the reload below
  await page.addInitScript(() => { if (!sessionStorage.getItem('fc-cleared')) { localStorage.removeItem('cascadelens.fieldChecks.v1'); sessionStorage.setItem('fc-cleared', '1') } })
  await open(page)
  await page.getByRole('button', { name: 'Trishuli downstream corridor' }).click()
  await page.getByRole('tab', { name: 'Inspector' }).click()
  const hz = page.locator('.hazard-at')
  await expect(hz).toContainText('exposure', { timeout: 20000 })
  await hz.getByText('Evidence for this stretch').click()
  const id = (await hz.locator('.road-evidence dd.mono').first().textContent())!.trim()
  await hz.getByRole('button', { name: 'Add to field-check list' }).click()
  const fc = page.locator('.field-checks')
  await expect(fc).toContainText(`FV-rasuwa-2026-${id}`)
  await expect(fc).toContainText('Needs verification')
  await expect(fc).toContainText('What remains unknown')
  await expect(fc).toContainText('Nothing on the ground has been reported')
  // Verified needs a field report: the workflow menu does not offer it
  await expect(fc.getByLabel('New status').locator('option', { hasText: 'Verified' })).toHaveCount(0)
  // A report with no source is refused
  await fc.getByLabel('What was seen').fill('Typed by the test, not a real observation')
  await fc.getByLabel('Observed on').fill('2026-11-01')
  await fc.getByLabel('Outcome').selectOption('unable')
  await fc.getByRole('button', { name: 'Save field report' }).click()
  await expect(fc.getByRole('alert')).toContainText('who or what')
  await fc.getByLabel('Who or what reported it').fill('Browser test')
  await fc.getByRole('button', { name: 'Save field report' }).click()
  await expect(fc.locator('.fc-reports')).toContainText('Typed by the test')
  await expect(fc.locator('.fc-detail > p .fc-status')).toHaveText('Unable to verify')
  await expect(fc).toContainText('Satellite record, unchanged')
  await fc.getByRole('button', { name: '← All field checks' }).click()
  await expect(page.getByRole('tab', { name: 'Field checks (1)' })).toBeVisible()
  const [csv] = await Promise.all([page.waitForEvent('download'), fc.getByRole('button', { name: 'CSV' }).click()])
  const text = readFileSync((await csv.path())!, 'utf8')
  expect(text).toContain(id)
  expect(text).toContain('Exposure is not damage or closure')
  // The list survives a reload: it lives in this browser
  await page.reload()
  await expect(page.locator('.map-state')).toHaveText('Map ready')
  await expect(page.getByRole('tab', { name: 'Field checks (1)' })).toBeVisible()
})

test('a spot the radar cannot use gets rule-based next steps that only promise data this build holds', async ({ page }) => {
  await open(page)
  await page.getByRole('button', { name: 'Mountain source area' }).click()
  await page.getByRole('tab', { name: 'Inspector' }).click()
  const obs = page.locator('.obs-at')
  await expect(obs).toContainText('No valid data in the product', { timeout: 20000 })
  await obs.getByText('What to try next').first().click()
  const next = obs.locator('.next-steps').first()
  await expect(next).toContainText('[R-MASK]')
  await expect(next).toContainText(/Already in CascadeLens|Not found in the data here/)
  await expect(next).toContainText('Needs a person to collect it')
})

test('a slow connection is warned about, with its speed and an estimate, and goes away when the map is ready', async ({ page }) => {
  test.setTimeout(240_000)
  const cdp = await page.context().newCDPSession(page)
  await cdp.send('Network.emulateNetworkConditions', { offline: false, latency: 150, downloadThroughput: 60_000, uploadThroughput: 50_000 })
  await page.goto('/')
  const notice = page.locator('.slow-notice')
  await expect(notice).toContainText('Slow connection', { timeout: 60_000 })
  await expect(notice).toContainText(/about \d+ KB\/s/)
  await expect(notice).toContainText(/may need about .* more to load/)
  await expect(notice.getByRole('button', { name: 'Use light mode' })).toBeVisible()
  await cdp.send('Network.emulateNetworkConditions', { offline: false, latency: 0, downloadThroughput: -1, uploadThroughput: -1 })
  await expect(page.locator('.map-state')).toHaveText('Map ready', { timeout: 120_000 })
  await expect(notice).toHaveCount(0)
})

test('light mode draws more lightly and can be switched off again, with the same data on screen', async ({ page }) => {
  await open(page, '/?lite=1')
  await expect(page.locator('html')).toHaveClass(/\blite\b/)
  const toggle = page.getByRole('button', { name: 'Light mode: on' })
  await expect(toggle).toHaveAttribute('aria-pressed', 'true')
  expect(await page.evaluate(() => window.__clMap.getPixelRatio())).toBe(1)
  await expect(page.locator('.legend-title').first()).toContainText('relative to frame median')
  await toggle.click()
  await expect(page.getByRole('button', { name: 'Light mode: off' })).toBeVisible()
  await expect(page.locator('html')).not.toHaveClass(/\blite\b/)
  expect(await page.evaluate(() => localStorage.getItem('cascadelens.lite'))).toBe('off')
})
