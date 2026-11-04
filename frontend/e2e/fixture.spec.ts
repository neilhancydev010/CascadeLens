import { expect, test, type Page } from '@playwright/test'

// Runs against the synthetic fixture, whose pixels are known. These values are invented and prove software only.
declare global { interface Window { __clMap: import('maplibre-gl').Map } }

const VALID = [85.41258924981882, 28.178783575841948] // row 100, col 100
const WATER = [85.33330567372667, 28.24715240329843] // row 4, col 4: phase -5.9038, mask 111
const NAN = [85.33, 28.25] // row 0, col 0

async function open(page: Page) {
  await page.goto('/')
  await expect(page.locator('.map-state')).toHaveText('Map ready')
  await page.waitForFunction(() => window.__clMap?.isStyleLoaded())
}

const click = (page: Page, [lng, lat]: number[]) =>
  page.evaluate(([lng, lat]) => { window.__clMap.fire('click', { lngLat: { lng, lat }, point: { x: 0, y: 0 }, originalEvent: new MouseEvent('click') }) }, [lng, lat])

const rasters = (page: Page) => page.evaluate(() => window.__clMap.getStyle().layers.map((l) => l.id).filter((i) => /^(active|overlay)-/.test(i)))

test.beforeEach(({ page }) => open(page))

test('labels itself as synthetic', async ({ page }) => {
  await expect(page.locator('.fixture-banner')).toContainText('SYNTHETIC TEST FIXTURE')
})

test('renders real tiles for the selected measurement', async ({ page }) => {
  await expect(page.locator('.legend-title').first()).toContainText('Unwrapped phase (radians')
  expect(await rasters(page)).toEqual(['active-0'])
  const tile = page.waitForResponse((r) => r.url().includes('/tiles/pair-a/gunw-phase/') && r.status() === 200)
  await page.reload() // The full-screen map fetches its tiles while opening, so a bookmark may need no new ones
  await tile
})

test('the inspector reads known pixels exactly', async ({ page }) => {
  const inspector = page.locator('.inspector')
  await click(page, VALID)
  await expect(inspector).toHaveAttribute('data-state', 'valid')
  await expect(page.locator('.value')).toHaveText('-3.5952 radians')
  await expect(page.locator('.quality-row').first()).toContainText('0.70000')
  await click(page, WATER)
  await expect(inspector).toHaveAttribute('data-state', 'masked')
  await expect(page.locator('.value')).toHaveText('-5.9038 radians')
  await click(page, NAN)
  await expect(inspector).toHaveAttribute('data-state', 'nodata')
  await expect(page.locator('.value')).toHaveCount(0)
  await click(page, [84, 27])
  await expect(inspector).toHaveAttribute('data-state', 'outside')
  await expect(page.locator('.value')).toHaveCount(0)
})

test('switching evidence keeps the location and changes the measurement', async ({ page }) => {
  await click(page, VALID)
  await expect(page.locator('.inspector')).toHaveAttribute('data-state', 'valid')
  const place = await page.locator('.inspector dd').first().textContent()
  await page.getByRole('tab', { name: 'Pixel offsets' }).click()
  await expect(page.getByRole('heading', { name: 'Slant-range offset' })).toBeVisible()
  await expect(page.locator('.legend-title').first()).toHaveText('Slant-range offset (meters)')
  await expect(page.locator('.inspector dd').first()).toHaveText(place!)
  await expect(page.locator('.quality-row')).toHaveCount(2)
})

test('quality overlays, masks, opacity and visibility change the real map', async ({ page }) => {
  await page.getByRole('tab', { name: 'Pixel offsets' }).click()
  await page.getByRole('checkbox', { name: 'Show masked pixels' }).check()
  await expect.poll(() => rasters(page)).toContain('overlay-m0')
  await page.getByLabel('Quality overlay').selectOption('pair-a:goff-snr')
  await expect.poll(() => rasters(page)).toContain('overlay-q0')
  await page.getByLabel(/Layer opacity/).fill('0.4')
  await expect.poll(() => page.evaluate(() => window.__clMap.getPaintProperty('active-0', 'raster-opacity'))).toBe(0.4)
  await page.getByRole('radio', { name: /Along-track offset/ }).check()
  await expect.poll(() => rasters(page)).toEqual(['active-0'])
  await page.getByRole('checkbox', { name: /Show Along-track offset/ }).uncheck()
  await expect.poll(() => rasters(page)).toEqual([])
  await expect(page.locator('.legend')).not.toContainText('Along-track')
})

test('GCOV snapshots store linear values and display decibels', async ({ page }) => {
  await page.getByRole('tab', { name: 'Snapshots' }).click()
  await expect(page.getByRole('heading', { name: 'Gamma-0 backscatter' })).toBeVisible()
  await expect(page.locator('.legend-title').first()).toHaveText('Gamma-0 backscatter (dB)')
  await page.getByRole('tab', { name: 'Inspector' }).click()
  await click(page, VALID)
  await expect(page.locator('.value')).toContainText('0.01')
  await expect(page.locator('.value')).toContainText('-20.00 dB')
})

test('announces when the layer has no coverage in view', async ({ page }) => {
  await page.evaluate(() => window.__clMap.jumpTo({ center: [84.5, 27.8], zoom: 11 }))
  await expect(page.locator('.map-notice')).toContainText('no data in this view')
  await page.evaluate(() => window.__clMap.jumpTo({ center: [85.4, 28.2], zoom: 11 }))
  await expect(page.locator('.map-notice')).toHaveCount(0)
})

test('a failed raster source reports an error and leaves the app usable', async ({ page }) => {
  await page.route('**/data/tiles/pair-a/**', (r) => r.fulfill({ status: 500, body: 'boom' }))
  await page.reload()
  await expect(page.locator('.legend-title').first()).toContainText('Unwrapped phase (radians')
  await page.getByRole('button', { name: 'Bhote Koshi corridor' }).click()
  await expect(page.locator('.map-alert')).toContainText('Could not load map source')
  await expect(page.locator('.map-state')).toHaveText('Map source failed')
  await page.getByRole('radio', { name: /Coherence magnitude/ }).check()
  await expect(page.getByRole('heading', { name: 'Coherence magnitude' })).toBeVisible()
})

test('a failed sampling asset is reported, never shown as a number', async ({ page }) => {
  await page.route('**/data/sampling/pair-a/**', (r) => r.abort())
  await page.reload()
  await page.waitForFunction(() => window.__clMap?.isStyleLoaded())
  await click(page, VALID)
  await expect(page.locator('.inspector')).toHaveAttribute('data-state', 'error')
  await expect(page.locator('.value')).toHaveCount(0)
})

test('the story uses loaded measurements when they exist', async ({ page }) => {
  await page.getByRole('button', { name: 'Start the guided story' }).click()
  await page.getByRole('button', { name: 'Next' }).click()
  await expect(page.locator('.story')).toContainText('The map shows coherence')
  await expect.poll(() => rasters(page)).toEqual(['active-0'])
})
