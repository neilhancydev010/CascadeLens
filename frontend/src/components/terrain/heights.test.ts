// @vitest-environment node
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'
import { unpackHeights } from './heights'

// The packed heights the web page downloads must give back exactly the plain heights file, point for point.
const DIR = join(__dirname, '../../../public/data/terrain/rasuwa-2026')
const model = JSON.parse(readFileSync(join(DIR, 'model.json'), 'utf-8'))

describe('packed Rasuwa heights', () => {
  it('unpack to the plain heights exactly', async () => {
    const gz = readFileSync(join(DIR, 'heights.bin.gz'))
    const z = await unpackHeights(gz.buffer.slice(gz.byteOffset, gz.byteOffset + gz.byteLength), model.width, model.height)
    const raw = readFileSync(join(DIR, 'heights.bin'))
    const plain = new Int16Array(raw.buffer.slice(raw.byteOffset, raw.byteOffset + raw.byteLength))
    expect(z.length).toBe(plain.length)
    let worst = 0
    for (let i = 0; i < plain.length; i++) worst = Math.max(worst, Math.abs(z[i] - plain[i]))
    expect(worst).toBe(0)
    expect(z.reduce((a, b) => Math.min(a, b))).toBe(model.minM)
    expect(z.reduce((a, b) => Math.max(a, b))).toBe(model.maxM)
  })
  it('also reads a copy the browser has already unzipped', async () => {
    const { gunzipSync } = await import('node:zlib')
    const plain = gunzipSync(readFileSync(join(DIR, 'heights.bin.gz')))
    const z = await unpackHeights(plain.buffer.slice(plain.byteOffset, plain.byteOffset + plain.byteLength), model.width, model.height)
    const raw = readFileSync(join(DIR, 'heights.bin'))
    expect(z[12345]).toBe(raw.readInt16LE(12345 * 2))
    expect(z[z.length - 1]).toBe(raw.readInt16LE(raw.length - 2))
  })
  it('keeps what the page needs at the start under 1 MB', () => {
    expect(model.startBytes).toBeGreaterThan(0)
    expect(model.startBytes).toBeLessThan(1_000_000)
  })
})
