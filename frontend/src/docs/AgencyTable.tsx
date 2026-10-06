import { useMemo, useState } from 'react'
import { AgentChip, AgentPagination, AgentSelect, AgentTable, AgentTextField } from '@bv-ds/ui'
import type { AgencyRow } from '../api'

// 기관별 핵심 데이터와 관계 — knowledge/agencies (A등급은 Opus 기관 분석: 운영 시스템·핵심 원장·고유 키·관계·빠진 핵심)

const PAGE = 15
const TYPE: Record<string, string> = { central: '중앙부처', public: '공공기관', metro: '광역', local: '기초', education: '교육', other: '기타' }

export function AgencyTable({ rows }: { rows: AgencyRow[] }) {
  const [q, setQ] = useState('')
  const [tier, setTier] = useState('')
  const [page, setPage] = useState(1)
  const [open, setOpen] = useState<string | null>(null)
  const shown = useMemo(() => {
    const s = q.trim()
    return rows.filter((r) => (!tier || r.tier === tier) && (!s || r.name.includes(s)))
  }, [rows, q, tier])
  const pages = Math.max(1, Math.ceil(shown.length / PAGE))
  const cur = shown.slice((Math.min(page, pages) - 1) * PAGE, Math.min(page, pages) * PAGE)
  const sel = rows.find((r) => r.id === open)
  return (
    <div className="doc-table">
      <div className="doc-filters">
        <AgentTextField search size="sm" placeholder="기관 검색" value={q} onChange={(e) => { setQ(e.target.value); setPage(1) }} />
        <AgentSelect size="sm" value={tier} onChange={(e) => { setTier(e.target.value); setPage(1) }}
          options={[{ value: '', label: 'A·B 전체' }, { value: 'A', label: 'A 중앙·공공 (정밀 분석)' }, { value: 'B', label: 'B 광역' }]} />
      </div>
      <p className="doc-small">{shown.length.toLocaleString()}곳 · 기관 이름을 누르면 운영 시스템과 고유 키가 펼쳐집니다.</p>
      <AgentTable
        caption="기관별 핵심 데이터와 관계"
        columns={[{ key: 'name', label: '기관' }, { key: 'catalog', label: '목록', numeric: true }, { key: 'verified', label: '검증', numeric: true },
          { key: 'core', label: '핵심', numeric: true }, { key: 'systems', label: '시스템', numeric: true }, { key: 'keys', label: '고유 키', numeric: true },
          { key: 'within', label: '기관 안 조인', numeric: true }, { key: 'across', label: '기관 밖 조인', numeric: true }, { key: 'missing', label: '빠진 핵심', numeric: true }]}
        rows={cur.map((r) => ({
          key: r.id,
          name: <button type="button" className="pds-card-title" onClick={() => setOpen(open === r.id ? null : r.id)}>
            {r.name} <AgentChip variant={r.tier === 'A' ? 'primary' : 'neutral'}>{r.tier} · {TYPE[r.type] ?? r.type}</AgentChip></button>,
          catalog: (r.catalog ?? 0).toLocaleString(), verified: (r.verified ?? 0).toLocaleString(), core: (r.core ?? 0).toLocaleString(),
          systems: r.systems.length || '—', keys: r.keys.length || '—', within: r.edges_within || '—', across: r.edges_across || '—',
          missing: r.core_missing || '—',
        }))}
      />
      <AgentPagination page={Math.min(page, pages)} pageCount={pages} onChange={setPage} label="기관 표 페이지" />
      {sel ? (
        <div className="doc-card">
          <b>{sel.name}</b>{sel.portal ? <span className="doc-small"> · 자체 개방 사이트 {sel.portal}</span> : null}
          {sel.note ? <p className="doc-p">{sel.note}</p> : null}
          {sel.systems.length ? <ul className="doc-facts">{sel.systems.map((s) => <li key={s.name}>{s.name} — 데이터 {s.n} · 핵심 {s.core}</li>)}</ul> : <p className="doc-small">아직 기관 분석 전입니다.</p>}
          {sel.keys.length ? <p className="doc-small">고유 키: {sel.keys.map((k) => <code key={k} className="pds-code">{k}</code>)}</p> : null}
          {sel.gaps.length ? <p className="doc-small">공백: {sel.gaps.join(' · ')}</p> : null}
        </div>
      ) : null}
    </div>
  )
}
