// 서비스 API (pds/service/app.py) 응답 모양 — 화면이 쓰는 필드만.

export interface Access {
  channel: 'portal' | 'external'
  issuer?: string | null
  approval?: string | null
  daily_limit?: number | null
}

export type Tone = 'ok' | 'inf' | 'key' | 'warn' | 'neutral'

export interface Badge {
  label: string
  tone: Tone
  kind: string
}

export interface ClaimView {
  id: string
  kind: string
  kind_label: string
  value: string
  evidence: string[]
  date?: string | null
}

export interface PlanDataset {
  id: string
  tier: string
  role: string
  title: string
  agency: string
  why: string
  evidence: string[]
  caveats: string[]
  access: Access
  portal_url?: string
  rows?: number | null
  badges: Badge[]
  claims: ClaimView[]
}

export interface PlanJoin {
  edge: string
  rel: string
  left: string
  right: string
  hub?: string | null
  on: { left?: string[] | null; right?: string[] | null; transform?: string | null }
  via_mapping?: string | null
  relationship?: string | null
  match_rate?: number | null
}

export interface Excluded {
  id: string
  title?: string | null
  reason: string
  kind?: string
}

export interface Lead {
  id: string
  title: string
  agency: string
  portal_url: string
  similarity: number
  why_maybe: string
  kind?: string | null
  head?: string
  rep?: boolean
}

export interface HeadLink { head: string; id: string; kind: 'edge' | 'key' | 'aligned'; label: string; estimated?: boolean }
export interface HeadPick {
  id: string
  tier: 'verified' | 'candidate' | 'catalog'
  title: string
  agency?: string | null
  score: number
  why: string
  unit?: string | null
  unit_estimated?: boolean
  excluded_by?: string | null
  links: HeadLink[]
}
export interface PlanHead { name: string; need: string; must: boolean; rep: string | null; queries: string[]; picks: HeadPick[] }
export interface PlanHeadLink {
  heads: [string, string]; left: string; right: string; kind: 'edge' | 'key' | 'aligned' | 'none'; label: string; estimated?: boolean
  alt?: { left: string; left_title: string; right: string; right_title: string; kind: string; label: string }
}

export interface Plan {
  version?: number
  heads?: PlanHead[] | null
  head_links?: PlanHeadLink[] | null
  goal: string
  context?: string | null
  summary: string
  datasets: PlanDataset[]
  joins: PlanJoin[]
  aligned?: { kind: 'aligned'; left: string; right: string; align: { space?: string; time?: string; category?: string; rules: string[]; label: string }; note: string }[]
  pipeline: { step: number; do: string; dataset?: string; edge?: string; note?: string }[]
  schedule?: { reason: string } | null
  candidates: { id: string; title: string; status?: string | null; blocked_by?: string | null }[]
  unverified_leads: Lead[]
  not_recommended: Excluded[]
  hubs: Record<string, string>
  gaps: string[]
  confidence: number
  knowledge_version: string
  code: string
}

export interface Step {
  id: string
  label: string
  status: 'running' | 'done' | 'failed'
  detail: string
  t: number
}

export interface Usage {
  model: string
  calls: number
  input: number
  output: number
}

export interface ChatDone {
  turn_id?: string
  reply: string
  plans: Plan[]
  trace: { tool: string; input: Record<string, unknown> }[]
  usage?: Usage
  elapsed_s: number
}

export type StreamEvent =
  | ({ type: 'step' } & Step)
  | { type: 'plan'; plan: Plan }
  | ({ type: 'done' } & ChatDone)
  | { type: 'error'; detail: string }

export interface Stats {
  datasets: Record<string, number>
  catalog: number
  measured_edges: number
  code_lists: number
}

export interface DatasetOut {
  dataset: { id: string; title: string }
  dossier_md?: string | null
}

async function json<T>(r: Response): Promise<T> {
  const j = await r.json().catch(() => ({}))
  if (!r.ok) throw new Error((j as { detail?: string }).detail || `HTTP ${r.status}`)
  return j as T
}

