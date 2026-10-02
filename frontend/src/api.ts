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
async function chatStream(messages: { role: string; content: string }[], on: (e: StreamEvent) => void): Promise<void> {
  const r = await fetch('/api/chat/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ messages }),
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
