// Undoes prepare_rasuwa_3d.py's packing: gunzip, rejoin the high and low byte planes, then add up each row's steps
export async function unpackHeights(gz: ArrayBuffer, width: number, height: number) {
  // Some servers send a .gz file with Content-Encoding: gzip, and then the browser has already unzipped it
  const head = new Uint8Array(gz, 0, Math.min(2, gz.byteLength))
  const zipped = head[0] === 0x1f && head[1] === 0x8b
  const bytes = zipped ? new Uint8Array(await new Response(new Blob([gz]).stream().pipeThrough(new DecompressionStream('gzip'))).arrayBuffer()) : new Uint8Array(gz)
  const n = width * height
  if (bytes.length !== n * 2) throw new Error(`The 3D heights file has the wrong size (${bytes.length} bytes, expected ${n * 2})`)
  const z = new Float32Array(n)
  for (let r = 0; r < height; r++) {
    let v = 0
    for (let c = 0; c < width; c++) {
      const i = r * width + c
      const step = ((bytes[i] << 8) | bytes[n + i]) << 16 >> 16
      v = c === 0 ? step : v + step
      z[i] = v
    }
  }
  return z
}
