import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { App } from './app/App'
import { ErrorBoundary } from './components/layout/ErrorBoundary'
// Fonts ship with the app, so it reads the same with the network off
import '@fontsource-variable/manrope/wght.css'
import '@fontsource/instrument-serif/latin-400.css'
import '@fontsource/instrument-serif/latin-400-italic.css'
import '@fontsource/instrument-serif/latin-ext-400.css'
import '@fontsource/instrument-serif/latin-ext-400-italic.css'
import 'maplibre-gl/dist/maplibre-gl.css' // Here, not in the map's own lazy file: app.css has to load after it to override it
import './styles/app.css'

createRoot(document.getElementById('root')!).render(<StrictMode><ErrorBoundary><App /></ErrorBoundary></StrictMode>)
