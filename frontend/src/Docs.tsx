import { useEffect, useMemo, useState, type ReactNode } from 'react'
import {
  AgentAccordion,
  AgentButton,
  AgentChip,
  AgentKpiCard,
  AgentSkeleton,
  AgentTable,
  AgentTabs,
  BarChart,
  PieChart,
  ProportionBar,
} from '@bv-ds/ui'
import { docsApi, type DocsData } from './api'
import { DatasetDrawer } from './DatasetDrawer'
import { Diagram, type DLink, type DNode } from './docs/Diagram'
import { DataTable, level } from './docs/DataTable'
import { SiteTable } from './docs/SiteTable'
import { fmtCount } from './JoinMap'
import { TrustLegend } from './Trust'

// Docs — 이 시스템을 설명하는 문서. 숫자는 /api/docs에서 실시간으로 (지식 체계가 늘면 같이 바뀐다).

const TOC = [
  { id: 'philosophy', n: 1, t: '작성 사상' },
  { id: 'tech', n: 2, t: '구성 기술' },
  { id: 'standard', n: 3, t: '표준과 데이터별 구성' },
  { id: 'relations', n: 4, t: '관계의 정의' },
  { id: 'scope', n: 5, t: '데이터 대상과 커버리지' },
  { id: 'sites', n: 6, t: '가입이 필요한 사이트' },
  { id: 'progress', n: 7, t: '지금까지 진행된 사항' },
  { id: 'verified', n: 8, t: '확인된 관계와 데이터' },
  { id: 'coverage', n: 9, t: '데이터별 범위와 커버리지 수준' },
]

const n = (v?: number | null) => (v ?? 0).toLocaleString()
const entries = (o: Record<string, number>, order?: string[]): [string, number][] =>
  (order ? order.filter((k) => k in o).map((k): [string, number] => [k, o[k]]) : Object.entries(o).sort((a, b) => b[1] - a[1]))

function Section({ id, n: num, title, lead, children }: { id: string; n: number; title: string; lead?: ReactNode; children: ReactNode }) {
  return (
    <section id={id} className="doc-section">
      <h2 className="doc-h2"><span className="doc-num">{num}</span>{title}</h2>
      {lead ? <p className="doc-lead">{lead}</p> : null}
      {children}
    </section>
  )
}

function Code({ children, lang }: { children: string; lang?: string }) {
  const [ok, setOk] = useState(false)
  return (
    <div className="doc-code">
      <div className="doc-code-bar"><span>{lang}</span>
        <button type="button" onClick={() => { void navigator.clipboard?.writeText(children).then(() => { setOk(true); setTimeout(() => setOk(false), 1200) }) }}>{ok ? '복사됨' : '복사'}</button>
      </div>
      <pre>{children}</pre>
    </div>
  )
}

function Bars({ data, unit = '건', onPick, picked }: { data: [string, number][]; unit?: string; onPick?: (k: string) => void; picked?: string }) {
  const max = Math.max(1, ...data.map((d) => d[1]))
  return (
    <ul className="doc-bars">
      {data.map(([k, v]) => (
        <li key={k} className={picked === k ? 'doc-bars--on' : ''}>
          {onPick ? <button type="button" onClick={() => onPick(picked === k ? '' : k)}>{k}</button> : <span>{k}</span>}
          <div className="doc-bar"><i style={{ width: `${(v / max) * 100}%` }} /></div>
          <b>{n(v)}{unit}</b>
        </li>
      ))}
    </ul>
  )
}

const PRINCIPLES: [string, string][] = [
  ['① 실물 우선', '메타가 아니라 직접 불러 본 것만 믿는다. 모든 대상은 활용신청 → 키 → 실제 호출·다운로드 → 컬럼별 통계까지 했다. 예시값 착시 26건, 코드가 하나도 겹치지 않는 학교ID처럼 메타로는 안 보이는 것이 실측에서 드러났다.'],
  ['② 근거 없는 사실은 사실이 아니다', '모든 진술은 claim으로 저장하고 근거를 단다. 근거 6종 중 실측·법령·검토 결정이 있어야 "사실"이고, 포털 메타·AI 추론만 있으면 (미확인)으로 표시돼 전략의 근거로 나가지 못한다.'],
  ['③ 선언된 조인만 쓴다', '데이터를 잇는 방법은 Edge로 미리 선언하고 실제 데이터로 매칭률을 잰다. AI는 조인 조건을 만들지 않고 선언된 것 중에서 고르기만 한다. 경로가 없으면 없다고 말한다.'],
  ['④ 모델이 이미 아는 것은 가치가 낮다', '법령 본문처럼 널리 공개된 것보다 오늘 올라온 의안, 어제 낙찰된 입찰, 지금의 대기질처럼 모델이 모르는 시의성 있는 데이터를 높게 친다.'],
  ['⑤ 집계보다 원천, 일부보다 전수, 고립보다 연결', '건별 원천(공고 하나·점포 하나·필지 하나)을 통계보다 위에, 끝까지 받을 수 있는 전수 데이터를 더 위에, 조인 키가 있는 데이터를 더 위에 둔다.'],
  ['⑥ 부처의 분류가 아니라 국민의 질문으로', '흩어진 같은 시스템 데이터는 원래 시스템 기준으로 다시 모으고, 부처가 달라도 같은 질문(영유아 돌봄·동네 상권·이 땅에 무엇을 지을 수 있나)은 맥락(context)으로 잇는다.'],
  ['⑦ 코드표가 품질을 가른다', '대상 데이터 필드 1,910개를 전부 판정해 코드표 없이는 뜻을 알 수 없는 필드부터 정하고, 국가 표준 코드를 전수로 확보했다 (코드표 120종).'],
  ['⑧ 세 층은 섞이지 않는다', '검증(verified) · 후보(candidate) · 단서(catalog). 검증하지 않은 것을 검증한 것처럼 말하지 않으면서도 나머지 9만 건을 버리지 않는다 — 노출 → 사용 → 승격.'],
  ['⑨ 접근이 불편한 것은 깎지 않고 설명한다', '기관 사이트에 있는 API(브이월드·나이스·서울·법제처)도 점수를 깎지 않는다. 불편함은 어디서 어떤 절차로 키를 받는지, 접근 경로로 드러낸다.'],
  ['⑩ 사람이 확정하고, 결정은 기록으로', '부문 구분·대상·조인 확정은 사람이 하고, 결정은 날짜·결정자와 함께 파일(_review_log.md)에 남는다. 생성기는 그 줄을 admin_review 근거로 인용한다.'],
  ['⑪ 파일이 원본이고 나머지는 파생물', '지식의 원본은 knowledge/ YAML이다. DB·검색 색인·설명서는 모두 다시 만들 수 있는 파생물이고, 모든 파일은 스키마로 검증된다.'],
  ['⑫ 키는 사용자 것이고, 모르는 것은 모른다고 말한다', '저장소에는 어떤 키도 없다. 포털에 없는 업무 영역은 공백(gap)으로 기록하고, 조인 경로가 없으면 "미선언", 관찰 전이면 "근거 없음"이라고 쓴다.'],
]

