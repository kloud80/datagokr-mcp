import { Fragment, type ReactNode } from 'react'
import { AgentTable } from '@bv-ds/ui'

// 아주 작은 markdown → React: 굵게·인라인 코드·목록·제목·표. 목록키(포털 ID)는 상세 보기 버튼이 된다.

export type OpenDataset = (id: string) => void

function inline(text: string, open?: OpenDataset): ReactNode[] {
  const out: ReactNode[] = []
  const re = /\*\*(.+?)\*\*|`([^`]+)`|\b(1\d{7}|3\d{6})\b/g
  let last = 0
  let m: RegExpExecArray | null
  while ((m = re.exec(text))) {
    if (m.index > last) out.push(text.slice(last, m.index))
    const k = `${m.index}`
    if (m[1] != null) out.push(<strong key={k}>{inline(m[1], open)}</strong>)
    else if (m[2] != null) out.push(<code key={k} className="pds-code">{m[2]}</code>)
    else if (open) out.push(<DsLink key={k} id={m[3]} open={open} />)
    else out.push(m[3])
    last = re.lastIndex
  }
  if (last < text.length) out.push(text.slice(last))
  return out
}

export function DsLink({ id, open }: { id: string; open: OpenDataset }) {
  return (
    <button type="button" className="pds-dslink" onClick={() => open(id)} title="데이터 상세 보기">
      {id}
    </button>
  )
}

export function Markdown({ text, open }: { text: string; open?: OpenDataset }) {
  const blocks: ReactNode[] = []
  const lines = text.split('\n')
  let list: string[] = []
  let table: string[] = []
  const flushList = () => {
    if (list.length) {
      const items = list
      blocks.push(
        <ul key={`l${blocks.length}`}>
          {items.map((li, i) => <li key={i}>{inline(li, open)}</li>)}
        </ul>,
      )
    }
    list = []
  }
  const flushTable = () => {
    const rows = table.filter((r) => !/^\|[-:| ]+\|$/.test(r.trim()))
    if (rows.length) {
      const cells = rows.map((r) => r.trim().slice(1, -1).split('|').map((c) => c.trim()))
      const columns = cells[0].map((label, i) => ({ key: `c${i}`, label }))
      const body = cells.slice(1).map((r, ri) => {
        const row: Record<string, ReactNode> = { key: ri }
        r.forEach((c, i) => (row[`c${i}`] = inline(c, open)))
        return row
      })
      blocks.push(<div key={`t${blocks.length}`} className="pds-table"><AgentTable columns={columns} rows={body} /></div>)
    }
    table = []
  }
  for (const line of lines) {
    if (line.trim().startsWith('|')) { flushList(); table.push(line); continue }
    flushTable()
    const li = line.match(/^\s*(?:[-*]|\d+[.)])\s+(.*)/)
    if (li) { list.push(li[1]); continue }
    flushList()
    const h = line.match(/^(#{1,4})\s+(.*)/)
    if (h) { blocks.push(<p key={`h${blocks.length}`} className={`pds-h pds-h${h[1].length}`}>{inline(h[2], open)}</p>); continue }
    if (line.startsWith('>') || !line.trim() || /^-{3,}$/.test(line.trim())) continue
    blocks.push(<p key={`p${blocks.length}`}>{inline(line, open)}</p>)
  }
  flushList()
  flushTable()
  return <div className="pds-md">{blocks.map((b, i) => <Fragment key={i}>{b}</Fragment>)}</div>
}

