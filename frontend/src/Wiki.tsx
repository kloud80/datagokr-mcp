import { useEffect, useMemo, useState, type ReactNode } from 'react'
import {
  AgentAlert,
  AgentBreadcrumb,
  AgentButton,
  AgentCheckbox,
  AgentChip,
  AgentEmptyState,
  AgentModal,
  AgentPagination,
  AgentSegmentedControl,
  AgentSelect,
  AgentSkeleton,
  AgentTable,
  AgentTabs,
  AgentTextField,
  AgentTextarea,
} from '@bv-ds/ui'
import {
  wikiApi,
  type WikiClaim,
  type WikiCodePage,
  type WikiCodeRow,
  type WikiDsRef,
  type WikiFacets,
  type WikiKeyPage,
  type WikiKeyRow,
  type WikiPageOut,
  type WikiProposal,
  type WikiRelation,
  type WikiRow,
  type WikiSearchParams,
} from './api'
import { Markdown } from './md'
import { Credit } from './Credit'

// Wiki — knowledge/datasets의 yaml을 찾아 읽고, 관계·키를 따라 옮겨 다니고, 수정을 제안한다.
// 경로: #/wiki?q=… 데이터셋 탐색 · #/wiki/d/{id} 데이터 문서 · #/wiki/keys 키 목록 · #/wiki/k/{key} 키 문서
//       #/wiki/codes 코드표 목록 · #/wiki/c/{id} 코드표 문서 · #/wiki/review 제안 검토(승인권자)
// 제안은 바로 반영되지 않는다 — 승인권자가 승인하면 yaml에 admin_review 근거로 들어간다.

const n = (v?: number | null) => (v ?? 0).toLocaleString()
const pct = (v?: number | null) => (v == null ? null : `${Math.round(v * 1000) / 10}%`)
const go = (path: string) => { window.location.hash = path }
const dsHref = (id: string) => `#/wiki/d/${encodeURIComponent(id)}`
const keyHref = (k: string) => `#/wiki/k/${encodeURIComponent(k)}`
const codeHref = (c: string) => `#/wiki/c/${encodeURIComponent(c)}`
type Section = 'datasets' | 'keys' | 'codes' | 'review'
const sectionOf = (route: string): Section =>
  route === 'keys' || route === 'k' ? 'keys' : route === 'codes' || route === 'c' ? 'codes' : route === 'review' ? 'review' : 'datasets'
const portal = (id: string) => `https://www.data.go.kr/data/${id}/openapi.do`

const REL_LABEL: Record<string, string> = { joinable: '조인', lookup: '조회(lookup)', related_to: '관련' }
const STATUS_LABEL: Record<string, string> = { pending: '검토 대기', approved: '승인', rejected: '반려' }
const EVIDENCE_LABEL: Record<string, string> = {
  measured: '실측', law: '법령', admin_review: '검토 결정', portal_meta: '포털 등록값', inferred: '추론(승인 전)', user: '사용자',
}
const GROUNDED = new Set(['measured', 'law', 'admin_review'])