const TIMELINE: { d: string; t: string; s: string }[] = [
  { d: '2026-09-28', t: '1단계 — 포털 목록과 분류', s: 'data.go.kr 전체 96,110건 목록을 받아 정책 분야·세부 부문으로 나누고, 활용·최신성·세부 단위·연결 가능성·시의성으로 점수를 매겼다. 부문 검토 원칙(원장·실시간 유지, 통계·보조 미룸)을 정했다.' },
  { d: '2026-09-29~30', t: '2단계 — 1차 검증', s: '세부 부문 대표 데이터를 실제로 활용신청·호출·다운로드해 265건을 검증했다(라운드 1~3).' },
  { d: '2026-09-30', t: '3단계 — 지식 체계', s: 'KNOWLEDGE-SPEC에 따라 Dataset·Claim·Edge·Key·CodeList·Context·Recipe 스키마를 세우고, 전수 원장으로 코드표 120종·매핑 7종·법령 43개를 만들고, 조인 365개를 선언·실측했다.' },
  { d: '2026-10-01', t: '서비스', s: '전략 플래너·REST API·MCP 서버·웹 채팅. LLM은 선택된 전략을 설명만 한다.' },
  { d: '2026-10-02', t: '화면 v2 · 실행 코드', s: 'BigValue 디자인 시스템 2열 화면, 지역 필터, 답과 전략의 일치(제외 도구), 검증 때 성공한 호출로 실행 코드를 생성.' },
  { d: '2026-10-02', t: '2차 확대 — 조인 키 기준', s: '열 정보로 조인 키가 보이는 5,689단위를 부문 검토 → 969건 검증 → 815건 편입.' },
  { d: '2026-10-02', t: '3차 확대 — 점수 상위 5,000건', s: '4,588단위 부문 검토 → 포털 502건 검증 → 391건 편입. 채팅 모델은 비교 후 Sonnet 5.5로.' },
  { d: '2026-10-02', t: '외부 사이트 (키 보유 4곳)', s: '브이월드·서울 열린데이터광장·법제처·나이스의 링크형 데이터 162건을 제공처 페이지에서 호출 주소를 찾아 검증 → 116건.' },
  { d: '2026-10-03', t: '사이트 커버리지 · Docs', s: '포털 링크형 21,988건의 제공처를 모두 조회해 1,309개 사이트로 묶고, 키 보유·검증 여부를 정리했다. 이 문서(Docs)를 만들었다.' },
]

