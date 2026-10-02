// 만든 이 표기 — 화면 하단 공통
export function Credit({ compact }: { compact?: boolean }) {
  return (
    <p className={compact ? 'pds-credit pds-credit--compact' : 'pds-credit'}>
      Created by <b>BigValue Kloud</b> &amp; <b>Claude Code</b> ·{' '}
      <a href="https://github.com/kloud80/datagokr-mcp" target="_blank" rel="noreferrer">GitHub</a>
    </p>
  )
}
