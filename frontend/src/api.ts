// 서비스 API (pds/service/app.py) 응답 모양 — 화면이 쓰는 필드만.

export interface Access {
  channel: 'portal' | 'external'
  issuer?: string
  approval?: string
  daily_limit?: number | null
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
}

export interface PlanJoin {
  edge: string
  rel: string
  left: string
  right: string
  hub?: string | null
  on: { left?: string[]; right?: string[]; transform?: string | null }
  via_mapping?: string | null
  relationship?: string
  match_rate?: number | null
}

export interface Plan {
  goal: string
  context?: string | null
  summary: string
  datasets: PlanDataset[]
  joins: PlanJoin[]
  pipeline: { do: string; dataset?: string; edge?: string; note?: string }[]
  schedule?: { reason: string } | null
  candidates: { id: string; title: string; status?: string; blocked_by?: string }[]
  unverified_leads: { title: string; agency: string; portal_url: string; similarity: number; why_maybe: string }[]
  gaps: string[]
  confidence: string | number
  knowledge_version: string
  code: string
}

export interface ChatTrace {
  tool: string
  input: Record<string, unknown>
  chars?: number
}

export interface ChatOut {
  reply: string
  plans: Plan[]
  trace: ChatTrace[]
  elapsed_s: number
}

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

export const api = {
  stats: () => fetch('/api/stats').then((r) => json<Stats>(r)),
  chat: (messages: { role: string; content: string }[]) =>
    fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ messages }),
    }).then((r) => json<ChatOut>(r)),
  dataset: (id: string) => fetch(`/api/datasets/${id}`).then((r) => json<DatasetOut>(r)),
}
