import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { initializeTheme } from '@/lib/theme-store'
import './index.css'
import App from './App.tsx'

// Applies the stored fleet theme (dark by default) before the first render.
initializeTheme()

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
