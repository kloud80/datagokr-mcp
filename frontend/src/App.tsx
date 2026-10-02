import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  AgentAIChatWorkspace,
  AgentButton,
  type AgentAIChatActivity,
  type AgentAIChatExecutionStatus,
  type AgentAIChatMessage,
  type AgentAIChatSource,
} from '@bv-ds/ui'
import { api, type ChatTrace, type Plan, type Stats } from './api'
import { Markdown } from './md'
import { PlanPanel } from './PlanPanel'
import { DatasetDrawer } from './DatasetDrawer'

const EXAMPLES = [
  '성수동 상권 변화를 월 단위로 추적하고 싶어',
  '이 아파트 실거래가와 공시지가를 비교하고 싶어',
  '가맹본부가 믿을 만한지 확인하려면?',
  '지금 가까운 응급실과 병상 현황',
  '우리 아이 어린이집·유치원 고르기',
  '나라장터 입찰공고부터 계약까지 따라가기',
]

const TOOL_LABEL: Record<string, string> = {
  plan_strategy: '전략 계산',
  search_datasets: '데이터 검색',
  get_dataset: '데이터 상세 조회',
  find_code_list: '코드표 찾기',
  lookup_code: '코드값 조회',
}

const RUNNING: AgentAIChatActivity[] = [
  { id: 'r1', label: '목표 해석', status: 'completed' },
  { id: 'r2', label: '검증 데이터·조인 경로 계산', status: 'running', description: '지식 체계(실측 Edge)만 사용' },
  { id: 'r3', label: '답변 작성', status: 'pending' },
]

type Turn = { role: 'user' | 'assistant'; content: string; meta?: string }

function traceActivities(trace: ChatTrace[]): AgentAIChatActivity[] {
  return trace.map((t, i) => {
    const arg = Object.values(t.input ?? {}).find((v) => typeof v === 'string') as string | undefined
    return { id: `t${i}`, label: TOOL_LABEL[t.tool] ?? t.tool, status: 'completed', description: arg }
  })
}

export function App() {
  const [turns, setTurns] = useState<Turn[]>([])
  const [draft, setDraft] = useState('')
  const [status, setStatus] = useState<AgentAIChatExecutionStatus>('idle')
  const [error, setError] = useState<string | null>(null)
  const [activities, setActivities] = useState<AgentAIChatActivity[]>([])
  const [plan, setPlan] = useState<Plan | null>(null)
  const [artifactOpen, setArtifactOpen] = useState(true)
  const [stats, setStats] = useState<Stats | null>(null)
  const [dsId, setDsId] = useState<string | null>(null)

  useEffect(() => { api.stats().then(setStats).catch(() => {}) }, [])

  const run = useCallback(async (history: Turn[]) => {
    setStatus('running')
    setError(null)
    setActivities(RUNNING)
    try {
      const out = await api.chat(history.map(({ role, content }) => ({ role, content })))
      const tools = out.trace.map((t) => TOOL_LABEL[t.tool] ?? t.tool).join(', ') || '없음'
      setTurns([...history, { role: 'assistant', content: out.reply, meta: `${out.elapsed_s}s · 도구 ${tools}` }])
      setActivities(traceActivities(out.trace))
      if (out.plans?.length) { setPlan(out.plans[out.plans.length - 1]); setArtifactOpen(true) }
      setStatus('completed')
    } catch (e) {
      setError((e as Error).message)
      setActivities([])
      setStatus('failed')
    }
  }, [])

  const submit = useCallback((value: string) => {
    const text = value.trim()
    if (!text || status === 'running') return
    const history: Turn[] = [...turns, { role: 'user', content: text }]
    setTurns(history)
    setDraft('')
    void run(history)
  }, [turns, status, run])

  const retry = useCallback(() => {
    if (turns.length && turns[turns.length - 1].role === 'user') void run(turns)
  }, [turns, run])

  const messages: AgentAIChatMessage[] = useMemo(() => {
    if (!turns.length) {
      return [{
        id: 'intro',
        role: 'assistant',
        content: (
          <div className="pds-intro">
            <p>하고 싶은 일을 말해 주세요. 검증된 공공데이터와 실측된 조인 경로만으로 데이터 조합·파이프라인·실행 코드를 만들어 드립니다.</p>
            <div className="pds-row">
              {EXAMPLES.map((e) => (
                <AgentButton key={e} variant="secondary" size="sm" onClick={() => submit(e)}>{e}</AgentButton>
              ))}
            </div>
          </div>
        ),
      }]
    }
    const out: AgentAIChatMessage[] = turns.map((t, i) => ({
      id: `m${i}`,
      role: t.role,
      content: t.role === 'assistant' ? <Markdown text={t.content} open={setDsId} /> : t.content,
      meta: t.meta,
    }))
    if (status === 'failed' && error) out.push({ id: 'err', role: 'system', content: `오류: ${error}` })
    return out
  }, [turns, status, error, submit])

  const sources: AgentAIChatSource[] = useMemo(
    () => (plan?.datasets ?? []).map((d) => ({
      title: d.title,
      href: d.portal_url ?? `https://www.data.go.kr/data/${d.id}/openapi.do`,
      description: `${d.agency} · ${d.role}`,
      confidence: d.tier,
    })),
    [plan],
  )

  const description = stats
    ? `검증 ${stats.datasets.verified ?? 0} · 후보 ${stats.datasets.candidate ?? 0} · 포털 목록 ${stats.catalog.toLocaleString()} · 실측 조인 ${stats.measured_edges} · 코드표 ${stats.code_lists}`
    : '공공데이터 지식 체계'

  return (
    <div className="pds-app">
      <AgentAIChatWorkspace
        headingLevel={1}
        title="공공데이터 전략 도우미"
        description={description}
        assistantName="PDS"
        messages={messages}
        status={status}
        statusDescription={status === 'running' ? '데이터를 찾고 조인 경로를 계산하는 중 (20초 안팎)' : undefined}
        activities={activities}
        sources={sources}
        artifact={plan ? { title: '전략', description: plan.goal, content: <PlanPanel plan={plan} open={setDsId} /> } : undefined}
        artifactOpen={artifactOpen}
        onArtifactToggle={() => setArtifactOpen((v) => !v)}
        draft={draft}
        onDraftChange={setDraft}
        onSubmit={(v) => submit(v)}
        onRetry={retry}
        composerPlaceholder="예) 성수동 상권 변화를 월 단위로 추적하고 싶어"
        disclaimer="근거(claim)가 있는 사실만 답합니다. 미검증 데이터는 단서로만 표시됩니다."
      />
      <DatasetDrawer id={dsId} onClose={() => setDsId(null)} open={setDsId} />
    </div>
  )
}
