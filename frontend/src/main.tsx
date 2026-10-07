import '@bv-ds/tokens/root.css'
import '@bv-ds/tokens/tokens.css'
import '@bv-ds/ui/style.css'
import '@bv-ds/ui/agent.css'
import './app.css'
import './docs.css'
import './wiki.css'

import { StrictMode, useEffect, useState } from 'react'
import { createRoot } from 'react-dom/client'
import { App } from './App'
import { Docs } from './Docs'
import { Mcp } from './Mcp'
import { Wiki } from './Wiki'

// 해시 경로 — #/docs 문서 · #/wiki 데이터 위키 · #/mcp MCP 가이드 · 그 밖은 채팅 (서버는 / 하나만 서빙한다)
function Root() {
  const [hash, setHash] = useState(window.location.hash)
  useEffect(() => {
    const on = () => { setHash(window.location.hash); window.scrollTo(0, 0) }
    window.addEventListener('hashchange', on)
    return () => window.removeEventListener('hashchange', on)
  }, [])
  return hash.startsWith('#/docs') ? <Docs /> : hash.startsWith('#/wiki') ? <Wiki hash={hash} /> : hash.startsWith('#/mcp') ? <Mcp /> : <App />
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <Root />
  </StrictMode>,
)