export function Docs() {
  const [d, setD] = useState<DocsData | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [active, setActive] = useState('philosophy')
  const [keyFilter, setKeyFilter] = useState('')
  const [dsId, setDsId] = useState<string | null>(null)

  useEffect(() => { docsApi().then(setD).catch((e: Error) => setErr(e.message)) }, [])
  useEffect(() => {
    if (!d) return
    const obs = new IntersectionObserver((es) => {
      const v = es.filter((e) => e.isIntersecting).sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top)[0]
      if (v) setActive(v.target.id)
    }, { rootMargin: '-10% 0px -70% 0px' })
    TOC.forEach((s) => { const el = document.getElementById(s.id); if (el) obs.observe(el) })
    return () => obs.disconnect()
  }, [d])

  const go = (id: string) => document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  const pickKey = (k: string) => { setKeyFilter(k); if (k) setTimeout(() => document.querySelector('.doc-table')?.scrollIntoView({ block: 'start' }), 250) }

  const T = d?.totals ?? {}
  const levels = useMemo(() => {
    const c: Record<string, number> = { 상: 0, 중: 0, 하: 0 }
    d?.datasets.filter((r) => r.tier === 'verified').forEach((r) => { c[level(r)] += 1 })
    return c
  }, [d])

  if (err) return <div className="doc-page"><p>Docs를 불러오지 못했습니다: {err}</p></div>

  const arch: DNode[] = [
    { id: 'portal', x: 150, y: 16, label: 'data.go.kr 포털', sub: `목록 ${n(T.catalog)}건`, tone: 'source', detail: '공공데이터포털 전체 목록. 메타(제목·기관·분류·출력 항목)만 있는 출발점이다. 목록 스냅샷은 GitHub Release로 배포한다.' },
    { id: 'ext', x: 620, y: 16, label: '외부 사이트', sub: '브이월드·서울·법제처·나이스', tone: 'ext', detail: '포털에는 링크만 있고 실제 API는 기관 사이트에 있는 데이터. 제공처 페이지에서 호출 주소를 찾아 검증한다(pds/probe/external_sites.py).' },
    { id: 'rank', x: 20, y: 110, label: '분류·점수', sub: 'pds/rank', tone: 'service', detail: '정책 분야 → 세부 부문 분류, 제외 규칙, 활용·최신성·세부 단위·연결 가능성·시의성 점수.' },
    { id: 'review', x: 260, y: 110, label: '부문 검토', sub: '사람 결정 + LLM 초안', tone: 'service', detail: '원장·실시간은 유지, 통계·보조는 미룸, 잘못 분류된 것은 이동. 결정은 _review_log.md와 knowledge/expansion에 남는다.' },
    { id: 'probe', x: 500, y: 110, label: '실호출 검증', sub: '활용신청·호출·다운로드', tone: 'service', detail: '포털 활용신청(Playwright, 보안문자는 사람), API 호출·파일 다운로드, 컬럼별 셀 통계, 실데이터 값으로 키 판정(pds/probe).' },
    { id: 'master', x: 740, y: 110, label: '전수 원장·코드표', sub: '코드 120 · 매핑 7', tone: 'service', detail: '표본으로는 매칭률이 의미 없어서 원장을 끝까지 받는다(병원 8만·기관코드 41만·실거래 24만). 코드표는 필드 판정에서 출발.' },
    { id: 'core', x: 310, y: 210, w: 340, h: 60, label: 'knowledge/ — YAML 원본', sub: 'Dataset · Claim · Edge · Key · Code · Context · Recipe', tone: 'core', detail: '지식의 원본. git으로 이력·리뷰. 모든 파일은 pydantic 스키마로 검증된다(python -m pds validate).' },
    { id: 'val', x: 20, y: 320, label: '스키마 검증', sub: 'pydantic · JSON Schema', tone: 'derived', detail: '참조 무결성, 근거 규칙(사실 = 실측·법령·검토), 승격 조건(근거 3+ · Edge 1+), 선언되지 않은 Edge 사용 금지.' },
    { id: 'db', x: 250, y: 320, label: 'Postgres', sub: 'pds_* 테이블 (파생)', tone: 'derived', detail: '목록·분류·점수·지식 엔티티·지식 그래프를 적재한 파생 인덱스. 서비스는 DB 없이도 돈다. pds_* 테이블만 백업·복원.' },
    { id: 'idx', x: 480, y: 320, label: '검색 색인', sub: 'BM25 · 한글 2-gram', tone: 'derived', detail: '데이터셋·맥락·공백·포털 목록 검색. 지식 파일이 바뀌면 다시 만든다.' },
    { id: 'dossier', x: 710, y: 320, label: '설명서', sub: 'Markdown 1,500여 개', tone: 'derived', detail: '데이터마다 한 줄 요약·호출 방법·필드·키·근거·주의점을 담은 설명서 (docs/dossiers, 화면의 상세 서랍).' },
    { id: 'plan', x: 150, y: 420, label: '전략 플래너', sub: 'networkx · 선언 Edge만', tone: 'service', detail: '목표 → 맥락 매칭 → 검증 데이터 검색(지역 필터·가중치) → 선언된 Edge로 최단 조인 경로 → 파이프라인 → 검사(§4 규칙).' },
    { id: 'code', x: 400, y: 420, label: '코드 생성기', sub: 'requests + pandas', tone: 'service', detail: '검증 때 성공한 호출(주소·필수 파라미터·형식·실제 페이지 크기)을 다시 꾸며, 이 저장소 없이 돌아가는 Python을 만든다.' },
    { id: 'llm', x: 650, y: 420, label: 'LLM 설명', sub: 'Claude Sonnet 5.5', tone: 'service', detail: '고른 전략을 설명만 한다. 데이터는 [[id]]로 인용, 맞지 않는 데이터는 제외 도구로 전략에서 뺀다. 10문항 비교로 Haiku 대신 Sonnet을 기본으로.' },
    { id: 'api', x: 150, y: 516, label: 'REST API', sub: 'FastAPI · SSE', tone: 'use', detail: '/api/chat(/stream) · /api/plan · /api/search · /api/datasets · /api/codes · /api/stats · /api/docs' },
    { id: 'web', x: 400, y: 516, label: '웹 화면', sub: 'React + BV 디자인 시스템', tone: 'use', detail: '2열 화면: 대화(진행 단계 실시간) + 전략 패널(조인 지도·데이터 카드·단계·코드·단서). 지금 보고 있는 Docs도 여기.' },
    { id: 'mcp', x: 650, y: 516, label: 'MCP 서버', sub: 'Claude Desktop 등', tone: 'use', detail: 'plan_public_data_strategy · search_datasets · get_dataset · list_code_lists · lookup_code 도구와 dataset:// 리소스.' },
  ]
  const archLinks: DLink[] = [
    { from: 'portal', to: 'rank' }, { from: 'portal', to: 'review' }, { from: 'portal', to: 'probe' }, { from: 'ext', to: 'probe' }, { from: 'ext', to: 'master' },
    { from: 'rank', to: 'core' }, { from: 'review', to: 'core' }, { from: 'probe', to: 'core' }, { from: 'master', to: 'core' },
    { from: 'core', to: 'val' }, { from: 'core', to: 'db' }, { from: 'core', to: 'idx' }, { from: 'core', to: 'dossier' },
    { from: 'idx', to: 'plan' }, { from: 'plan', to: 'code' }, { from: 'plan', to: 'llm' },
    { from: 'plan', to: 'api' }, { from: 'llm', to: 'web' }, { from: 'code', to: 'web' }, { from: 'plan', to: 'mcp', dashed: true },
  ]
  const ent: DNode[] = [
    { id: 'claim', x: 380, y: 16, label: 'Claim', sub: `사실 진술 ${n(T.claims)}`, tone: 'core', detail: '데이터에 대한 진술 하나 — 접근·갱신·키·범위·법적 근거·주의점 등. 값과 근거(evidence)를 가진다.' },
    { id: 'ev', x: 640, y: 16, label: 'Evidence', sub: '근거 6종', tone: 'source', detail: '실측(measured) · 법령(law) · 검토 결정(admin_review)이 있어야 사실. 포털 메타·AI 추론·사용자는 보조.' },
    { id: 'law', x: 760, y: 120, label: 'Law', sub: '법령 43', tone: 'source', detail: '데이터가 존재하는 이유가 되는 법 조문. 법제처 원문을 근거로 연결한다.' },
    { id: 'ds', x: 370, y: 170, w: 190, h: 60, label: 'Dataset', sub: `검증 ${n(T.verified)} · 후보 ${n(T.candidate)}`, tone: 'core', detail: '데이터 하나. 호출 방법(services)·필드(schema)·범위(coverage)·주기·분류·근거 claim·검증 기록을 담는다.' },
    { id: 'field', x: 110, y: 170, label: 'Field', sub: '필드·의미 유형', tone: 'derived', detail: '응답 열 하나. 실측 통계(빈 값 비율·표본값)와 의미 유형(address·pnu·bizno…), 코드표 연결.' },
    { id: 'key', x: 110, y: 40, label: 'Key', sub: `키 유형 ${n(T.keys)}`, tone: 'derived', detail: '조인의 기준이 되는 식별자 체계 — PNU·법정동·사업자번호·기관코드·좌표·주소 등.' },
    { id: 'code', x: 110, y: 300, label: 'CodeList', sub: `코드표 ${n(T.code_lists)}`, tone: 'derived', detail: '코드값의 뜻. 공식 전체 / 원장에서 쓰이는 값 전부 / 표본에서 본 값만을 구분해 적는다.' },
    { id: 'edge', x: 640, y: 240, label: 'Edge', sub: `조인 ${n(T.edges)} · 실측 ${n(T.measured)}`, tone: 'core', detail: '두 데이터를 잇는 선언: 어느 열과 어느 열, 관계(다대일 등), 변환 규칙, 매핑표, 실측 매칭률.' },
    { id: 'map', x: 800, y: 340, label: 'Mapping', sub: `매핑 ${n(T.mappings)}`, tone: 'derived', detail: '코드 체계가 다른 두 키의 대응표 (예: K-apt 단지코드 ↔ 실거래 단지번호). 전수 원장으로 만들고 일치율을 잰다.' },
    { id: 'rule', x: 580, y: 360, label: 'Rule', sub: `변환 규칙 ${n(T.rules)}`, tone: 'derived', detail: 'R-02 시군구=법정동 앞 5자리, R-07 PNU 조립, R-12 좌표→PNU, R-13 주소→좌표, R-14 이름→코드 … 테스트가 있는 함수.' },
    { id: 'ctx', x: 370, y: 330, label: 'Context', sub: `맥락 ${n(T.contexts)}`, tone: 'service', detail: '부처가 달라도 같은 국민 질문으로 묶은 데이터 묶음과 그 차원(같은 생애 질문·같은 필지 규제·같은 키…).' },
    { id: 'recipe', x: 370, y: 430, label: 'Recipe', sub: `레시피 ${n(T.recipes)}`, tone: 'service', detail: '맥락별 표준 경로(데이터·조인·파이프라인). 지금은 자동 초안 — 사람이 확정하면 골든셋 경로가 된다.' },
    { id: 'iss', x: 800, y: 200, label: 'Issuer', sub: '키 발급처', tone: 'ext', detail: '외부 사이트 키 발급처(브이월드·나이스 등) — 어디서 어떤 절차로 키를 받는지. 추가외부키.md 참고.' },
  ]
  const entLinks: DLink[] = [
    { from: 'ds', to: 'claim', label: 'claims' }, { from: 'claim', to: 'ev', label: 'evidence' }, { from: 'claim', to: 'law', label: 'legal_basis', dashed: true },
    { from: 'ds', to: 'field', label: 'schema' }, { from: 'field', to: 'key', label: 'semantic_type' }, { from: 'field', to: 'code', label: 'code_list' },
    { from: 'ds', to: 'edge', label: 'src·dst' }, { from: 'edge', to: 'map', label: 'via_mapping' }, { from: 'edge', to: 'rule', label: 'transform' },
    { from: 'ctx', to: 'ds', label: 'members' }, { from: 'recipe', to: 'ctx' }, { from: 'ds', to: 'iss', label: 'access', dashed: true },
  ]

  return (
    <div className="doc-page">
      <header className="doc-top">
        <a className="doc-back" href="#/">← 공공데이터 전략 도우미</a>
        <h1 className="doc-title">Docs</h1>
        <span className="doc-small">{d ? `지식 버전 ${d.knowledge_version} · 실시간 집계` : '불러오는 중…'}</span>
      </header>
      <div className="doc-layout">
        <nav className="doc-toc" aria-label="목차">
          <p className="doc-toc-h">목차</p>
          <ol>
            {TOC.map((s) => (
              <li key={s.id}><button type="button" className={active === s.id ? 'on' : ''} onClick={() => go(s.id)}><span>{s.n}</span>{s.t}</button></li>
            ))}
          </ol>
        </nav>
        <main className="doc-main">
          {!d ? <AgentSkeleton variant="text" lines={12} /> : (<>
            <div className="doc-kpis">
              <AgentKpiCard label="검증된 데이터" value={n(T.verified)} unit="건" />
              <AgentKpiCard label="선언된 조인" value={n(T.edges)} unit="개" delta={`실측 ${n(T.measured)}`} />
              <AgentKpiCard label="근거 있는 사실" value={n(d.claims.grounded['근거 있음'])} unit="개" />
              <AgentKpiCard label="포털 목록(단서)" value={n(T.catalog)} unit="건" />
            </div>

            <Section id="philosophy" n={1} title="작성 사상"
              lead={<>공공데이터는 9만 건이 넘지만, "이 데이터들로 내 문제를 어떻게 풀까"에 답하려면 무엇이 실제로 불러지고, 무엇과 무엇이 실제로 이어지는지를 알아야 한다. 이 시스템은 그 지식을 <b>실측과 근거로만</b> 쌓고, AI에게는 <b>고르고 설명하는 일</b>만 맡긴다. 아래 열두 원칙이 그 사상이다.</>}>
              <AgentAccordion exclusive items={PRINCIPLES.map(([t, s], i) => ({ id: `p${i}`, title: t, content: <p className="doc-p">{s}</p> }))} defaultOpenId="p0" />
              <h3 className="doc-h3">세 층 — 섞이지 않는다</h3>
              <div className="doc-tiers">
                <div className="doc-tier doc-tier--v"><b>{n(T.verified)}</b><span>verified · 검증</span><small>실제 호출·다운로드·통계까지. 정식 추천, 조인 참여</small></div>
                <div className="doc-tier doc-tier--c"><b>{n(T.candidate)}</b><span>candidate · 후보</span><small>선정했으나 검증 실패·보류. 조인 불가</small></div>
                <div className="doc-tier doc-tier--l"><b>{n(T.catalog)}</b><span>catalog · 단서</span><small>포털 전체 목록. "직접 확인이 필요한 단서"로만</small></div>
              </div>
              <TrustLegend />
            </Section>

            <Section id="tech" n={2} title="구성 기술"
              lead="수집·검증 → 지식(원본) → 파생물 → 서비스로 흐른다. 원본은 파일 하나뿐이고 나머지는 언제든 다시 만들 수 있다. 상자를 눌러 각 부분을 보세요.">
              <Diagram title="시스템 구성도" width={940} height={580} nodes={arch} links={archLinks} initial="core" />
              <AgentTable caption="기술 구성" columns={[{ key: 'layer', label: '층' }, { key: 'tech', label: '기술' }, { key: 'where', label: '위치' }]}
                rows={[
                  { key: 1, layer: '지식 원본', tech: 'YAML · pydantic 스키마 · JSON Schema', where: 'knowledge/ · pds/schema' },
                  { key: 2, layer: '수집·검증', tech: 'httpx · Playwright(활용신청·다운로드) · pandas 셀 통계', where: 'pds/probe · pds/ingest' },
                  { key: 3, layer: '관계', tech: '선언 Edge · 변환 규칙 함수 · 매핑표 · 실측 매칭률', where: 'knowledge/edges.yaml · pds/rules · pds/mapping' },
                  { key: 4, layer: '검색·전략', tech: 'BM25(한글 2-gram) · networkx 최단 경로 · 지역 판정', where: 'pds/service/index.py · pds/strategy' },
                  { key: 5, layer: '설명', tech: 'Claude Sonnet 5.5 (도구 사용 · 구조화 출력 · 서버 폴백)', where: 'pds/service/llm.py' },
                  { key: 6, layer: '서비스', tech: 'FastAPI · SSE · MCP(mcp 2.x)', where: 'pds/service/app.py · pds/mcp' },
                  { key: 7, layer: '화면', tech: 'React 19 · Vite · BigValue 디자인 시스템(@bv-ds/ui Agent)', where: 'frontend/ → web/dist' },
                  { key: 8, layer: '파생 저장', tech: 'PostgreSQL 17 (pds_* 테이블) · parquet 백업', where: 'sql/ · pds/db.py · pds/setup.py' },
                ]} />
              <h3 className="doc-h3">써 보기</h3>
              <AgentTabs label="예시 코드" items={[
                { id: 'plan', label: '전략 API', content: <Code lang="bash">{`curl -s -X POST http://localhost:8765/api/plan \\
  -H 'Content-Type: application/json' \\
  -d '{"goal": "성수동 상권 변화를 월 단위로 추적하고 싶어", "use_llm": false}'
# → datasets(역할·근거) · joins(선언 Edge·실측률) · pipeline · not_recommended(지역 불일치 등) · code`}</Code> },
                { id: 'setup', label: '설치', content: <Code lang="bash">{`pip install -e .
cp .env.example .env          # CLAUDE_API_KEY만 있어도 채팅이 된다
python -m pds setup           # 지식 검증 → 목록 스냅샷 → 설명서 → (DB) → 색인
python -m pds serve --port 8765`}</Code> },
                { id: 'mcp', label: 'MCP', content: <Code lang="json">{`{ "mcpServers": { "datagokr": {
    "command": ".../.venv/Scripts/python.exe",
    "args": ["-m", "pds", "mcp"], "cwd": ".../datagokr-mcp" } } }`}</Code> },
                { id: 'gen', label: '생성 코드', content: <Code lang="python">{`# 검증 때 성공한 호출을 그대로 — 지역은 목표에서(성수동 → 성동구 3030000)
df_15154916 = fetch('https://apis.data.go.kr/1741000/general_restaurants/info',
                    {'returnType': 'json', 'cond[OPN_ATMY_GRP_CD::EQ]': '3030000'},
                    page='pageNo', size='numOfRows', page_size=100)
df_15154916['pnu'] = df_15154916['MNG_NO'].astype(str)   # e-0384 → 필지(PNU)
by_pnu = pd.concat([...])                                  # 필지별로 쌓아 비교`}</Code> },
              ]} />
            </Section>

            <Section id="standard" n={3} title="표준과 데이터별 구성"
              lead="모든 지식은 몇 가지 엔티티로 표현된다. 데이터(Dataset)는 사실 진술(Claim)의 묶음이고, 각 진술은 근거(Evidence)를 가진다. 상자를 눌러 정의를 보세요.">
              <Diagram title="지식 모델" width={980} height={500} nodes={ent} links={entLinks} initial="ds" />
              <h3 className="doc-h3">근거의 종류 — 사실로 인정되는 것</h3>
              <AgentTable caption="근거(evidence) 종류" columns={[{ key: 't', label: '종류' }, { key: 'm', label: '뜻' }, { key: 'g', label: '사실 인정' }, { key: 'c', label: '쓰인 수', numeric: true }]}
                rows={[['measured', '실측 — 직접 호출·다운로드·통계', true], ['law', '법령 원문', true], ['admin_review', '사람의 검토 결정(기록)', true],
                  ['portal_meta', '포털 등록값', false], ['inferred', 'AI 초안', false], ['user', '사용자 피드백', false]].map(([t, m, g]) => ({
                  key: String(t), t: <code className="pds-code">{String(t)}</code>, m: String(m),
                  g: g ? <AgentChip variant="live">사실</AgentChip> : <AgentChip variant="neutral">보조</AgentChip>, c: n(d.claims.by_evidence[String(t)]) }))} />
              <ProportionBar unit="개" data={entries(d.claims.grounded).map(([k, v]) => ({ label: k, value: v }))} />
              <h3 className="doc-h3">사실 진술의 종류</h3>
              <Bars data={entries(d.claims.by_kind).map(([k, v]) => [({ access: '접근', cadence: '갱신', key: '조인 키', coverage: '범위', legal_basis: '법적 근거', admin_note: '검토 메모', pitfall: '주의', domain_law: '관련 법' } as Record<string, string>)[k] ?? k, v] as [string, number])} unit="개" />
              <h3 className="doc-h3">실제 파일</h3>
              <AgentTabs label="지식 파일 예시" items={[
                { id: 'ds', label: 'Dataset', content: <Code lang="yaml">{d.examples.dataset}</Code> },
                { id: 'edge', label: 'Edge', content: <Code lang="yaml">{d.examples.edge}</Code> },
                { id: 'rule', label: 'Rule', content: <Code lang="yaml">{d.examples.rule}</Code> },
                { id: 'ctx', label: 'Context', content: <Code lang="yaml">{d.examples.context}</Code> },
              ]} />
            </Section>

            <Section id="relations" n={4} title="관계의 정의"
              lead="데이터 사이의 관계는 Edge로 미리 선언한다. AI는 이 중에서 고르기만 하고, 경로가 없으면 없다고 말한다.">
              <div className="doc-cards3">
                <div className="doc-card"><AgentChip variant="primary">joinable</AgentChip><b>{n(d.edges.by_rel.joinable)}</b><p>같은 키(또는 변환·매핑을 거친 키)로 행을 이을 수 있다.</p></div>
                <div className="doc-card"><AgentChip variant="secondary">lookup</AgentChip><b>{n(d.edges.by_rel.lookup)}</b><p>한쪽을 부르려면 다른 쪽의 값(코드)이 먼저 필요하다 — 호출 체인.</p></div>
                <div className="doc-card"><AgentChip variant="neutral">related_to</AgentChip><b>{n(d.edges.by_rel.related_to)}</b><p>같은 맥락의 참고 관계. 행을 잇지는 않는다(측정하지 않음).</p></div>
              </div>
              <h3 className="doc-h3">허브 — 많은 데이터가 모이는 키</h3>
              <p className="doc-p">모든 데이터를 서로 잇면 n² 조합이 된다. 그래서 필지(PNU)·법정동 같은 공통 키를 <b>허브</b>로 두고 데이터마다 허브로의 길 하나만 선언한다(별 모양). 두 데이터는 허브를 거쳐 이어진다.</p>
              <div className="doc-hubs">
                {d.edges.hubs.map((h) => (
                  <div key={h.id} className="doc-hub"><b>{h.name}</b><span>{n(h.edges)}개 조인</span><small>{h.id}</small></div>
                ))}
              </div>
              <h3 className="doc-h3">변환 규칙</h3>
              <div className="doc-grid2">
                <AgentTable caption="변환 규칙" columns={[{ key: 'id', label: '규칙' }, { key: 'name', label: '내용' }, { key: 'c', label: '쓰는 조인', numeric: true }]}
                  rows={Object.entries(d.rules).map(([k, v]) => ({ key: k, id: <code className="pds-code">{k}</code>, name: v, c: n(d.edges.by_rule[k]) }))} />
                <BarChart type="horizontal" responsive height={260} categories={entries(d.edges.by_rule).map(([k]) => k)}
                  series={[{ label: '조인 수', data: entries(d.edges.by_rule).map(([, v]) => v) }]} legend={false} />
              </div>
              <h3 className="doc-h3">조인 키 — 누르면 9장 표가 그 키로 걸러집니다</h3>
              <Bars data={d.keys.filter((k) => k.datasets > 0).slice(0, 16).map((k) => [k.id, k.datasets] as [string, number])} unit="개 데이터" onPick={pickKey} picked={keyFilter} />
              <h3 className="doc-h3">매핑표 — 코드 체계가 다른 키 잇기</h3>
              <AgentTable caption="매핑표" columns={[{ key: 'id', label: '매핑' }, { key: 'r', label: '일치율' }]}
                rows={d.mappings.map((m) => ({ key: m.id, id: <code className="pds-code">{m.id}</code>, r: m.rate == null ? '—' : `${(m.rate * 100).toFixed(1)}%` }))} />
              <h3 className="doc-h3">맥락 — 같은 국민 질문</h3>
              <div className="doc-ctx">
                {d.contexts.slice().sort((a, b) => b.members - a.members).map((c) => (
                  <div key={c.id} className="doc-ctx-item" title={c.question ?? ''}>
                    <b>{c.name}</b><span>{c.dimension ?? ''}</span><small>멤버 {c.members}{c.recipe ? ' · 레시피' : ''}</small>
                  </div>
                ))}
              </div>
            </Section>

            <Section id="scope" n={5} title="데이터 대상과 커버리지"
              lead="포털 전체에서 출발해, 점수와 부문 검토로 대상을 고르고, 실제 호출로 검증된 것만 지식이 된다.">
              <div className="doc-funnel">
                {([['포털 전체 목록', T.catalog], ['검토 단위 (1~3차 + 외부)', 331 + (d.waves.wave2?.units ?? 0) + (d.waves.wave3?.units ?? 0) + 521],
                  ['검증 대상', Object.values(d.rounds).reduce((a, r) => a + Object.values(r).reduce((x, y) => x + y, 0), 0)],
                  ['검증 통과 (지식 체계)', T.verified], ['조인으로 연결된 데이터', T.datasets_with_edge]] as [string, number][]).map(([k, v], i, arr) => (
                  <div key={k} className="doc-funnel-row">
                    <span>{k}</span>
                    <div className="doc-bar doc-bar--wide"><i style={{ width: `${Math.max(3, (Math.log10(v + 1) / Math.log10(arr[0][1] + 1)) * 100)}%` }} /></div>
                    <b>{n(v)}</b>
                  </div>
                ))}
                <p className="doc-small">막대는 로그 눈금입니다.</p>
              </div>
              <div className="doc-grid2">
                <div>
                  <h3 className="doc-h3">부문별 검증 데이터</h3>
                  <BarChart type="horizontal" responsive height={Math.max(320, d.sectors.length * 44)} categories={d.sectors.map((s) => s.sector)}
                    series={[{ label: '검증', data: d.sectors.map((s) => s.verified) }, { label: '조인 있음', data: d.sectors.map((s) => s.with_edge) }]} />
                </div>
                <div>
                  <h3 className="doc-h3">접근 경로</h3>
                  <PieChart type="donut" responsive height={260} data={entries(d.channels).map(([k, v]) => ({ label: k, value: v }))} />
                  <p className="doc-small">외부 사이트는 기관 사이트에서 키를 받아야 하는 데이터입니다(브이월드·서울·법제처·나이스). 나머지 외부 사이트 359건은 키가 없어 대기 중입니다(추가외부키.md).</p>
                </div>
              </div>
            </Section>

            <Section id="sites" n={6} title="가입이 필요한 사이트와 사이트별 커버리지"
              lead={<>data.go.kr 목록에 있어도 데이터가 기관 사이트에 있는 경우(링크형)가 많다. 포털 데이터는 포털 계정 하나와 데이터별 활용신청(대부분 자동승인)이면 되지만, 링크형은 <b>그 사이트에 따로 가입하고 키를 받아야</b> 한다. 아래는 포털 목록 전체의 링크형 데이터를 제공처 주소로 묶은 결과다.</>}>
              {d.sites ? (<>
                <ProportionBar unit="건" data={[
                  { label: '포털에서 바로 (계정 1개 + 활용신청)', value: d.sites.summary.portal_direct },
                  { label: `외부 사이트 API (${n(d.sites.summary.api_sites)}곳)`, value: d.sites.sites.reduce((a, r) => a + r.api, 0) },
                  { label: '외부 사이트 파일', value: d.sites.sites.reduce((a, r) => a + r.file, 0) },
                ]} />
                <div className="doc-cards4">
                  {(['보유·검증', '보유', '미보유', '키 불필요'] as const).map((k) => (
                    <div key={k} className={`doc-card doc-card--${k === '보유·검증' ? 'ok' : k === '미보유' ? 'need' : 'plain'}`}>
                      <AgentChip variant={k === '보유·검증' ? 'live' : k === '보유' ? 'primary' : k === '미보유' ? 'hot' : 'neutral'}>{k}</AgentChip>
                      <b>{n(d.sites?.summary.by_key[k]?.sites)}곳</b>
                      <p>{n(d.sites?.summary.by_key[k]?.datasets)}건 · {({ '보유·검증': '키를 받아 실제로 불러 확인한 사이트', '보유': '키는 있으나 아직 이 시스템 대상 데이터가 없는 사이트', '미보유': 'API 키가 필요하지만 아직 받지 않은 사이트 (추가외부키.md)', '키 불필요': '파일 내려받기만 하는 사이트(대부분 기관 홈페이지) — 가입 없이 또는 계정만' } as Record<string, string>)[k]}</p>
                    </div>
                  ))}
                </div>
                <p className="doc-p">이 시스템이 키를 받아 확인한 곳은 <b>data.go.kr</b>(포털)과 <b>브이월드 · 서울 열린데이터광장 · 법제처 · 나이스</b>다. 나머지 API 사이트는 가입·신청 부담 때문에 아직 받지 않았고, 대상 데이터와 사이트별 발급 절차는 저장소의 <code className="pds-code">추가외부키.md</code>에 정리돼 있다.</p>
                <SiteTable sites={d.sites.sites} />
              </>) : <p className="doc-p">사이트별 집계를 아직 만들지 않았습니다 (python -m pds.expand.site_coverage).</p>}
            </Section>

            <Section id="progress" n={7} title="지금까지 진행된 사항">
              <ol className="doc-timeline">
                {TIMELINE.map((t, i) => (<li key={i}><time>{t.d}</time><b>{t.t}</b><p>{t.s}</p></li>))}
              </ol>
              <h3 className="doc-h3">검증 라운드</h3>
              <AgentTable caption="라운드별 검증" columns={[{ key: 'r', label: '라운드' }, { key: 'what', label: '대상' }, { key: 'v', label: '통과', numeric: true }, { key: 'f', label: '실패', numeric: true }, { key: 'p', label: '대기', numeric: true }]}
                rows={Object.entries(d.rounds).map(([r, c]) => ({
                  key: r, r, what: ({ '1': '1차 대표 데이터(상위)', '2': '1차 대표 데이터(나머지)', '3': '1차 보강', '4': '2차 확대 — 조인 키 기준', '5': '3차 확대 — 점수 상위', external: '외부 사이트' } as Record<string, string>)[r] ?? r,
                  v: n(c.verified), f: n(c.failed), p: n(c.pending) }))} />
              <h3 className="doc-h3">확대 차수별 부문 검토</h3>
              {Object.entries(d.waves).map(([w, c]) => (
                <div key={w} className="doc-wave"><b>{w === 'wave2' ? '2차' : '3차'} · {n(c.units)}단위</b>
                  <ProportionBar unit="" data={[['유지', c.keep], ['이동', c.move], ['대체', c.absorb], ['미룸', c.defer]].filter(([, v]) => v).map(([k, v]) => ({ label: String(k), value: Number(v) }))} />
                </div>
              ))}
            </Section>

            <Section id="verified" n={8} title="확인된 관계와 데이터"
              lead="선언된 조인은 실제 데이터로 매칭률을 잰다. 표본에서 판단할 수 없는 조인은 '실측 보류'로 남긴다.">
              <div className="doc-grid2">
                <div>
                  <h3 className="doc-h3">조인 실측 매칭률</h3>
                  <BarChart responsive height={240} categories={['100%', '95~99%', '80~95%', '50~80%', '50% 이하', '미측정'].filter((k) => k in d.edges.rate)}
                    series={[{ label: '조인 수', data: ['100%', '95~99%', '80~95%', '50~80%', '50% 이하', '미측정'].filter((k) => k in d.edges.rate).map((k) => d.edges.rate[k]) }]} legend={false} />
                </div>
                <div>
                  <h3 className="doc-h3">최신성 — 가장 최근 행이 며칠 전인가</h3>
                  <BarChart responsive height={240} categories={['하루 이내', '1주 이내', '한 달 이내', '1년 이내', '1년 넘음', '관찰 전'].filter((k) => k in d.coverage.fresh)}
                    series={[{ label: '데이터 수', data: ['하루 이내', '1주 이내', '한 달 이내', '1년 이내', '1년 넘음', '관찰 전'].filter((k) => k in d.coverage.fresh).map((k) => d.coverage.fresh[k]) }]} legend={false} />
                </div>
              </div>
              <ul className="doc-facts">
                <li>조인 {n(T.edges)}개 중 <b>{n(T.measured)}개</b>를 실제 데이터로 쟀고, 매칭률 100%가 {n(d.edges.rate['100%'])}개입니다.</li>
                <li>검증된 데이터 {n(T.verified)}건 중 <b>{n(T.datasets_with_edge)}건</b>이 하나 이상의 조인으로 다른 데이터와 이어집니다.</li>
                <li>사실 진술 {n(T.claims)}개 중 {n(d.claims.grounded['근거 있음'])}개가 실측·법령·검토 근거를 가집니다. 나머지는 화면에서 (미확인)으로 표시됩니다.</li>
                <li>코드 체계가 다른 키는 매핑표 {n(T.mappings)}종으로 잇고, {n(d.edges.via_mapping)}개 조인이 매핑을 거칩니다.</li>
              </ul>
              <h3 className="doc-h3">아직 없는 것 — 공백</h3>
              <AgentTable caption="공백" columns={[{ key: 'n', label: '영역' }, { key: 's', label: '상태' }, { key: 'r', label: '이유' }]}
                rows={[...d.gaps.map((g) => ({ key: g.name, n: g.name, s: g.status === 'resolved' ? '해결' : '열림', r: (g.reason ?? '').slice(0, 120) })),
                  { key: 'childcare', n: '전국 어린이집·유치원 원장', s: '외부 키', r: '보육통합정보시스템·유치원알리미 키가 필요 (추가외부키.md)' },
                  { key: 'flood', n: '산사태위험지구·침수흔적도', s: '외부 키', r: '외부 지도 서비스 키가 필요' }]} />
            </Section>

            <Section id="coverage" n={9} title="데이터별 범위와 커버리지 수준"
              lead={<>데이터마다 <b>범위</b>(전국·시도·시군구), <b>단위</b>(개별 원장·필지·집계), <b>규모</b>(전체 건수), <b>최신성</b>, <b>조인 키</b>를 실측으로 적었습니다. 커버리지 수준은 상(전국·개별 원장·1천 건 이상) · 중(전국 집계 또는 지역 단위 원장) · 하(그 밖) 입니다.</>}>
              <div className="doc-grid3">
                <div><h3 className="doc-h3">수준</h3><ProportionBar unit="건" data={[['상', levels['상']], ['중', levels['중']], ['하', levels['하']]].map(([k, v]) => ({ label: String(k), value: Number(v) }))} /></div>
                <div><h3 className="doc-h3">범위</h3><Bars data={entries(d.coverage.spatial)} /></div>
                <div><h3 className="doc-h3">단위</h3><Bars data={entries(d.coverage.unit)} /></div>
              </div>
              <h3 className="doc-h3">규모 — 전체 건수</h3>
              <Bars data={entries(d.coverage.rows, ['100만 이상', '100만 미만', '10만 미만', '1만 미만', '1천 미만', '미상'])} />
              <h3 className="doc-h3">전체 목록</h3>
              <DataTable rows={d.datasets} keyFilter={keyFilter} onKeyFilter={setKeyFilter} open={setDsId} />
              <p className="doc-small">건수 표기 예: {fmtCount(2300238)} = 2,300,238건.</p>
            </Section>
            <div className="doc-end"><AgentButton variant="secondary" onClick={() => go('philosophy')}>맨 위로</AgentButton></div>
          </>)}
        </main>
      </div>
      <DatasetDrawer id={dsId} onClose={() => setDsId(null)} open={setDsId} />
    </div>
  )
}
