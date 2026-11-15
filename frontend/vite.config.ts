import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

// `--mode fixture` serves the synthetic software-test assets. The app's real data stays in public/.
export default defineConfig(({ mode }) => ({
  base: './',
  appType: 'mpa', // A missing tile must be a 404, not index.html: sparse tile pyramids depend on it
  publicDir: mode === 'fixture' ? '../tests/fixtures/public' : 'public',
  plugins: [react()],
  build: {
    chunkSizeWarningLimit: 2500, // MapLibre alone is ~1 MB; this is a single-screen app
    // Fonts stay real files: the offline policy below refuses a font folded into the stylesheet as data.
    assetsInlineLimit: (file) => (/\.woff2?$/.test(file) ? false : undefined),
  },
  preview: {
    // The offline demo proof: the browser refuses any request that leaves this origin.
    headers: { 'Content-Security-Policy': "default-src 'self'; connect-src 'self'; img-src 'self' data: blob:; worker-src 'self' blob:; style-src 'self' 'unsafe-inline'; script-src 'self' 'sha256-9RhnX3H62x9JK7C4XaHxPW59jwPE4LvvXZKk4OLX7dI=' 'wasm-unsafe-eval'" },
  },
  test: { environment: 'jsdom', globals: true, css: false },
}))
