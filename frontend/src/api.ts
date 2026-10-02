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
}

export interface Plan {
  version?: number
  goal: string
  context?: string | null
  summary: string
  datasets: PlanDataset[]
  joins: PlanJoin[]
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
  key: '보유·검증' | '보유' | '미보유' | '키 불필요'
  env: string
  how: string
}

export interface SiteCoverage {
  summary: { catalog: number; portal_direct: number; link_total: number; sites: number; api_sites: number; by_key: Record<string, { sites: number; datasets: number }> }
  sites: SiteRow[]
}
