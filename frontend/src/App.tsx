import { useCallback, useEffect, useRef, useState, type KeyboardEvent } from 'react'
import {
  AgentAIMessage,
  AgentAccordion,
  AgentButton,
  AgentChip,
  AgentPlan,
  AgentSegmentedControl,
  AgentTooltip,
  PromptInput,
} from '@bv-ds/ui'
import { api, sendFeedback, type Plan, type Stats, type Step, type Usage } from './api'
import { Markdown } from './md'
import { PlanPanel, type PlanTab } from './PlanPanel'
import { DatasetDrawer } from './DatasetDrawer'
import { Credit } from './Credit'
import type { Trust } from './Trust'

// 2열 — 왼쪽 대화(입력창은 열 바닥에 고정, 대화만 스크롤) · 오른쪽 전략(헤더·탭 고정, 본문만 스크롤).
// 답마다 '전략 vN' 카드가 붙고, 오른쪽은 고른 버전을 보여준다. 좁은 화면은 대화/전략 전환.

const EXAMPLES = [  // 포털 AI 비교 1천 문항에서 고른 질문 (evals/portal_1k/notes.json showcase의 ★)
  '성수동 카페 인허가 추이랑 성수역 승하차 인원 비교',
  '위생등급 지정 업소와 행정처분 이력 겹치는 곳 찾기',
  '낚시어선 사고 기록이랑 당시 기상특보 발효 여부 연결 가능해?',
  '지역별 도시가스 공급량을 기온 데이터랑 합쳐서 수요 예측하고 싶어요',
  '울릉도 배 타려는데 결항 얼마나 자주 돼요?',
  '인천 미추홀구 동별 전세 거래량이랑 청년 인구 비율',
]

interface Turn {
  role: 'user' | 'assistant'
  content: string
  steps?: Step[]
  version?: number
  status?: 'running' | 'done' | 'failed'
  error?: string
  usage?: Usage
  elapsed?: number
  turnId?: string
  rating?: 'up' | 'down'
}

const STEP_STATUS = { running: 'in_progress', done: 'completed', failed: 'completed' } as const

function trustOf(p: Plan | undefined, id: string): Trust | null {
  if (!p) return null
  if (p.datasets.some((d) => d.id === id)) return 'verified'
  if (p.not_recommended.some((x) => x.id === id)) return 'excluded'
  if (p.unverified_leads.some((x) => x.id === id) || p.candidates.some((x) => x.id === id)) return 'lead'
  if ((p.heads ?? []).some((h) => h.picks.some((x) => x.id === id))) return 'lead'
  return null
}