/** /api/chat/stream — SSE(POST)라 EventSource 대신 fetch 스트림을 직접 읽는다. */
/** 브라우저 세션 id — 사용 기록(개선용)에서 같은 사람의 대화를 묶는다. 저장이 막히면 탭마다 새로 */
export function sessionId(): string {
  try {
    let v = localStorage.getItem('pds-session')
    if (!v) {
      v = crypto.randomUUID()
      localStorage.setItem('pds-session', v)
    }
    return v
  } catch {
    return 'tab-' + Math.random().toString(36).slice(2)
  }
}

export function sendFeedback(turn_id: string, rating: 'up' | 'down', comment?: string) {
  return fetch('/api/feedback', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ turn_id, rating, comment, session: sessionId() }),
  })
}

async function chatStream(messages: { role: string; content: string }[], on: (e: StreamEvent) => void): Promise<void> {
  const r = await fetch('/api/chat/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ messages, session: sessionId() }),
  })
  if (!r.ok || !r.body) {
    const j = await r.json().catch(() => ({}))
    throw new Error((j as { detail?: string }).detail || `HTTP ${r.status}`)
  }
  const reader = r.body.getReader()
  const dec = new TextDecoder()
  let buf = ''
  for (;;) {
    const { value, done } = await reader.read()
    if (done) break
    buf += dec.decode(value, { stream: true })
    let i: number
    while ((i = buf.indexOf('\n\n')) >= 0) {
      const chunk = buf.slice(0, i)
      buf = buf.slice(i + 2)
      const data = chunk.split('\n').filter((l) => l.startsWith('data: ')).map((l) => l.slice(6)).join('\n')
      if (data) on(JSON.parse(data) as StreamEvent)
    }
  }
}

export const api = {
  stats: () => fetch('/api/stats').then((r) => json<Stats>(r)),
  chatStream,
  dataset: (id: string) => fetch(`/api/datasets/${id}`).then((r) => json<DatasetOut>(r)),
}

// ── Docs (GET /api/docs) — pds/service/docs.py
export interface DocsRow {
  id: string
  title: string
  agency?: string | null
  sector: string
  tier: string
  channel?: string | null
  kind?: string | null
  rows?: number | null
  spatial?: string | null
  unit?: string | null
  lag?: number | null
  keys: string[]
  fields: number
  edges: number
  rate?: number | null
  claims: number
}

export interface DocsData {
  knowledge_version: string
  totals: Record<string, number>
  rounds: Record<string, Record<string, number>>
  waves: Record<string, Record<string, number>>
  sectors: { sector: string; verified: number; candidate: number; with_edge: number }[]
  channels: Record<string, number>
  edges: { by_rel: Record<string, number>; by_rule: Record<string, number>; rate: Record<string, number>; hubs: { id: string; name: string; edges: number }[]; via_mapping: number }
  rules: Record<string, string>
  grain?: { space: Record<string, number>; time: Record<string, number>; category: Record<string, number>; with_space: number; no_edge_with_space: number }  // 서버가 옛 판이면 없다
  agencies?: Agencies  // 서버가 옛 판이면 없다
  claims: { by_kind: Record<string, number>; by_evidence: Record<string, number>; grounded: Record<string, number> }
  keys: { id: string; name: string; type: string; datasets: number }[]
  contexts: { id: string; name: string; dimension?: string; question?: string; members: number; recipe: boolean }[]
  mappings: { id: string; rate?: number | null }[]
  gaps: { name: string; status?: string; reason?: string }[]
  coverage: Record<'spatial' | 'unit' | 'fresh' | 'rows', Record<string, number>>
  datasets: DocsRow[]
  examples: Record<'dataset' | 'edge' | 'rule' | 'context', string>
  sites?: SiteCoverage | null
}

export const docsApi = () => fetch('/api/docs').then((r) => json<DocsData>(r))

export interface SiteRow {
  host: string
  name: string
  api: number
  file: number
  total: number
  targets: number
  verified: number
  key: '보유·검증' | '보유' | '미보유' | '키 불필요' | '가입 불필요(견본)' | '승인·신청 대기'
  env: string
  how: string
}

