import { useEffect, useState } from 'react'
import { AgentChip, AgentPagination, AgentSelect, AgentTable, AgentTextField } from '@bv-ds/ui'
import { docsTable, type DocsRow, type DocsTablePage } from '../api'
import { fmtCount } from '../JoinMap'

// 데이터별 내용 범위와 커버리지 수준 — 검색·필터·정렬은 서버(/api/docs/datasets)가 하고 한 쪽(25행)만 받는다. 행을 누르면 설명서.

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


export function DataTable({ sectors, keys, keyFilter, onKeyFilter, open }: {
  sectors: string[]
  keys: string[]
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
  const [data, setData] = useState<DocsTablePage | null>(null)
  const [err, setErr] = useState('')

  useEffect(() => {  // 검색어는 잠깐 멈췄을 때만 요청
    let live = true
    const t = setTimeout(() => {
      docsTable({ q, tier, sector, key: keyFilter, lv, sort, page })
        .then((r) => { if (live) { setData(r); setErr('') } })
        .catch((e: Error) => { if (live) setErr(e.message) })
    }, q ? 250 : 0)
    return () => { live = false; clearTimeout(t) }
  }, [q, tier, sector, keyFilter, lv, sort, page])
  const reset = <T,>(f: (v: T) => void) => (v: T) => { f(v); setPage(1) }
  const cur = data?.rows ?? []
  const pages = data?.pages ?? 1

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
        <AgentSelect size="sm" value={sort} onChange={(e) => reset(setSort)(e.target.value)}
          options={[{ value: 'rows', label: '건수 많은 순' }, { value: 'edges', label: '조인 많은 순' }, { value: 'lag', label: '최신 순' },
            { value: 'claims', label: '근거 많은 순' }, { value: 'title', label: '이름순' }]} />
      </div>
      <p className="doc-small">{err ? `표를 불러오지 못했습니다: ${err}` : data ? `${data.total.toLocaleString()}건${keyFilter ? ` · 키 ${keyFilter}` : ''} — 이름을 누르면 설명서가 열립니다.` : '불러오는 중…'}</p>
      <AgentTable
        caption="데이터별 범위와 커버리지"
        columns={[
          { key: 'title', label: '데이터' }, { key: 'sector', label: '부문' }, { key: 'path', label: '경로' },
          { key: 'rows', label: '건수', numeric: true }, { key: 'scope', label: '범위·단위' }, { key: 'lag', label: '최신성' },
          { key: 'keys', label: '조인 키' }, { key: 'edges', label: '조인', numeric: true }, { key: 'rate', label: '실측' },
          { key: 'claims', label: '근거', numeric: true }, { key: 'level', label: '수준' },
        ]}
        rows={cur.map((r) => {
          const l = r.level
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
