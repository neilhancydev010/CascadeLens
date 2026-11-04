import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { App } from './app/App'
import 'maplibre-gl/dist/maplibre-gl.css' // Here, not in the map's own lazy file: app.css has to load after it to override it
import './styles/app.css'

createRoot(document.getElementById('root')!).render(<StrictMode><App /></StrictMode>)