export interface AgencyRow {
  id: string; name: string; type: string; tier: string; catalog?: number; verified?: number; core?: number
  edges_within?: number; edges_across?: number; portal?: string | null; note?: string | null
  systems: { name: string; n: number; core: number }[]; keys: string[]; relations: number; core_missing: number; gaps: string[]
}

export interface Agencies {
  total: number; tiers: Record<string, number>; types: Record<string, number>; analyzed: number
  systems: number; relations: number; core_missing: number; detail: AgencyRow[]
}

export interface SiteCoverage {
  summary: { catalog: number; portal_direct: number; link_total: number; sites: number; api_sites: number; by_key: Record<string, { sites: number; datasets: number }> }
  sites: SiteRow[]
}

// ── Wiki (/api/wiki/*) — pds/service/wiki.py
export interface WikiRow {
  id: string
  title: string
  agency: string
  sector: string
  tier: string
  kind: string
  grade: string
  summary: string
  edges: number
  measured: number
  keys: string[]
}

export interface WikiFacets {
  counts: { datasets: number; keys: number; codes: number }
  sectors: [string, number][]
  agencies: [string, number][]
  grades: [string, number][]
  keys: [string, number][]
  kinds: Record<string, string>
}

export interface WikiRelation {
  edge: string
  rel: 'joinable' | 'lookup' | 'related_to'
  dir: 'in' | 'out'
  other: string
  other_title?: string | null
  other_known: boolean
  other_sector?: string | null
  other_agency?: string | null
  left?: string[] | null
  right?: string[] | null
  transform?: string | null
  via_mapping?: string | null
  relationship?: string | null
  confidence?: number | null
  source?: string | null
  note?: string | null
  match_rate?: number | null
  measured_at?: string | null
}

export interface WikiField {
  name: string
  title?: string | null
  type?: string
  semantic_type?: string | null
  code_list?: string | null
  null_rate?: number | null
  sample_values?: unknown[]
  description?: string | null
}

export interface WikiEvidence { type: string; source: string; by?: string | null; at?: string | null; observed_at?: string | null; detail?: string | null }
export interface WikiClaim { id: string; kind: string; value: string; evidence: WikiEvidence[]; qualifiers?: Record<string, unknown>; rank?: string }

export interface WikiDataset {
  id: string
  tier: string
  title: string
  family?: string | null
  sector: string
  agency: { id?: string; name: string }
  kind: string
  channel: string
  portal_url?: string | null
  synonyms?: string[]
  summary_user?: string | null
  description_portal?: string | null
  accrual_periodicity?: string | null
  limits?: string | null
  team?: { dept?: string | null } | null
  schema?: { fields?: WikiField[]; foreign_keys?: { fields: string[]; reference: { key?: string } }[] }
  facets?: Record<string, string[]>
  coverage?: Record<string, unknown> | null
  grain?: Record<string, unknown> | null
  classification?: { subsector_name?: string | null; why?: string | null } | null
  claims?: WikiClaim[]
  edges_hint?: string[]
  status?: string
  distributions?: { title?: string; url?: string; format?: string }[]
  services?: { name?: string; endpoint?: string; approval?: string }[]
}

export interface WikiPageOut {
  dataset: WikiDataset
  relations: WikiRelation[]
  relation_totals: Record<string, number>
  keys: { id: string; name: string; datasets: number }[]
  family: { id: string; title: string; agency: string }[]
  dossier_md?: string | null
  file: string
}

export interface WikiProposal {
  id: number
  dataset_id: string
  kind: string
  target?: string | null
  current_value?: string | null
  proposed_value: string
  reason?: string | null
  author?: string | null
  status: 'pending' | 'approved' | 'rejected'
  reviewer?: string | null
  review_note?: string | null
  reviewed_at?: string | null
  applied?: { file?: string; field?: string; claim?: string } | null
  created_at: string
}

export interface WikiKeyRow {
  id: string
  name: string
  type?: string | null
  scope?: string | null
  issuer?: string | null
  agency?: string | null
  datasets: number
  masters: number
  mappings: number
  codes: number
}

export interface WikiDsRef { id: string; title?: string | null; known: boolean; agency?: string | null; fields?: string[] }