function parse(hash: string): { route: string; arg: string; query: URLSearchParams } {
  const [path, q = ''] = hash.replace(/^#\/wiki\/?/, '').split('?')
  const [route = '', ...rest] = path.split('/')
  return { route, arg: decodeURIComponent(rest.join('/')), query: new URLSearchParams(q) }
}

export function Wiki({ hash }: { hash: string }) {
  const { route, arg, query } = parse(hash)
  const [facets, setFacets] = useState<WikiFacets | null>(null)
  const [pending, setPending] = useState<number | null>(null)
  useEffect(() => { wikiApi.facets().then(setFacets).catch(() => {}) }, [])
  useEffect(() => { wikiApi.proposals({ status: 'pending' }).then((r) => setPending(r.counts.pending ?? 0)).catch(() => setPending(null)) }, [hash])

  return (
    <div className="doc-page">
      <header className="doc-top wiki-top">
        <a className="doc-back" href="#/">← 공공데이터 전략 도우미</a>
        <h1 className="doc-title"><a href="#/wiki" className="wiki-home">Wiki</a></h1>
        <TopSearch section={sectionOf(route)} initial={['', 'keys', 'codes'].includes(route) ? query.get('q') ?? '' : ''} />
        <a className="doc-small" href="#/docs">Docs</a>
        <a className="doc-small" href="#/mcp">MCP</a>
        <a className="doc-small wiki-review-link" href="#/wiki/review">제안 검토{pending ? <b>{n(pending)}</b> : null}</a>
      </header>
      <nav className="wiki-sections" aria-label="위키 구분">
        {([['datasets', '#/wiki', '데이터셋', facets?.counts.datasets], ['keys', '#/wiki/keys', '키', facets?.counts.keys],
          ['codes', '#/wiki/codes', '코드표', facets?.counts.codes]] as [Section, string, string, number | undefined][]).map(([k, href, label, c]) => (
          <a key={k} href={href} className={sectionOf(route) === k ? 'on' : ''} aria-current={sectionOf(route) === k ? 'page' : undefined}>
            {label}{c != null ? <span>{n(c)}</span> : null}</a>
        ))}
      </nav>
      {route === 'd' ? <DatasetPage id={arg} facets={facets} />
        : route === 'k' ? <KeyPage keyId={arg} page={Number(query.get('page') || 1)} />
        : route === 'keys' ? <KeysList q={query.get('q') ?? ''} />
        : route === 'c' ? <CodePage codeId={arg} />
        : route === 'codes' ? <CodesList q={query.get('q') ?? ''} />
        : route === 'review' ? <ReviewPage />
        : <Home query={query} facets={facets} />}
      <div className="wiki-credit"><Credit /></div>
    </div>
  )
}

const SEARCH: Record<Section, [string, string]> = {
  datasets: ['/wiki', '데이터 이름·기관·필드·포털 ID로 찾기'], review: ['/wiki', '데이터 이름·기관·필드·포털 ID로 찾기'],
  keys: ['/wiki/keys', '키 이름·id·발급 기관으로 찾기 (예: 사업자, pnu)'], codes: ['/wiki/codes', '코드표 이름·id·컬럼 이름으로 찾기 (예: 법정동, 업종)'],
}

function TopSearch({ section, initial }: { section: Section; initial: string }) {
  const [q, setQ] = useState(initial)
  useEffect(() => setQ(initial), [initial])
  const [path, ph] = SEARCH[section]
  return (
    <form className="wiki-topsearch" role="search" onSubmit={(e) => { e.preventDefault(); go(q.trim() ? `${path}?q=${encodeURIComponent(q.trim())}` : path) }}>
      <AgentTextField search size="sm" aria-label="위키 검색" placeholder={ph} value={q} onChange={(e) => setQ(e.target.value)} />
    </form>
  )
}

// ─────────── 탐색
function Home({ query, facets }: { query: URLSearchParams; facets: WikiFacets | null }) {
  const p: WikiSearchParams = {
    q: query.get('q') ?? '', sector: query.get('sector') ?? '', agency: query.get('agency') ?? '', grade: query.get('grade') ?? '',
    key: query.get('key') ?? '', linked: query.get('linked') === '1', sort: query.get('sort') ?? 'relevance', page: Number(query.get('page') || 1),
  }
  const k = JSON.stringify(p)
  const [res, setRes] = useState<{ total: number; size: number; rows: WikiRow[] } | null>(null)
  const [err, setErr] = useState<string | null>(null)
  useEffect(() => {
    setRes(null); setErr(null)
    wikiApi.search(p).then(setRes).catch((e: Error) => setErr(e.message))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [k])
  const set = (patch: Partial<WikiSearchParams>) => {
    const next = { ...p, page: 1, ...patch }
    const s = new URLSearchParams(Object.entries(next).filter(([, v]) => v !== '' && v !== false && v !== 'relevance' && !(typeof v === 'number' && v <= 1))
      .map(([a, v]) => [a, v === true ? '1' : String(v)]))
    go(`/wiki${s.toString() ? `?${s}` : ''}`)
  }
  const pages = res ? Math.max(1, Math.ceil(res.total / res.size)) : 1

  return (
    <div className="doc-layout">
      <nav className="doc-toc wiki-side" aria-label="부문">
        <p className="doc-toc-h">정책 분야</p>
        <ul className="wiki-facet">
          <li><button type="button" className={!p.sector ? 'on' : ''} onClick={() => set({ sector: '' })}>전체</button></li>
          {facets?.sectors.map(([s, c]) => (
            <li key={s}><button type="button" className={p.sector === s ? 'on' : ''} onClick={() => set({ sector: s })}><em>{s}</em><span>{n(c)}</span></button></li>
          ))}
        </ul>
        <p className="doc-toc-h">많이 쓰이는 키 <a href="#/wiki/keys" className="wiki-x">전체 보기</a></p>
        <ul className="wiki-facet">
          {facets?.keys.slice(0, 16).map(([key, c]) => (
            <li key={key}><a href={keyHref(key)} title={key}><em>{key}</em><span>{n(c)}</span></a></li>
          ))}
        </ul>
      </nav>
      <main className="doc-main">
        <div className="wiki-filters">
          <AgentSelect size="sm" label="기관" value={p.agency} onChange={(e) => set({ agency: e.target.value })}
            options={[{ value: '', label: '전체 기관' }, ...(facets?.agencies ?? []).map(([a, c]) => ({ value: a, label: `${a} (${n(c)})` }))]} />
          <AgentSelect size="sm" label="등급" value={p.grade} onChange={(e) => set({ grade: e.target.value })}
            options={[{ value: '', label: '전체' }, ...(facets?.grades ?? []).map(([g, c]) => ({ value: g, label: `${g} (${n(c)})` }))]} />
          <AgentSegmentedControl size="sm" label="정렬" value={p.sort} onChange={(v) => set({ sort: v })}
            options={[{ value: 'relevance', label: p.q ? '관련도' : '연결 많은 순' }, { value: 'edges', label: '연결 많은 순' }, { value: 'title', label: '이름순' }]
              .filter((o, i, a) => a.findIndex((x) => x.label === o.label) === i)} />
          <AgentCheckbox label="실측된 관계가 있는 것만" checked={!!p.linked} onChange={(e) => set({ linked: e.target.checked })} />
        </div>
        {p.key ? <p className="doc-small">키 <a href={keyHref(p.key)}>{p.key}</a>를 쓰는 데이터만 <button type="button" className="wiki-x" onClick={() => set({ key: '' })}>거르기 해제</button></p> : null}
        {err ? <AgentAlert tone="error" title="불러오지 못했습니다">{err}</AgentAlert>
          : !res ? <AgentSkeleton variant="text" lines={10} />
          : !res.rows.length ? <AgentEmptyState title="찾은 데이터가 없습니다" description="다른 낱말로 찾거나 거르기를 풀어 보세요." />
          : (<>
            <p className="doc-small">{p.q ? `‘${p.q}’ ` : ''}{n(res.total)}건{p.q && res.total >= 600 ? ' (관련도 상위 600건)' : ''}</p>
            <ul className="wiki-list">{res.rows.map((r) => <RowCard key={r.id} r={r} />)}</ul>
            {pages > 1 ? <AgentPagination page={p.page} pageCount={pages} onChange={(pg) => set({ page: pg })} label="결과 페이지" /> : null}
          </>)}
      </main>
    </div>
  )
}

function RowCard({ r, fields }: { r: WikiRow; fields?: string[] }) {
  return (
    <li className="wiki-card">
      <div className="wiki-card-h">
        <a href={dsHref(r.id)} className="wiki-card-t">{r.title}</a>
        <span className="wiki-id">{r.id}</span>
      </div>
      <div className="wiki-meta">
        <span>{r.agency}</span><span>{r.sector.split('/').slice(0, 2).join(' › ')}</span><span>{r.kind}</span>
        {r.grade !== '핵심' ? <AgentChip variant="neutral">{r.grade}</AgentChip> : null}
        {r.tier === 'candidate' ? <AgentChip variant="new">후보</AgentChip> : null}
      </div>
      {r.summary ? <p className="wiki-sum">{r.summary}</p> : null}
      <div className="wiki-meta">
        <span>관계 {n(r.edges)} · 실측 {n(r.measured)}</span>
        {fields?.length ? <span>필드 {fields.join(', ')}</span> : null}
        {r.keys.slice(0, 5).map((k) => <a key={k} className="wiki-key" href={keyHref(k)}>{k}</a>)}
      </div>
    </li>
  )
}

// ─────────── 데이터 문서
type Tab = 'about' | 'fields' | 'relations' | 'claims' | 'dossier' | 'proposals'

function DatasetPage({ id, facets }: { id: string; facets: WikiFacets | null }) {
  const [d, setD] = useState<WikiPageOut | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [tab, setTab] = useState<Tab>('about')
  const [props, setProps] = useState<WikiProposal[] | null>(null)
  const [draft, setDraft] = useState<{ kind: string; target?: string } | null>(null)
  const [sent, setSent] = useState<number | null>(null)
  const loadProps = () => wikiApi.proposals({ dataset: id }).then((r) => setProps(r.rows)).catch(() => setProps([]))
  useEffect(() => {
    setD(null); setErr(null); setTab('about'); setSent(null); window.scrollTo(0, 0)
    wikiApi.page(id).then(setD).catch((e: Error) => setErr(e.message))
    void loadProps()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id])

  if (err) {
    return (
      <div className="doc-single">
        <AgentAlert tone="info" title="지식 체계에 없는 데이터">
          {id}는 아직 검증되지 않아 위키 문서가 없습니다. <a href={portal(id)} target="_blank" rel="noreferrer">포털에서 보기</a>
        </AgentAlert>
      </div>
    )
  }
  if (!d) return <div className="doc-single"><AgentSkeleton variant="text" lines={14} /></div>
  const ds = d.dataset
  const [field, part] = ds.sector.split('/')
  const pend = (props ?? []).filter((p) => p.status === 'pending').length
  const relTotal = Object.values(d.relation_totals).reduce((a, b) => a + b, 0)

  return (
    <div className="doc-single wiki-doc">
      <AgentBreadcrumb label="위치" items={[{ label: 'Wiki', href: '#/wiki' }, { label: field, href: `#/wiki?sector=${encodeURIComponent(field)}` },
        { label: part }, { label: ds.title }]} />
      <header className="wiki-head">
        <h2 className="wiki-h">{ds.title}</h2>
        <div className="wiki-meta">
          <span className="wiki-id">{ds.id}</span>
          <a href={`#/wiki?agency=${encodeURIComponent(ds.agency.name)}`}>{ds.agency.name}</a>
          {ds.team?.dept ? <span>{ds.team.dept}</span> : null}
          <span>{ds.kind} · {ds.channel === 'portal' ? '포털' : '외부 사이트'}</span>
          {ds.accrual_periodicity ? <span>갱신 {ds.accrual_periodicity}</span> : null}
          <AgentChip variant={ds.tier === 'verified' ? 'primary' : 'new'}>{ds.tier === 'verified' ? '검증됨' : '후보'}</AgentChip>
          {(ds.facets?.grade ?? []).map((g) => <AgentChip key={g} variant="neutral">{g}</AgentChip>)}
          {ds.status && ds.status !== 'active' ? <AgentChip variant="hot">{ds.status}</AgentChip> : null}
        </div>
        <div className="wiki-actions">
          {ds.portal_url ? <a className="wiki-btnlink" href={ds.portal_url} target="_blank" rel="noreferrer">포털에서 보기 ↗</a> : null}
          <AgentButton size="sm" variant="secondary" onClick={() => setDraft({ kind: 'summary' })}>수정 제안</AgentButton>
        </div>
      </header>
      {sent ? <AgentAlert tone="success" title={`제안 #${sent}을 받았습니다`}>승인권자가 검토한 뒤 반영 여부를 정합니다. ‘제안’ 탭에서 진행 상황을 볼 수 있습니다.</AgentAlert> : null}

      <AgentTabs label="문서 구획" value={tab} onChange={(v) => setTab(v as Tab)} items={[
        { id: 'about', label: '개요', content: tab === 'about' ? <About d={d} onPropose={setDraft} /> : null },
        { id: 'fields', label: `필드 ${n(ds.schema?.fields?.length)}`, content: tab === 'fields' ? <Fields d={d} onPropose={setDraft} /> : null },
        { id: 'relations', label: `관계 ${n(relTotal)}`, content: tab === 'relations' ? <Relations d={d} onPropose={setDraft} /> : null },
        { id: 'claims', label: `사실·근거 ${n(ds.claims?.length)}`, content: tab === 'claims' ? <Claims claims={ds.claims ?? []} onPropose={setDraft} /> : null },
        { id: 'dossier', label: '설명서', content: tab === 'dossier' ? (d.dossier_md ? <Markdown text={d.dossier_md} open={(x) => go(`/wiki/d/${x}`)} />
          : <AgentEmptyState compact title="설명서가 아직 없습니다" />) : null },
        { id: 'proposals', label: `제안${pend ? ` · 대기 ${pend}` : ''}`, content: tab === 'proposals' ? <ProposalList rows={props} showDataset={false} /> : null },
      ]} />
      <p className="doc-small wiki-file">원본: <code>{d.file}</code></p>
      {draft ? <ProposeModal d={d} kinds={facets?.kinds} initial={draft} onClose={() => setDraft(null)}
        onSent={(p) => { setDraft(null); setSent(p.id); void loadProps() }} /> : null}
    </div>
  )
}

function KV({ rows }: { rows: [string, ReactNode][] }) {
  const shown = rows.filter(([, v]) => v !== null && v !== undefined && v !== '')
  return <dl className="wiki-kv">{shown.map(([k, v]) => <div key={k}><dt>{k}</dt><dd>{v}</dd></div>)}</dl>
}

const FACET_LABEL: Record<string, string> = {
  spatial: '공간 범위', admin_unit: '행정 단위', temporal: '기간', space: '공간 단위', space_fields: '공간 필드', space_via: '잇는 방법',
  time: '시간 단위', time_fields: '시간 필드', category: '분류', category_fields: '분류 필드', entity: '한 행', entity_fields: '행 식별 필드',
}
const fmt = (o?: Record<string, unknown> | null): string | null =>
  o ? Object.entries(o).filter(([, v]) => v !== null && v !== '' && !(Array.isArray(v) && !v.length))
    .map(([k, v]) => `${FACET_LABEL[k] ?? k} ${Array.isArray(v) ? v.join('·') : typeof v === 'object' ? fmt(v as Record<string, unknown>) : String(v)}`).join(' / ') : null

type Propose = (x: { kind: string; target?: string }) => void

function About({ d, onPropose }: { d: WikiPageOut; onPropose: Propose }) {
  const ds = d.dataset
  return (
    <div className="wiki-sec">
      <h3 className="doc-h3">무엇을 담은 데이터인가 <button type="button" className="wiki-x" onClick={() => onPropose({ kind: 'summary' })}>고쳐 쓰기 제안</button></h3>
      <p className="doc-p">{ds.summary_user ?? <span className="doc-small">아직 사람이 쓴 설명이 없습니다.</span>}</p>
      {ds.description_portal ? <details className="wiki-details"><summary>포털 등록 설명 원문</summary><p className="doc-p">{ds.description_portal}</p></details> : null}
      {ds.limits ? (<><h3 className="doc-h3">주의할 점</h3><p className="doc-p wiki-pre">{ds.limits}</p></>) : null}
      <h3 className="doc-h3">범위와 단위</h3>
      <KV rows={[
        ['세부 부문', ds.classification?.subsector_name], ['범위', fmt(ds.coverage)], ['단위', fmt(ds.grain)],
        ['파일·서비스', [...(ds.distributions ?? []).map((x) => x.format?.toUpperCase()), ...(ds.services ?? []).map((x) => x.name)].filter(Boolean).join(', ')],
      ]} />
      <h3 className="doc-h3">이 데이터를 잇는 키</h3>
      {d.keys.length ? (
        <ul className="wiki-chips">{d.keys.map((k) => <li key={k.id}><a className="wiki-key" href={keyHref(k.id)}>{k.name}</a><span className="doc-small"> {n(k.datasets)}건이 함께 씀</span></li>)}</ul>
      ) : <p className="doc-small">실측된 전역 조인 키가 없습니다.</p>}
      <CodeLinks fields={ds.schema?.fields ?? []} />
      <h3 className="doc-h3">검색어 <button type="button" className="wiki-x" onClick={() => onPropose({ kind: 'synonym' })}>검색어 추가 제안</button></h3>
      <ul className="wiki-chips">{(ds.synonyms ?? []).map((s) => <li key={s}><AgentChip variant="neutral">{s}</AgentChip></li>)}</ul>
      {d.family.length ? (<>
        <h3 className="doc-h3">같은 가족(지역판·연도판) {n(d.family.length)}건</h3>
        <ul className="wiki-links">{d.family.map((f) => <li key={f.id}><a href={dsHref(f.id)}>{f.title}</a> <span className="doc-small">{f.agency}</span></li>)}</ul>
      </>) : null}
    </div>
  )
}

function CodeLinks({ fields }: { fields: { name: string; code_list?: string | null }[] }) {
  const cl = fields.filter((f) => f.code_list)
  if (!cl.length) return null
  return (<>
    <h3 className="doc-h3">코드값의 뜻 — 코드표</h3>
    <ul className="wiki-chips">{cl.map((f) => <li key={f.name}><a className="wiki-key wiki-key--code" href={codeHref(f.code_list!)}>{f.code_list}</a><span className="doc-small"> ← {f.name}</span></li>)}</ul>
  </>)
}

function Fields({ d, onPropose }: { d: WikiPageOut; onPropose: Propose }) {
  const fields = d.dataset.schema?.fields ?? []
  const notes = useMemo(() => {
    const m: Record<string, string[]> = {}
    for (const c of d.dataset.claims ?? []) {
      const f = c.qualifiers?.field
      if (typeof f === 'string') (m[f] ||= []).push(c.value.replace(/^필드 '[^']*': /, ''))
    }
    return m
  }, [d])
  if (!fields.length) return <AgentEmptyState compact title="실측 필드가 없습니다" description="아직 표본을 내려받지 못한 데이터입니다." />
  return (
    <div className="wiki-sec">
      <AgentTable caption="필드 (실측 표본 기준)" columns={[{ key: 'name', label: '필드' }, { key: 'type', label: '형식' }, { key: 'skey', label: '키·코드표' },
        { key: 'null', label: '빈 값', numeric: true }, { key: 'sample', label: '표본 값' }, { key: 'note', label: '설명' }]}
        rows={fields.map((f) => ({
          key: f.name,
          name: <span><b>{f.name}</b>{f.title && f.title !== f.name ? <span className="doc-small"> {f.title}</span> : null}</span>,
          type: f.type ?? '',
          skey: <span className="wiki-chips">{f.semantic_type ? <a className="wiki-key" href={keyHref(f.semantic_type)}>{f.semantic_type}</a> : null}
            {f.code_list ? <a className="wiki-key wiki-key--code" href={codeHref(f.code_list)}>{f.code_list}</a> : null}</span>,
          null: f.null_rate == null ? '' : pct(f.null_rate),
          sample: <span className="wiki-sample">{(f.sample_values ?? []).slice(0, 3).map(String).join(' · ')}</span>,
          note: <span>{[f.description, ...(notes[f.name] ?? [])].filter(Boolean).join(' / ')}{' '}
            <button type="button" className="wiki-x" onClick={() => onPropose({ kind: 'field', target: f.name })}>설명 제안</button></span>,
        }))} />
    </div>
  )
}

function Relations({ d, onPropose }: { d: WikiPageOut; onPropose: Propose }) {
  const [q, setQ] = useState('')
  const [rel, setRel] = useState('all')
  const rows = d.relations.filter((r) => (rel === 'all' || r.rel === rel)
    && (!q || `${r.other} ${r.other_title ?? ''} ${r.other_agency ?? ''} ${(r.left ?? []).join(' ')} ${(r.right ?? []).join(' ')}`.toLowerCase().includes(q.toLowerCase())))
  const hints = d.dataset.edges_hint ?? []
  return (
    <div className="wiki-sec">
      <p className="doc-p">조인은 규칙이 만들고 실제 데이터로 매칭률을 잽니다. 사람이 승인한 관계 제안은 아래 ‘검토로 확인된 관계’에 먼저 들어가고, 다음 조인 생성·실측 때 정식 조인이 됩니다.</p>
      <div className="wiki-filters">
        <AgentSegmentedControl size="sm" label="종류" value={rel} onChange={setRel}
          options={[{ value: 'all', label: '전체' }, ...Object.entries(d.relation_totals).map(([k, c]) => ({ value: k, label: `${REL_LABEL[k] ?? k} ${n(c)}` }))]} />
        <AgentTextField size="sm" search aria-label="관계 거르기" placeholder="상대 데이터·필드로 거르기" value={q} onChange={(e) => setQ(e.target.value)} />
        <AgentButton size="sm" variant="secondary" onClick={() => onPropose({ kind: 'relation' })}>관계 제안</AgentButton>
      </div>
      {hints.length ? (<>
        <h3 className="doc-h3">검토로 확인된 관계</h3>
        <ul className="wiki-links">{hints.map((h) => <li key={h}><a href={dsHref(h)}>{h}</a></li>)}</ul>
      </>) : null}
      {!rows.length ? <AgentEmptyState compact title="해당하는 관계가 없습니다" /> : (
        <ul className="wiki-rels">{rows.map((r) => <RelRow key={r.edge} r={r} />)}</ul>
      )}
      {Object.entries(d.relation_totals).some(([k, c]) => c > d.relations.filter((r) => r.rel === k).length)
        ? <p className="doc-small">관계가 많은 허브 데이터라 종류마다 매칭률 높은 순으로 200개까지만 보여줍니다.</p> : null}
    </div>
  )
}

function RelRow({ r }: { r: WikiRelation }) {
  const on = [r.left?.join(', '), r.right?.join(', ')]
  const how = [r.transform ? `규칙 ${r.transform}` : null, r.via_mapping ? `매핑 ${r.via_mapping}` : null, r.relationship].filter(Boolean).join(' · ')
  const rate = r.match_rate
  return (
    <li className="wiki-rel">
      <span className={`wiki-rel-k wiki-rel-k--${r.rel}`}>{REL_LABEL[r.rel] ?? r.rel}</span>
      <div className="wiki-rel-b">
        <div>
          <span className="doc-small">{r.dir === 'out' ? '→' : '←'} </span>
          {r.other_known ? <a href={dsHref(r.other)}>{r.other_title ?? r.other}</a>
            : <a href={portal(r.other)} target="_blank" rel="noreferrer">{r.other_title ?? r.other} ↗</a>}
          <span className="wiki-id"> {r.other}</span>
          {r.other_agency ? <span className="doc-small"> · {r.other_agency}</span> : null}
        </div>
        {(on[0] || on[1]) ? <div className="doc-small"><code>{on[0] || '—'}</code> = <code>{on[1] || '—'}</code>{how ? ` · ${how}` : ''}</div>
          : how ? <div className="doc-small">{how}</div> : null}
        {r.note ? <div className="doc-small">{r.note}</div> : null}
      </div>
      <span className={`wiki-rate${rate == null ? ' wiki-rate--none' : rate >= 0.95 ? ' wiki-rate--ok' : rate >= 0.5 ? ' wiki-rate--mid' : ' wiki-rate--low'}`}
        title={r.measured_at ? `실측 ${r.measured_at}` : '아직 실측 전이거나 판정 보류'}>
        {rate == null ? (r.rel === 'related_to' ? '' : '미측정') : `매칭 ${pct(rate)}`}
      </span>
    </li>
  )
}

function Claims({ claims, onPropose }: { claims: WikiClaim[]; onPropose: Propose }) {
  return (
    <div className="wiki-sec">
      <p className="doc-p">실측·법령·검토 결정 근거가 있는 진술만 사실로 씁니다. 근거가 포털 등록값뿐인 진술은 ‘미확인’입니다.
        <button type="button" className="wiki-x" onClick={() => onPropose({ kind: 'note' })}>사실·의견 제안</button></p>
      <ul className="wiki-claims">
        {claims.map((c) => {
          const ok = c.evidence.some((e) => GROUNDED.has(e.type))
          return (
            <li key={c.id} className={ok ? '' : 'wiki-claim--weak'}>
              <div className="wiki-meta"><b>{c.kind}</b><span className="wiki-id">{c.id}</span>{ok ? null : <AgentChip variant="neutral">미확인</AgentChip>}
                {c.qualifiers?.source === 'wiki' ? <AgentChip variant="new">위키 제안 #{String(c.qualifiers.proposal)}</AgentChip> : null}</div>
              <p className="doc-p">{c.value}</p>
              <div className="doc-small">{c.evidence.map((e, i) => (
                <span key={i} className="wiki-ev">{EVIDENCE_LABEL[e.type] ?? e.type} · {e.source}{e.by ? ` · ${e.by}` : ''}{e.at || e.observed_at ? ` · ${e.at ?? e.observed_at}` : ''}</span>
              ))}</div>
            </li>
          )
        })}
      </ul>
    </div>
  )
}

// ─────────── 제안
function ProposeModal({ d, kinds, initial, onClose, onSent }: {
  d: WikiPageOut; kinds?: Record<string, string>; initial: { kind: string; target?: string }; onClose: () => void; onSent: (p: WikiProposal) => void
}) {
  const ds = d.dataset
  const [kind, setKind] = useState(initial.kind)
  const [target, setTarget] = useState(initial.target ?? '')
  const [value, setValue] = useState(initial.kind === 'summary' ? ds.summary_user ?? '' : '')
  const [reason, setReason] = useState('')
  const [author, setAuthor] = useState(() => { try { return localStorage.getItem('pds-wiki-author') ?? '' } catch { return '' } })
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const K = kinds ?? { summary: '설명 고쳐 쓰기', synonym: '검색어 추가', limit: '주의사항 추가', field: '필드 설명', relation: '다른 데이터와의 관계', note: '그 밖의 사실·의견' }
  const hint: Record<string, string> = {
    summary: '누가 무엇을 확인하는 데 쓰는지, 무엇이 한 행인지, 무엇으로 다른 데이터와 잇는지를 쓰면 좋습니다.',
    synonym: '사람들이 이 데이터를 찾을 때 쓸 낱말을 쉼표로 나눠 적어 주세요.',
    limit: '써 보며 겪은 함정 — 빠진 지역·기간, 바뀐 코드, 늦은 갱신 같은 것.',
    field: '이 필드에 실제로 무엇이 들어 있는지, 코드라면 어떤 코드표인지.',
    relation: '어떤 필드끼리 맞추면 이어지는지, 확인해 본 예시 값이 있으면 함께.',
    note: '데이터에 대한 사실이나 의견. 출처가 있으면 함께 적어 주세요.',
  }
  const submit = async () => {
    setBusy(true); setErr(null)
    try { localStorage.setItem('pds-wiki-author', author) } catch { /* 저장 불가 */ }
    try {
      const p = await wikiApi.propose({ dataset_id: ds.id, kind, proposed_value: value, target: target || undefined, reason: reason || undefined, author: author || undefined })
      onSent(p)
    } catch (e) { setErr((e as Error).message) } finally { setBusy(false) }
  }
  return (
    <AgentModal open title="수정 제안" description={`${ds.title} — 바로 반영되지 않고 승인권자가 검토합니다.`} onClose={onClose}
      actions={<><AgentButton variant="ghost" onClick={onClose}>취소</AgentButton>
        <AgentButton variant="primary" disabled={busy || !value.trim() || ((kind === 'field' || kind === 'relation') && !target)} onClick={() => void submit()}>제안 보내기</AgentButton></>}>
      <div className="wiki-form">
        <AgentSelect label="무엇을" value={kind} onChange={(e) => { setKind(e.target.value); setTarget(''); setValue(e.target.value === 'summary' ? ds.summary_user ?? '' : '') }}
          options={Object.entries(K).map(([v, l]) => ({ value: v, label: l }))} />
        {kind === 'field' ? <AgentSelect label="필드" value={target} onChange={(e) => setTarget(e.target.value)}
          options={[{ value: '', label: '필드를 고르세요' }, ...(ds.schema?.fields ?? []).map((f) => ({ value: f.name, label: f.name }))]} /> : null}
        {kind === 'relation' ? <AgentTextField label="상대 데이터 포털 ID" placeholder="예: 15012005" value={target} onChange={(e) => setTarget(e.target.value.trim())} /> : null}
        <AgentTextarea label={kind === 'summary' ? '새 설명' : '내용'} rows={kind === 'summary' ? 6 : 4} value={value} onChange={(e) => setValue(e.target.value)} />
        <p className="doc-small">{hint[kind]}</p>
        <AgentTextarea label="근거·이유 (선택)" rows={2} value={reason} onChange={(e) => setReason(e.target.value)} />
        <AgentTextField label="이름 (선택)" placeholder="검토자가 연락할 수 있게" value={author} onChange={(e) => setAuthor(e.target.value)} />
        {err ? <AgentAlert tone="error" title="보내지 못했습니다">{err}</AgentAlert> : null}
      </div>
    </AgentModal>
  )
}

function ProposalList({ rows, showDataset, reviewer, onReviewed }: {
  rows: WikiProposal[] | null; showDataset: boolean; reviewer?: string | null; onReviewed?: () => void
}) {
  if (!rows) return <AgentSkeleton variant="text" lines={5} />
  if (!rows.length) return <AgentEmptyState compact title="제안이 없습니다" description="문서의 ‘수정 제안’으로 첫 제안을 남겨 보세요." />
  return <ul className="wiki-props">{rows.map((p) => <ProposalItem key={p.id} p={p} showDataset={showDataset} reviewer={reviewer} onReviewed={onReviewed} />)}</ul>
}

function ProposalItem({ p, showDataset, reviewer, onReviewed }: { p: WikiProposal; showDataset: boolean; reviewer?: string | null; onReviewed?: () => void }) {
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const act = async (decision: 'approve' | 'reject') => {
    setBusy(true); setErr(null)
    try { await wikiApi.review(p.id, decision, note || undefined); onReviewed?.() } catch (e) { setErr((e as Error).message) } finally { setBusy(false) }
  }
  return (
    <li className={`wiki-prop wiki-prop--${p.status}`}>
      <div className="wiki-meta">
        <b>#{p.id}</b>
        <AgentChip variant={p.status === 'approved' ? 'primary' : p.status === 'rejected' ? 'neutral' : 'live'}>{STATUS_LABEL[p.status]}</AgentChip>
        <span>{({ summary: '설명', synonym: '검색어', limit: '주의사항', field: '필드', relation: '관계', note: '사실·의견' } as Record<string, string>)[p.kind] ?? p.kind}
          {p.target ? <> · {p.kind === 'relation' ? <a href={dsHref(p.target)}>{p.target}</a> : <code>{p.target}</code>}</> : null}</span>
        {showDataset ? <a href={dsHref(p.dataset_id)}>데이터 {p.dataset_id}</a> : null}
        <span className="doc-small">{p.author ?? '익명'} · {p.created_at.slice(0, 16).replace('T', ' ')}</span>
      </div>
      {p.current_value && p.kind === 'summary' ? (
        <div className="wiki-diff"><div><p className="doc-small">지금</p><p className="doc-p">{p.current_value}</p></div>
          <div><p className="doc-small">제안</p><p className="doc-p">{p.proposed_value}</p></div></div>
      ) : <p className="doc-p wiki-pre">{p.proposed_value}</p>}
      {p.reason ? <p className="doc-small">이유: {p.reason}</p> : null}
      {p.status !== 'pending' ? (
        <p className="doc-small">{STATUS_LABEL[p.status]} — {p.reviewer} · {p.reviewed_at?.slice(0, 16).replace('T', ' ')}{p.review_note ? ` · ${p.review_note}` : ''}
          {p.applied ? ` · 반영: ${[p.applied.field, p.applied.claim].filter(Boolean).join(', ')}` : ''}</p>
      ) : reviewer ? (
        <div className="wiki-review">
          <AgentTextField size="sm" aria-label="검토 의견" placeholder="검토 의견 (선택 — 반려라면 이유를)" value={note} onChange={(e) => setNote(e.target.value)} />
          <AgentButton size="sm" variant="primary" disabled={busy} onClick={() => void act('approve')}>승인·반영</AgentButton>
          <AgentButton size="sm" variant="secondary" disabled={busy} onClick={() => void act('reject')}>반려</AgentButton>
        </div>
      ) : null}
      {err ? <AgentAlert tone="error" title="처리하지 못했습니다">{err}</AgentAlert> : null}
    </li>
  )
}

function ReviewPage() {
  const [status, setStatus] = useState('pending')
  const [rows, setRows] = useState<WikiProposal[] | null>(null)
  const [counts, setCounts] = useState<Record<string, number>>({})
  const [err, setErr] = useState<string | null>(null)
  const [reviewer, setReviewer] = useState<string | null>(null)
  const [token, setToken] = useState('')
  const load = () => { setRows(null); wikiApi.proposals({ status }).then((r) => { setRows(r.rows); setCounts(r.counts) }).catch((e: Error) => setErr(e.message)) }
  useEffect(load, [status]) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { wikiApi.me().then((r) => setReviewer(r.reviewer)).catch(() => {}) }, [])
  const login = async () => {
    const r = await wikiApi.me(token).catch(() => ({ reviewer: null }))
    if (r.reviewer) { wikiApi.setToken(token); setReviewer(r.reviewer); setToken('') } else setErr('승인권자 토큰이 맞지 않습니다')
  }
  return (
    <div className="doc-single wiki-doc">
      <AgentBreadcrumb label="위치" items={[{ label: 'Wiki', href: '#/wiki' }, { label: '제안 검토' }]} />
      <h2 className="wiki-h">제안 검토</h2>
      <p className="doc-p">누구나 문서에 수정·의견을 제안할 수 있고, 반영 여부는 승인권자가 정합니다. 승인하면 데이터 yaml에 <b>검토 결정(admin_review)</b> 근거로 들어가
        승인자 이름·날짜·제안 번호가 함께 남습니다. 반려된 제안도 이유와 함께 기록됩니다.</p>
      <div className="wiki-filters">
        <AgentSegmentedControl size="sm" label="상태" value={status} onChange={setStatus}
          options={['pending', 'approved', 'rejected'].map((s) => ({ value: s, label: `${STATUS_LABEL[s]} ${n(counts[s])}` }))} />
        {reviewer ? <span className="doc-small">승인권자 <b>{reviewer}</b>로 검토 중 <button type="button" className="wiki-x" onClick={() => { wikiApi.setToken(''); setReviewer(null) }}>나가기</button></span> : (
          <form className="wiki-login" onSubmit={(e) => { e.preventDefault(); void login() }}>
            <AgentTextField size="sm" type="password" aria-label="승인권자 토큰" placeholder="승인권자 토큰" value={token} onChange={(e) => setToken(e.target.value)} />
            <AgentButton size="sm" variant="secondary" type="submit" disabled={!token}>승인권자로 들어가기</AgentButton>
          </form>
        )}
      </div>
      {err ? <AgentAlert tone="error" title="문제가 있습니다">{err}</AgentAlert> : null}
      <ProposalList rows={rows} showDataset reviewer={reviewer} onReviewed={load} />
    </div>
  )
}

// ─────────── 키
const KEY_TYPE: Record<string, string> = { primary: '기본 키', foreign: '외래 키', natural: '자연 키', unique: '고유 키' }
const KEY_SCOPE: Record<string, string> = { global: '전역', family: '가족 안' }
const PAGE = 100

function useList<T>(load: () => Promise<T[]>, dep: string) {
  const [rows, setRows] = useState<T[] | null>(null)
  const [err, setErr] = useState<string | null>(null)
  useEffect(() => { setRows(null); setErr(null); load().then(setRows).catch((e: Error) => setErr(e.message)) }, [dep]) // eslint-disable-line react-hooks/exhaustive-deps
  return { rows, err }
}

function ListShell({ title, lead, q, total, err, children, page, pageCount, onPage }: {
  title: string; lead: ReactNode; q: string; total?: number; err: string | null; children: ReactNode; page: number; pageCount: number; onPage: (p: number) => void
}) {
  return (
    <div className="doc-single wiki-doc">
      <AgentBreadcrumb label="위치" items={[{ label: 'Wiki', href: '#/wiki' }, { label: title }]} />
      <h2 className="wiki-h">{title}</h2>
      <p className="doc-p">{lead}</p>
      {total != null ? <p className="doc-small">{q ? `‘${q}’ ` : ''}{n(total)}개</p> : null}
      {err ? <AgentAlert tone="error" title="불러오지 못했습니다">{err}</AgentAlert> : children}
      {pageCount > 1 ? <AgentPagination page={page} pageCount={pageCount} onChange={onPage} label={`${title} 페이지`} /> : null}
    </div>
  )
}

function KeysList({ q }: { q: string }) {
  const { rows, err } = useList<WikiKeyRow>(() => wikiApi.keys(q), q)
  const [page, setPage] = useState(1)
  useEffect(() => setPage(1), [q])
  const shown = (rows ?? []).slice((page - 1) * PAGE, page * PAGE)
  return (
    <ListShell title="키" q={q} total={rows?.length} err={err} page={page} pageCount={Math.ceil((rows?.length ?? 0) / PAGE)} onPage={setPage}
      lead={<>데이터와 데이터를 잇는 식별자입니다 — 사업자등록번호·필지(PNU)·법정동 코드처럼 여러 기관이 함께 쓰는 <b>전역 키</b>와 한 기관 안에서만 통하는 <b>기관 고유 키</b>가 있습니다. 같은 키를 가진 데이터끼리는 조인 후보가 됩니다.</>}>
      {!rows ? <AgentSkeleton variant="text" lines={12} /> : !rows.length ? <AgentEmptyState title="찾은 키가 없습니다" /> : (
        <AgentTable caption="키 목록 — 쓰는 데이터가 많은 순" columns={[{ key: 'name', label: '키' }, { key: 'kind', label: '종류' }, { key: 'issuer', label: '발급' },
          { key: 'ds', label: '쓰는 데이터', numeric: true }, { key: 'more', label: '원장·매핑·코드표' }]}
          rows={shown.map((k) => ({
            key: k.id,
            name: <span><a href={keyHref(k.id)}><b>{k.name}</b></a> <span className="wiki-id">{k.id}</span></span>,
            kind: `${KEY_TYPE[k.type ?? ''] ?? k.type ?? ''}${k.scope ? ` · ${KEY_SCOPE[k.scope] ?? k.scope}` : ''}`,
            issuer: k.issuer ?? (k.agency ? `기관 ${k.agency}` : ''),
            ds: n(k.datasets),
            more: [k.masters ? `원장 ${k.masters}` : '', k.mappings ? `매핑 ${k.mappings}` : '', k.codes ? `코드표 ${k.codes}` : ''].filter(Boolean).join(' · '),
          }))} />
      )}
    </ListShell>
  )
}

function DsRefLink({ r }: { r: WikiDsRef }) {
  return (
    <>
      {r.known ? <a href={dsHref(r.id)}>{r.title ?? r.id}</a> : <a href={portal(r.id)} target="_blank" rel="noreferrer">{r.title ?? r.id} ↗</a>}
      <span className="wiki-id"> {r.id}</span>{r.agency ? <span className="doc-small"> · {r.agency}</span> : null}
      {r.fields?.length ? <span className="doc-small"> · 필드 <code>{r.fields.join(', ')}</code></span> : null}
    </>
  )
}

function KeyPage({ keyId, page }: { keyId: string; page: number }) {
  const [d, setD] = useState<WikiKeyPage | null>(null)
  const [err, setErr] = useState<string | null>(null)
  useEffect(() => { setD(null); setErr(null); wikiApi.key(keyId, page).then(setD).catch((e: Error) => setErr(e.message)) }, [keyId, page])
  if (err) return <div className="doc-single"><AgentAlert tone="error" title="키를 찾지 못했습니다">{err}</AgentAlert></div>
  if (!d) return <div className="doc-single"><AgentSkeleton variant="text" lines={10} /></div>
  const k = d.key
  const pages = Math.max(1, Math.ceil(d.total / d.size))
  return (
    <div className="doc-single wiki-doc">
      <AgentBreadcrumb label="위치" items={[{ label: 'Wiki', href: '#/wiki' }, { label: '키', href: '#/wiki/keys' }, { label: k.name }]} />
      <header className="wiki-head">
        <h2 className="wiki-h">{k.name}</h2>
        <div className="wiki-meta">
          <span className="wiki-id">{k.id}</span>
          {k.type ? <AgentChip variant="neutral">{KEY_TYPE[k.type] ?? k.type}</AgentChip> : null}
          {k.scope ? <AgentChip variant={k.scope === 'global' ? 'primary' : 'neutral'}>{KEY_SCOPE[k.scope] ?? k.scope}</AgentChip> : null}
        </div>
      </header>
      <KV rows={[['형식', k.format], ['검증 정규식', k.pattern ? <code>{k.pattern}</code> : null], ['발급', k.issuer], ['운영 기관', k.agency],
        ['다른 이름', (k.shape_names ?? []).join(', ')], ['메모', k.notes]]} />
      {d.masters.length ? (<><h3 className="doc-h3">원장 — 이 키의 전체 값을 가진 데이터</h3>
        <ul className="wiki-links">{d.masters.map((m) => <li key={m.id}><DsRefLink r={m} /></li>)}</ul></>) : null}
      {d.composed_of.length || d.related.length ? (<><h3 className="doc-h3">관련 키</h3>
        <ul className="wiki-links">
          {d.composed_of.map((c) => <li key={`c-${c.key}`}>구성 요소 <a href={keyHref(c.key)}>{c.name ?? c.key}</a> <span className="wiki-id">{c.key}</span></li>)}
          {d.related.map((r, i) => <li key={`r-${i}`}>{r.relation} <a href={keyHref(r.key)}>{r.name ?? r.key}</a> <span className="wiki-id">{r.key}</span>{r.note ? <span className="doc-small"> · {r.note}</span> : null}</li>)}
        </ul></>) : null}
      {d.mappings.length ? (<><h3 className="doc-h3">매핑 — 다른 코드 체계로 바꾸는 표</h3>
        <AgentTable caption="매핑" columns={[{ key: 'm', label: '매핑' }, { key: 'how', label: '방법' }, { key: 'rows', label: '행', numeric: true }, { key: 'rate', label: '매칭률', numeric: true }]}
          rows={d.mappings.map((m) => ({ key: m.id, m: <span><a href={keyHref(m.left.key)}>{m.left.key}</a> ({m.left.system}) → <a href={keyHref(m.right.key)}>{m.right.key}</a> ({m.right.system})</span>,
            how: m.method ?? '', rows: n(m.rows), rate: pct(m.match_rate) ?? '' }))} /></>) : null}
      {d.codes.length ? (<><h3 className="doc-h3">코드표</h3>
        <ul className="wiki-chips">{d.codes.map((c) => <li key={c.id}><a className="wiki-key wiki-key--code" href={codeHref(c.id)}>{c.name}</a><span className="doc-small"> {n(c.rows)}개 값</span></li>)}</ul></>) : null}
      <h3 className="doc-h3">이 키를 가진 데이터 {n(d.total)}건</h3>
      <p className="doc-small">같은 키를 쓰는 데이터끼리는 조인 후보가 됩니다. 실측된 관계가 많은 순입니다. <a href={`#/wiki?key=${encodeURIComponent(k.id)}`}>검색·거르기와 함께 보기</a></p>
      <ul className="wiki-list">{d.rows.map((r) => <RowCard key={r.id} r={r} fields={r.fields} />)}</ul>
      {pages > 1 ? <AgentPagination page={page} pageCount={pages} onChange={(pg) => go(`/wiki/k/${encodeURIComponent(keyId)}?page=${pg}`)} label="키 데이터 페이지" /> : null}
      <p className="doc-small wiki-file">원본: <code>{d.file}</code></p>
    </div>
  )
}

// ─────────── 코드표
const COMPLETE_TONE: Record<string, 'primary' | 'secondary' | 'neutral'> = { complete: 'primary', master_scan: 'secondary', observed: 'neutral' }
const COMPLETE_SHORT: Record<string, string> = { complete: '전체', master_scan: '원장 전수', observed: '표본' }

function CodesList({ q }: { q: string }) {
  const { rows, err } = useList<WikiCodeRow>(() => wikiApi.codes(q), q)
  const [page, setPage] = useState(1)
  useEffect(() => setPage(1), [q])
  const shown = (rows ?? []).slice((page - 1) * PAGE, page * PAGE)
  return (
    <ListShell title="코드표" q={q} total={rows?.length} err={err} page={page} pageCount={Math.ceil((rows?.length ?? 0) / PAGE)} onPage={setPage}
      lead={<>코드값 → 이름 표입니다. 응답에 <code>clCd=31</code>처럼 코드만 오는 필드를 사람 말로 풀고, 조회 파라미터에 정확한 코드를 넣을 때 씁니다.
        <b> 전체</b>는 공식 원천 전체, <b>원장 전수</b>는 전수 원장에서 실제로 쓰이는 값 전부, <b>표본</b>은 표본에서 본 값만입니다.</>}>
      {!rows ? <AgentSkeleton variant="text" lines={12} /> : !rows.length ? <AgentEmptyState title="찾은 코드표가 없습니다" /> : (
        <AgentTable caption="코드표 목록 — 쓰는 데이터가 많은 순" columns={[{ key: 'name', label: '코드표' }, { key: 'c', label: '범위' }, { key: 'rows', label: '값', numeric: true },
          { key: 'key_', label: '키' }, { key: 'ds', label: '쓰는 데이터', numeric: true }, { key: 'al', label: '실리는 컬럼' }]}
          rows={shown.map((c) => ({
            key: c.id,
            name: <span><a href={codeHref(c.id)}><b>{c.name}</b></a> <span className="wiki-id">{c.id}</span></span>,
            c: <AgentChip variant={COMPLETE_TONE[c.completeness] ?? 'neutral'}>{COMPLETE_SHORT[c.completeness] ?? c.completeness}</AgentChip>,
            rows: n(c.rows),
            key_: c.key ? <a className="wiki-key" href={keyHref(c.key)}>{c.key}</a> : '',
            ds: n(c.datasets),
            al: <span className="wiki-sample">{c.aliases.slice(0, 4).join(', ')}</span>,
          }))} />
      )}
    </ListShell>
  )
}

function CodePage({ codeId }: { codeId: string }) {
  const [d, setD] = useState<WikiCodePage | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [q, setQ] = useState('')
  const [applied, setApplied] = useState('')
  useEffect(() => { setQ(''); setApplied('') }, [codeId])
  useEffect(() => { setErr(null); wikiApi.code(codeId, applied).then(setD).catch((e: Error) => setErr(e.message)) }, [codeId, applied])
  if (err) return <div className="doc-single"><AgentAlert tone="error" title="코드표를 찾지 못했습니다">{err}</AgentAlert></div>
  if (!d || d.code.id !== codeId) return <div className="doc-single"><AgentSkeleton variant="text" lines={10} /></div>
  const c = d.code
  const cols = [...new Set(d.values.flatMap((v) => Object.keys(v)))].filter((k) => !['code', 'name'].includes(k)).slice(0, 4)
  return (
    <div className="doc-single wiki-doc">
      <AgentBreadcrumb label="위치" items={[{ label: 'Wiki', href: '#/wiki' }, { label: '코드표', href: '#/wiki/codes' }, { label: c.name }]} />
      <header className="wiki-head">
        <h2 className="wiki-h">{c.name}</h2>
        <div className="wiki-meta">
          <span className="wiki-id">{c.id}</span>
          <AgentChip variant={COMPLETE_TONE[c.completeness] ?? 'neutral'}>{c.completeness_label}</AgentChip>
          <span>값 {n(c.rows)}개</span>
          {c.key ? <span>키 <a className="wiki-key" href={keyHref(c.key)}>{c.key_name ?? c.key}</a></span> : null}
        </div>
      </header>
      <KV rows={[['실리는 컬럼', (c.aliases ?? []).join(', ')], ['메모', c.notes],
        ['근거', c.evidence.map((e, i) => <span key={i} className="wiki-ev">{EVIDENCE_LABEL[e.type] ?? e.type} · {e.source}{e.observed_at || e.at ? ` · ${e.observed_at ?? e.at}` : ''}{e.detail ? ` · ${e.detail}` : ''}</span>)]]} />
      <h3 className="doc-h3">이 코드를 쓰는 데이터 {n(d.used_by.length)}건</h3>
      {d.used_by.length ? <ul className="wiki-links">{d.used_by.map((u) => <li key={u.id}><DsRefLink r={u} /></li>)}</ul>
        : <p className="doc-small">아직 필드와 연결된 데이터가 없습니다.</p>}
      <h3 className="doc-h3">코드값</h3>
      <form className="wiki-filters" onSubmit={(e) => { e.preventDefault(); setApplied(q.trim()) }}>
        <AgentTextField size="sm" search aria-label="코드값 찾기" placeholder="코드나 이름으로 찾기" value={q} onChange={(e) => setQ(e.target.value)} />
        <AgentButton size="sm" variant="secondary" type="submit">찾기</AgentButton>
        {applied ? <button type="button" className="wiki-x" onClick={() => { setQ(''); setApplied('') }}>전체 보기</button> : null}
      </form>
      <p className="doc-small">{applied ? `‘${applied}’ ${n(d.values_shown)}개` : `앞에서 ${n(d.values_shown)}개`}{c.rows > d.values_shown && !applied ? ` (전체 ${n(c.rows)}개 — 찾기로 좁혀 보세요)` : ''}</p>
      {d.values.length ? (
        <AgentTable caption="코드값" columns={[{ key: 'code', label: '코드' }, { key: 'name', label: '이름' }, ...cols.map((k) => ({ key: `x_${k}`, label: k }))]}
          rows={d.values.map((v, i) => ({ key: `${String(v.code)}-${i}`, code: <code>{String(v.code ?? '')}</code>, name: String(v.name ?? ''),
            ...Object.fromEntries(cols.map((k) => [`x_${k}`, v[k] == null ? '' : String(v[k])])) }))} />
      ) : <AgentEmptyState compact title="해당하는 코드값이 없습니다" />}
      <p className="doc-small wiki-file">원본: <code>{d.file}</code>{c.file ? <> · 값 <code>knowledge/{c.file}</code></> : null}</p>
    </div>
  )
}
