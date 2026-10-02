import { Fragment, type ReactNode } from 'react'
import { AgentTable } from '@bv-ds/ui'
import { TrustIcon, type Trust } from './Trust'

// 아주 작은 markdown → React: 굵게·인라인 코드·목록·제목·표.
// 데이터 참조: [[목록키]](채팅 답) → 신뢰 기호가 붙은 참조 버튼, 맨 숫자 목록키(설명서) → 상세 열기 버튼.

export type OpenDataset = (id: string) => void
export type ResolveRef = (id: string) => Trust | null

interface Ctx {
  open?: OpenDataset
  resolve?: ResolveRef
}

function inline(text: string, c: Ctx): ReactNode[] {
  const out: ReactNode[] = []
  const re = /\[\[(\d{6,8})\]\]|\*\*(.+?)\*\*|`([^`]+)`|\b(1\d{7}|3\d{6})\b/g
  let last = 0
  let m: RegExpExecArray | null
  while ((m = re.exec(text))) {
    if (m.index > last) out.push(text.slice(last, m.index))
    const k = `${m.index}`
    if (m[1] != null) out.push(<Ref key={k} id={m[1]} c={c} />)
    else if (m[2] != null) out.push(<strong key={k}>{inline(m[2], c)}</strong>)
    else if (m[3] != null) out.push(<code key={k} className="pds-code">{m[3]}</code>)
    else if (c.open) out.push(<DsLink key={k} id={m[4]} open={c.open} />)
    else out.push(m[4])
    last = re.lastIndex
  }
  if (last < text.length) out.push(text.slice(last))
  return out
}

function Ref({ id, c }: { id: string; c: Ctx }) {
  const trust = c.resolve?.(id) ?? null
  return (
    <button type="button" className={`pds-ref${trust ? ` pds-ref--${trust}` : ''}`} onClick={() => c.open?.(id)}>
      {trust ? <TrustIcon trust={trust} /> : null}
      {id}
    </button>
  )
}

export function DsLink({ id, open }: { id: string; open: OpenDataset }) {
  return (
    <button type="button" className="pds-dslink" onClick={() => open(id)} title="데이터 상세 보기">
      {id}
    </button>
  )
}

export function Markdown({ text, open, resolve }: { text: string; open?: OpenDataset; resolve?: ResolveRef }) {
  const c: Ctx = { open, resolve }
  const blocks: ReactNode[] = []
  let list: string[] = []
  let table: string[] = []
  const flushList = () => {
    if (list.length) {
      const items = list
      blocks.push(<ul key={`l${blocks.length}`}>{items.map((li, i) => <li key={i}>{inline(li, c)}</li>)}</ul>)
    }
    list = []
  }
  const flushTable = () => {
    const rows = table.filter((r) => !/^\|[-:| ]+\|$/.test(r.trim()))
    if (rows.length) {
      const cells = rows.map((r) => r.trim().slice(1, -1).split('|').map((x) => x.trim()))
      const columns = cells[0].map((label, i) => ({ key: `c${i}`, label }))
      const body = cells.slice(1).map((r, ri) => {
        const row: Record<string, ReactNode> = { key: ri }
        r.forEach((x, i) => (row[`c${i}`] = inline(x, c)))
        return row
      })
      blocks.push(<div key={`t${blocks.length}`} className="pds-table"><AgentTable columns={columns} rows={body} /></div>)
    }
    table = []
  }
  for (const line of text.split('\n')) {
    if (line.trim().startsWith('|')) { flushList(); table.push(line); continue }
    flushTable()
    const li = line.match(/^\s*(?:[-*]|\d+[.)])\s+(.*)/)
    if (li) { list.push(li[1]); continue }
    flushList()
    const h = line.match(/^(#{1,4})\s+(.*)/)
    if (h) { blocks.push(<p key={`h${blocks.length}`} className={`pds-h pds-h${h[1].length}`}>{inline(h[2], c)}</p>); continue }
    if (line.startsWith('>') || !line.trim() || /^-{3,}$/.test(line.trim())) continue
    blocks.push(<p key={`p${blocks.length}`}>{inline(line, c)}</p>)
  }
  flushList()
  flushTable()
  return <div className="pds-md">{blocks.map((b, i) => <Fragment key={i}>{b}</Fragment>)}</div>
}
