import { useMemo, useState } from 'react'
import { AgentChip, AgentPagination, AgentSelect, AgentTable, AgentTextField } from '@bv-ds/ui'
import type { SiteRow } from '../api'

// 사이트별 커버리지 — 포털 링크형 데이터가 어느 사이트에 있고, 이 시스템은 어디까지 키를 받아 확인했는가.

const PAGE = 20
const KEY_CHIP: Record<SiteRow['key'], 'live' | 'primary' | 'hot' | 'neutral'> = {
  '보유·검증': 'live', 보유: 'primary', 미보유: 'hot', '키 불필요': 'neutral',
}

export function SiteTable({ sites }: { sites: SiteRow[] }) {
  const [q, setQ] = useState('')
  const [key, setKey] = useState('')
  const [kind, setKind] = useState('api')
  const [page, setPage] = useState(1)
  const shown = useMemo(() => {
    const s = q.trim().toLowerCase()
    return sites.filter((r) => (!key || r.key === key) && (kind === 'all' || (kind === 'api' ? r.api > 0 : r.api === 0))
      && (!s || r.name.toLowerCase().includes(s) || r.host.includes(s)))
  }, [sites, q, key, kind])
  const pages = Math.max(1, Math.ceil(shown.length / PAGE))
  const cur = shown.slice((Math.min(page, pages) - 1) * PAGE, Math.min(page, pages) * PAGE)
  return (
    <div className="doc-table">
      <div className="doc-filters">
        <AgentTextField search size="sm" placeholder="사이트 검색" value={q} onChange={(e) => { setQ(e.target.value); setPage(1) }} />
        <AgentSelect size="sm" value={kind} onChange={(e) => { setKind(e.target.value); setPage(1) }}
          options={[{ value: 'api', label: 'API 제공 사이트' }, { value: 'file', label: '파일만 제공' }, { value: 'all', label: '전체' }]} />
        <AgentSelect size="sm" value={key} onChange={(e) => { setKey(e.target.value); setPage(1) }}
          options={[{ value: '', label: '모든 키 상태' }, ...(['보유·검증', '보유', '미보유', '키 불필요'] as const).map((k) => ({ value: k, label: k }))]} />
      </div>
      <p className="doc-small">{shown.length.toLocaleString()}곳</p>
      <AgentTable
        caption="사이트별 커버리지"
        columns={[{ key: 'name', label: '사이트' }, { key: 'api', label: 'API', numeric: true }, { key: 'file', label: '파일', numeric: true },
          { key: 'targets', label: '검토 대상', numeric: true }, { key: 'verified', label: '검증', numeric: true }, { key: 'status', label: '키' },
          { key: 'how', label: '가입·발급' }]}
        rows={cur.map((r) => ({
          key: r.host,
          name: <a href={`https://${r.host}`} target="_blank" rel="noreferrer" title={r.host}>{r.name}</a>,
          api: r.api.toLocaleString(), file: r.file.toLocaleString(), targets: r.targets || '—', verified: r.verified || '—',
          status: <AgentChip variant={KEY_CHIP[r.key]}>{r.key}</AgentChip>,
          how: <span className="doc-small">{r.how || (r.api ? '사이트에서 회원가입 → 오픈API 인증키 신청 (절차 확인 필요)' : '사이트에서 파일 내려받기')}{r.env ? <> · <code className="pds-code">{r.env}</code></> : null}</span>,
        }))}
      />
      <AgentPagination page={Math.min(page, pages)} pageCount={pages} onChange={setPage} label="사이트 표 페이지" />
    </div>
  )
}
