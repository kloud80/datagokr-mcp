import { useState } from 'react'

// 클립보드 API는 https·localhost에서만 열린다 — http 주소(내부망·개발 서버)에서는 선택 후 복사로 대신한다
export async function copyText(text: string): Promise<boolean> {
  if (window.isSecureContext && navigator.clipboard) {
    try {
      await navigator.clipboard.writeText(text)
      return true
    } catch { /* 아래 방식으로 */ }
  }
  const ta = document.createElement('textarea')
  ta.value = text
  ta.setAttribute('readonly', '')
  ta.style.position = 'fixed'
  ta.style.opacity = '0'
  document.body.appendChild(ta)
  ta.select()
  let ok = false
  try {
    ok = document.execCommand('copy')
  } finally {
    document.body.removeChild(ta)
  }
  return ok
}

export function useCopy(): [boolean, (text: string) => void] {
  const [ok, setOk] = useState(false)
  return [ok, (text: string) => { void copyText(text).then(r => { if (r) { setOk(true); setTimeout(() => setOk(false), 1200) } }) }]
}

// 주소 옆 복사 아이콘
export function CopyIcon({ text, label }: { text: string; label?: string }) {
  const [ok, copy] = useCopy()
  return (
    <button type="button" className="copy-icon" title={ok ? '복사됨' : `${label ?? text} 복사`} aria-label={`${label ?? text} 복사`} onClick={() => copy(text)}>
      {ok ? (
        <svg viewBox="0 0 16 16" width="15" height="15" aria-hidden="true"><path d="M3 8.5l3 3 7-7" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" /></svg>
      ) : (
        <svg viewBox="0 0 16 16" width="15" height="15" aria-hidden="true"><rect x="5" y="5" width="8.5" height="8.5" rx="1.5" fill="none" stroke="currentColor" strokeWidth="1.4" /><path d="M10.5 3.5V3a1 1 0 0 0-1-1H3a1 1 0 0 0-1 1v6.5a1 1 0 0 0 1 1h.5" fill="none" stroke="currentColor" strokeWidth="1.4" /></svg>
      )}
    </button>
  )
}