export interface WikiKeyPage {
  key: {
    id: string; name: string; type?: string; scope?: string; format?: string | null; pattern?: string | null; issuer?: string | null
    agency?: string | null; notes?: string | null; shape_names?: string[]
  }
  total: number
  page: number
  size: number
  rows: (WikiRow & { fields: string[] })[]
  masters: WikiDsRef[]
  composed_of: { key: string; name?: string | null }[]
  related: { key: string; relation: string; note?: string | null; name?: string | null }[]
  mappings: { id: string; left: { key: string; system: string }; right: { key: string; system: string }; method?: string; rows?: number; match_rate?: number; notes?: string | null }[]
  codes: { id: string; name: string; rows: number }[]
  file: string
}

export interface WikiCodeRow { id: string; name: string; key?: string | null; completeness: string; rows: number; aliases: string[]; datasets: number }

export interface WikiCodePage {
  code: {
    id: string; name: string; key?: string | null; key_name?: string | null; completeness: string; completeness_label: string; rows: number
    aliases?: string[]; notes?: string | null; evidence: WikiEvidence[]; file?: string | null
  }
  used_by: WikiDsRef[]
  values: Record<string, unknown>[]
  values_shown: number
  q?: string | null
  file: string
}

export interface WikiSearchParams { q?: string; sector?: string; agency?: string; grade?: string; key?: string; linked?: boolean; sort?: string; page?: number }

function wikiToken(): string {
  try { return localStorage.getItem('pds-wiki-token') || '' } catch { return '' }
}

const qs = (o: Record<string, unknown>) =>
  new URLSearchParams(Object.entries(o).filter(([, v]) => v !== undefined && v !== '' && v !== false).map(([k, v]) => [k, String(v)])).toString()

export const wikiApi = {
  facets: () => fetch('/api/wiki/facets').then((r) => json<WikiFacets>(r)),
  search: (p: WikiSearchParams) => fetch(`/api/wiki/search?${qs({ ...p })}`).then((r) => json<{ total: number; page: number; size: number; rows: WikiRow[] }>(r)),
  page: (id: string) => fetch(`/api/wiki/datasets/${encodeURIComponent(id)}`).then((r) => json<WikiPageOut>(r)),
  keys: (q = '') => fetch(`/api/wiki/keys?${qs({ q })}`).then((r) => json<WikiKeyRow[]>(r)),
  key: (key: string, page = 1) => fetch(`/api/wiki/keys/${encodeURIComponent(key)}?page=${page}`).then((r) => json<WikiKeyPage>(r)),
  codes: (q = '') => fetch(`/api/wiki/codes?${qs({ q })}`).then((r) => json<WikiCodeRow[]>(r)),
  code: (id: string, q = '') => fetch(`/api/wiki/codes/${encodeURIComponent(id)}?${qs({ q })}`).then((r) => json<WikiCodePage>(r)),
  proposals: (p: { dataset?: string; status?: string }) => fetch(`/api/wiki/proposals?${qs(p)}`)
    .then((r) => json<{ rows: WikiProposal[]; counts: Record<string, number> }>(r)),
  propose: (body: { dataset_id: string; kind: string; proposed_value: string; target?: string; reason?: string; author?: string }) =>
    fetch('/api/wiki/proposals', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }).then((r) => json<WikiProposal>(r)),
  me: (token = wikiToken()) => fetch('/api/wiki/me', { headers: { 'x-wiki-token': token } }).then((r) => json<{ reviewer: string | null }>(r)),
  review: (id: number, decision: 'approve' | 'reject', note?: string) =>
    fetch(`/api/wiki/proposals/${id}/review`, { method: 'POST', headers: { 'Content-Type': 'application/json', 'x-wiki-token': wikiToken() },
      body: JSON.stringify({ decision, note }) }).then((r) => json<WikiProposal>(r)),
  setToken: (t: string) => { try { if (t) localStorage.setItem('pds-wiki-token', t); else localStorage.removeItem('pds-wiki-token') } catch { /* 저장이 막힌 브라우저 */ } },
}