export function App() {
  const [turns, setTurns] = useState<Turn[]>([])
  const [plans, setPlans] = useState<Plan[]>([])
  const [version, setVersion] = useState<number | null>(null)
  const [tab, setTab] = useState<PlanTab>('map')
  const [focusId, setFocusId] = useState<string | null>(null)
  const [dsId, setDsId] = useState<string | null>(null)
  const [draft, setDraft] = useState('')
  const [view, setView] = useState<'chat' | 'plan'>('chat')
  const [stats, setStats] = useState<Stats | null>(null)
  const busy = turns.some((t) => t.status === 'running')
  const scroller = useRef<HTMLDivElement>(null)

  useEffect(() => { api.stats().then(setStats).catch(() => {}) }, [])
  useEffect(() => { scroller.current?.scrollTo({ top: scroller.current.scrollHeight, behavior: 'smooth' }) }, [turns])

  const showPlan = useCallback((v: number, id?: string) => {
    setVersion(v)
    if (id) { setTab('data'); setFocusId(id) }
    setView('plan')
  }, [])

  const send = useCallback(async (text: string) => {
    const q = text.trim()
    if (!q || busy) return
    const history = [...turns.filter((t) => t.status !== 'failed').map(({ role, content }) => ({ role, content })), { role: 'user', content: q }]
    setDraft('')
    setTurns((ts) => [...ts, { role: 'user', content: q }, { role: 'assistant', content: '', steps: [], status: 'running' }])
    window.gtag?.('event', 'chat_question', { turn: Math.floor(history.length / 2) + 1, chars: q.length })  // 질문 내용은 보내지 않는다
    const patch = (f: (t: Turn) => Turn) => setTurns((ts) => ts.map((t, i) => (i === ts.length - 1 ? f(t) : t)))
    let ver: number | undefined
    try {
      await api.chatStream(history, (e) => {
        if (e.type === 'step') {
          patch((t) => {
            const steps = [...(t.steps ?? [])]
            const k = steps.findIndex((s) => s.id === e.id)
            const s: Step = { id: e.id, label: e.label, status: e.status, detail: e.detail, t: e.t }
            if (k >= 0) steps[k] = s
            else steps.push(s)
            return { ...t, steps }
          })
        } else if (e.type === 'plan') {
          setPlans((ps) => {
            if (ver == null) { ver = ps.length + 1; const v = ver; patch((t) => ({ ...t, version: v })); return [...ps, { ...e.plan, version: ver }] }
            return ps.map((p) => (p.version === ver ? { ...e.plan, version: ver } : p)) // 같은 답 안의 갱신(제외 등)은 같은 버전
          })
          setVersion((v) => ver ?? v)
          setTab(e.plan.heads?.length ? 'heads' : 'map')
          setFocusId(null)
        } else if (e.type === 'done') {
          patch((t) => ({ ...t, content: e.reply, status: 'done', usage: e.usage, elapsed: e.elapsed_s, turnId: e.turn_id }))
        } else if (e.type === 'error') {
          patch((t) => ({ ...t, status: 'failed', error: e.detail }))
        }
      })
    } catch (err) {
      patch((t) => ({ ...t, status: 'failed', error: (err as Error).message }))
    }
  }, [turns, busy])

  const retry = () => {
    const k = turns.length - 2
    if (k < 0 || turns[k].role !== 'user') return
    const q = turns[k].content
    setTurns((ts) => ts.slice(0, k))
    setTimeout(() => void send(q), 0)
  }

  // 한글 조합 중 Enter는 전송하지 않는다 (PromptInput은 조합 상태를 보지 않는다)
  const imeGuard = (e: KeyboardEvent) => {
    if (e.key === 'Enter' && (e.nativeEvent.isComposing || e.keyCode === 229)) e.stopPropagation()
  }

  const plan = plans.find((p) => p.version === version) ?? null
  const statsText = stats
    ? `검증 ${stats.datasets.verified ?? 0} · 후보 ${stats.datasets.candidate ?? 0} · 포털 목록 ${stats.catalog.toLocaleString()} · 실측 조인 ${stats.measured_edges} · 코드표 ${stats.code_lists}`
    : '지식 체계 불러오는 중'

  return (
    <div className={`pds-app pds-app--${view}`}>
      <div className="pds-switch">
        <AgentSegmentedControl size="sm" label="화면" value={view} onChange={(v) => setView(v as 'chat' | 'plan')}
          options={[{ value: 'chat', label: '대화' }, { value: 'plan', label: plan ? `전략 v${plan.version}` : '전략' }]} />
      </div>

      <section className="pds-chat" aria-label="대화">
        <header className="pds-chat-top">
          <div className="pds-brand-row">
            <h1 className="pds-brand">공공데이터 전략 도우미</h1>
            <a className="pds-docs-link" href="#/docs">Docs</a>
            <a className="pds-docs-link" href="#/wiki">Wiki</a>
            <a className="pds-docs-link" href="#/mcp">MCP</a>
          </div>
          <AgentTooltip content={statsText} position="bottom">
            <button type="button" className="pds-info" aria-label="지식 체계 규모">ⓘ</button>
          </AgentTooltip>
        </header>

        <div className="pds-msgs" ref={scroller}>
          {!turns.length ? (
            <AgentAIMessage role="assistant" name="PDS">
              <div className="pds-intro">
                <p>하고 싶은 일을 말해 주세요. 검증된 공공데이터와 실측된 조인 경로만으로 데이터 조합·단계·실행 코드를 만들어 오른쪽에 펼칩니다.</p>
                <div className="pds-row">
                  {EXAMPLES.map((e) => <AgentButton key={e} variant="secondary" size="sm" onClick={() => void send(e)}>{e}</AgentButton>)}
                </div>
              </div>
            </AgentAIMessage>
          ) : null}

          {turns.map((t, i) => {
            if (t.role === 'user') return <AgentAIMessage key={i} role="user" name="나">{t.content}</AgentAIMessage>
            const p = plans.find((x) => x.version === t.version)
            const open = (id: string) => (trustOf(p, id) === 'verified' || trustOf(p, id) === 'excluded') && t.version ? showPlan(t.version, id) : setDsId(id)
            const meta = t.status === 'done' && t.usage
              ? `${t.elapsed}s · ${t.usage.model.replace('claude-', '')} · 토큰 ${t.usage.input.toLocaleString()}/${t.usage.output.toLocaleString()}`
              : undefined
            return (
              <AgentAIMessage key={i} role="assistant" name="PDS" meta={meta}>
                <div className="pds-answer">
                  {t.steps?.length ? (() => {
                    const steps = (
                      <AgentPlan
                        className="pds-steps"
                        title={t.status === 'running' ? '진행 중' : '진행 기록'}
                        items={t.steps.map((s) => ({ id: s.id, label: s.label, status: STEP_STATUS[s.status], description: [s.detail, `${s.t}s`].filter(Boolean).join(' · ') }))}
                      />
                    )
                    // 끝나면 접어 둔다 — 답이 먼저 보이게
                    return t.status === 'running' ? steps : (
                      <AgentAccordion items={[{ id: 'steps', title: `진행 기록 · ${t.steps.length}단계 · ${t.elapsed ?? t.steps[t.steps.length - 1].t}s`, content: steps }]} />
                    )
                  })() : t.status === 'running' ? <p className="pds-ev">연결 중…</p> : null}
                  {t.content ? <Markdown text={t.content} open={open} resolve={(id) => trustOf(p, id)} /> : null}
                  {p ? (
                    <button type="button" className={`pds-vcard${version === p.version ? ' pds-vcard--on' : ''}`} onClick={() => showPlan(p.version!)}>
                      <span className="pds-vcard-name">전략 v{p.version}</span>
                      <span className="pds-ev">데이터 {p.datasets.length} · 조인 {p.joins.length} · 단계 {p.pipeline.length} · 코드 준비됨</span>
                      <span className="pds-vcard-chips">
                        <AgentChip variant="live">검증 {p.datasets.length}</AgentChip>
                        {p.not_recommended.length ? <AgentChip variant="hot">제외 {p.not_recommended.length}</AgentChip> : null}
                        {p.unverified_leads.length + p.candidates.length ? <AgentChip variant="neutral">단서 {p.unverified_leads.length + p.candidates.length}</AgentChip> : null}
                      </span>
                    </button>
                  ) : null}
                  {t.status === 'done' && t.turnId ? (
                    <div className="pds-feedback" role="group" aria-label="이 답이 도움이 됐나요?">
                      <span className="pds-ev">{t.rating ? '의견 고맙습니다' : '도움이 됐나요?'}</span>
                      {(['up', 'down'] as const).map((r) => (
                        <button key={r} type="button" className={`pds-fb${t.rating === r ? ' pds-fb--on' : ''}`} disabled={!!t.rating}
                          aria-label={r === 'up' ? '도움이 됐어요' : '아쉬워요'}
                          onClick={() => { void sendFeedback(t.turnId!, r); setTurns((ts) => ts.map((x, k) => (k === i ? { ...x, rating: r } : x))) }}>
                          {r === 'up' ? '👍' : '👎'}
                        </button>
                      ))}
                    </div>
                  ) : null}
                  {t.status === 'failed' ? (
                    <div className="pds-row">
                      <span className="pds-warn">오류: {t.error}</span>
                      {i === turns.length - 1 ? <AgentButton size="sm" variant="secondary" onClick={retry}>다시 시도</AgentButton> : null}
                    </div>
                  ) : null}
                </div>
              </AgentAIMessage>
            )
          })}
        </div>

        <div className="pds-composer" onKeyDownCapture={imeGuard}>
          <PromptInput
            value={draft}
            onValueChange={setDraft}
            onSubmit={(v) => void send(v)}
            disabled={busy}
            placeholder={busy ? '답을 만드는 중…' : '예) 성수동 상권 변화를 월 단위로 추적하고 싶어'}
          />
          <span className="pds-ev">Enter로 보내기 · Shift+Enter로 줄바꿈 — 답변에는 직접 불러 보거나 법령·검토로 확인된 내용만 씁니다</span>
          <span className="pds-ev">대화 내용은 서비스 개선을 위해 서버에 저장됩니다 (개인 식별 정보는 남기지 않습니다).</span>
          <Credit compact />
        </div>
      </section>

      <PlanPanel
        plan={plan}
        versions={plans.map((p) => p.version!)}
        version={version}
        onVersion={setVersion}
        tab={tab}
        onTab={setTab}
        focusId={focusId}
        onFocus={setFocusId}
        open={setDsId}
      />

      <DatasetDrawer id={dsId} onClose={() => setDsId(null)} open={setDsId} />
    </div>
  )
}
