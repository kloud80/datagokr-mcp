import '@bv-ds/tokens/root.css'
import '@bv-ds/tokens/tokens.css'
import '@bv-ds/ui/style.css'
import '@bv-ds/ui/agent.css'
import './app.css'

import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { App } from './App'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
