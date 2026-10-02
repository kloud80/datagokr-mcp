import { useMemo, useState } from 'react'
import { AgentChip, AgentPagination, AgentSelect, AgentTable, AgentTextField } from '@bv-ds/ui'
import type { DocsRow } from '../api'
import { fmtCount } from '../JoinMap'

// 데이터별 내용 범위와 커버리지 수준 — 검색·필터·정렬, 행을 누르면 설명서.

export type Level = '상' | '중' | '하'

/** 커버리지 수준 — 범위(전국/지역) × 단위(개별 원장/집계) × 규모 */
export function level(r: DocsRow): Level {
  const nation = r.spatial === '전국'
  const unit = (r.unit ?? '').split('(')[0]
  const record = ['개별', '필지·건물'].includes(unit)
  if (nation && record && (r.rows ?? 0) >= 1000) return '상'
  if (nation || (record && (r.spatial === '시도' || r.spatial === '시군구'))) return '중'
  return '하'
}

const PAGE = 25
const SORTS: Record<string, (a: DocsRow, b: DocsRow) => number> = {
  rows: (a, b) => (b.rows ?? -1) - (a.rows ?? -1),
  edges: (a, b) => b.edges - a.edges,
  lag: (a, b) => (a.lag ?? 1e9) - (b.lag ?? 1e9),
  claims: (a, b) => b.claims - a.claims,
  title: (a, b) => a.title.localeCompare(b.title, 'ko'),
}

export function DataTable({ rows, keyFilter, onKeyFilter, open }: {
  rows: DocsRow[]
  keyFilter: string
  onKeyFilter: (k: string) => void
  open: (id: string) => void
}) {
  const [q, setQ] = useState('')
  const [sector, setSector] = useState('')
  const [tier, setTier] = useState('verified')
  const [lv, setLv] = useState('')
  const [sort, setSort] = useState('rows')
  const [page, setPage] = useState(1)

  const sectors = useMemo(() => [...new Set(rows.map((r) => r.sector))].sort(), [rows])
  const keys = useMemo(() => [...new Set(rows.flatMap((r) => r.keys))].sort(), [rows])
  const shown = useMemo(() => {
    const s = q.trim().toLowerCase()
    return rows
      .filter((r) => (!tier || r.tier === tier) && (!sector || r.sector === sector) && (!keyFilter || r.keys.includes(keyFilter))
        && (!lv || level(r) === lv) && (!s || r.title.toLowerCase().includes(s) || (r.agency ?? '').toLowerCase().includes(s) || r.id.includes(s)))
      .sort(SORTS[sort])
  }, [rows, q, sector, tier, lv, keyFilter, sort])
  const pages = Math.max(1, Math.ceil(shown.length / PAGE))
  const cur = shown.slice((Math.min(page, pages) - 1) * PAGE, Math.min(page, pages) * PAGE)
  const reset = <T,>(f: (v: T) => void) => (v: T) => { f(v); setPage(1) }

  return (
    <div className="doc-table">
      <div className="doc-filters">
        <AgentTextField search size="sm" placeholder="데이터·기관·목록키 검색" value={q} onChange={(e) => reset(setQ)(e.target.value)} />
        <AgentSelect size="sm" value={tier} onChange={(e) => reset(setTier)(e.target.value)}
          options={[{ value: 'verified', label: '검증됨' }, { value: 'candidate', label: '후보' }, { value: '', label: '전체' }]} />
        <AgentSelect size="sm" value={sector} onChange={(e) => reset(setSector)(e.target.value)}
          options={[{ value: '', label: '모든 부문' }, ...sectors.map((s) => ({ value: s, label: s }))]} />
        <AgentSelect size="sm" value={keyFilter} onChange={(e) => reset(onKeyFilter)(e.target.value)}
          options={[{ value: '', label: '모든 키' }, ...keys.map((k) => ({ value: k, label: `키 ${k}` }))]} />
        <AgentSelect size="sm" value={lv} onChange={(e) => reset(setLv)(e.target.value)}
          options={[{ value: '', label: '모든 수준' }, { value: '상', label: '커버리지 상' }, { value: '중', label: '커버리지 중' }, { value: '하', label: '커버리지 하' }]} />
        <AgentSelect size="sm" value={sort} onChange={(e) => setSort(e.target.value)}
          options={[{ value: 'rows', label: '건수 많은 순' }, { value: 'edges', label: '조인 많은 순' }, { value: 'lag', label: '최신 순' },
            { value: 'claims', label: '근거 많은 순' }, { value: 'title', label: '이름순' }]} />
      </div>
      <p className="doc-small">{shown.length.toLocaleString()}건{keyFilter ? ` · 키 ${keyFilter}` : ''} — 이름을 누르면 설명서가 열립니다.</p>
      <AgentTable
        caption="데이터별 범위와 커버리지"
        columns={[
          { key: 'title', label: '데이터' }, { key: 'sector', label: '부문' }, { key: 'path', label: '경로' },
          { key: 'rows', label: '건수', numeric: true }, { key: 'scope', label: '범위·단위' }, { key: 'lag', label: '최신성' },
          { key: 'keys', label: '조인 키' }, { key: 'edges', label: '조인', numeric: true }, { key: 'rate', label: '실측' },
          { key: 'claims', label: '근거', numeric: true }, { key: 'level', label: '수준' },
        ]}
        rows={cur.map((r) => {
          const l = level(r)
          return {
            key: r.id,
            title: <button type="button" className="doc-link-btn" onClick={() => open(r.id)} title={r.agency ?? ''}>{r.title}</button>,
            sector: r.sector,
            path: r.channel === 'external' ? '외부 사이트' : r.kind === 'API' || r.kind === 'api' ? '포털 API' : '파일',
            rows: r.rows != null ? fmtCount(r.rows) : '—',
            scope: `${r.spatial ?? '미상'} · ${(r.unit ?? '미상').split('(')[0]}`,
            lag: r.lag == null ? '관찰 전' : r.lag <= 1 ? '하루 이내' : `${r.lag}일 전`,
            keys: r.keys.slice(0, 3).join(', ') || '—',
            edges: r.edges,
            rate: r.rate == null ? '—' : `${Math.round(r.rate * 100)}%`,
            claims: r.claims,
            level: <AgentChip variant={l === '상' ? 'live' : l === '중' ? 'primary' : 'neutral'}>{l}</AgentChip>,
          }
        })}
      />
      <AgentPagination page={Math.min(page, pages)} pageCount={pages} onChange={setPage} label="데이터 표 페이지" />
    </div>
  )
}
