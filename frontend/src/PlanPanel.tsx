import { useEffect, useState, type ReactNode } from 'react'
import {
  AgentAccordion,
  AgentButton,
  AgentChip,
  AgentEmptyState,
  AgentPlan,
  AgentSegmentedControl,
  AgentTabs,
} from '@bv-ds/ui'
import type { Badge, Plan, PlanDataset } from './api'
import { JoinMap, fmtCount, shortTitle } from './JoinMap'
import { TrustIcon, TrustLegend } from './Trust'
import type { OpenDataset } from './md'

export type PlanTab = 'map' | 'data' | 'pipe' | 'code' | 'leads'

const ROLE_LABEL: Record<string, string> = { primary: '핵심', join: '조인', lookup: '코드 조회', context: '참고' }

function BadgeChip({ b }: { b: Badge }) {
  if (b.tone === 'warn') return <span className="pds-warn">⚠ {b.label}</span>
  const v = b.tone === 'ok' ? 'live' : b.tone === 'inf' ? 'primary' : b.tone === 'key' ? 'secondary' : 'neutral'
  return <AgentChip variant={v}>{b.label}</AgentChip>
}

function bestRate(p: Plan, id: string) {
  const r = p.joins.filter((j) => j.left === id || j.right === id).map((j) => j.match_rate).filter((x): x is number => x != null)
  return r.length ? Math.max(...r) : null
}

function DataCard({ d, plan, focus, open }: { d: PlanDataset; plan: Plan; focus: boolean; open: OpenDataset }) {
  const rate = bestRate(plan, d.id)
  const num = d.rows != null ? { v: fmtCount(d.rows), u: '전체 건수' } : rate != null ? { v: `${Math.round(rate * 100)}%`, u: '조인 매치' } : { v: '—', u: '건수 미상' }
  return (
    <article id={`ds-${d.id}`} className={`pds-card${focus ? ' pds-card--focus' : ''}`}>
      <div className="pds-card-main">
        <div className="pds-card-name">
          <TrustIcon trust="verified" />
          <AgentChip variant={d.role === 'primary' ? 'new' : d.role === 'context' ? 'neutral' : 'primary'}>{ROLE_LABEL[d.role] ?? d.role}</AgentChip>
          <button type="button" className="pds-card-title" onClick={() => open(d.id)} title="설명서 열기">{d.title}</button>
        </div>
        <div className="pds-card-meta">{d.agency} · {d.why}</div>
      </div>
      <div className="pds-card-num">{num.v}<small>{num.u}</small></div>
      <div className="pds-badges">{d.badges.map((b, i) => <BadgeChip key={i} b={b} />)}</div>
      {d.claims.length ? (
        <AgentAccordion
          className="pds-claims"
          items={[{
            id: 'ev',
            title: `근거 ${d.claims.length}건 보기`,
            content: (
              <table className="pds-claim-table">
                <tbody>
                  {d.claims.map((c) => (
                    <tr key={c.id}>
                      <th>{c.kind_label}</th>
                      <td>{c.value}<span className="pds-ev">{c.id} · {c.evidence.join('·')}{c.date ? ` · ${c.date}` : ''}</span></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ),
          }]}
        />
      ) : null}
    </article>
  )
}

// 클립보드 API는 https·localhost에서만 열린다 — http(bv.bigvalue.co.kr:9001)에서는 선택 후 복사로 대신한다
async function copyText(text: string): Promise<boolean> {
  if (window.isSecureContext && navigator.clipboard) {
    try {
      await navigator.clipboard.writeText(text)
      return true
    } catch { /* 아래 방식으로 */ }
  }
  const ta = document.createElement('textarea')
  ta.value = text
  ta.setAttribute('readonly', '')
  ta.style.position = 'fixed'
  ta.style.opacity = '0'
  document.body.appendChild(ta)
  ta.select()
  let ok = false
  try {
    ok = document.execCommand('copy')
  } finally {
    document.body.removeChild(ta)
  }
  return ok
}

function keysNeeded(p: Plan) {
  const portal = p.datasets.filter((d) => d.access.channel !== 'external')
  const ext = [...new Set(p.datasets.filter((d) => d.access.channel === 'external').map((d) => d.access.issuer || '외부 사이트'))]
  const auto = portal.every((d) => d.access.approval === 'auto')
  return [
    portal.length ? `data.go.kr 서비스키 1개로 ${portal.length}개 호출${auto ? ' (전부 자동승인)' : ' (일부 심의승인)'} — DATA_GO_KR_SERVICE_KEY` : '',
    ext.length ? `외부 키: ${ext.join(', ')}` : '',
  ].filter(Boolean).join(' · ')
}

export function PlanPanel(props: {
  plan: Plan | null
  versions: number[]
  version: number | null
  onVersion: (v: number) => void
  tab: PlanTab
  onTab: (t: PlanTab) => void
  focusId: string | null
  open: OpenDataset
  onFocus: (id: string) => void
}) {
  const { plan: p, versions, version, onVersion, tab, onTab, focusId, open, onFocus } = props
  const [copied, setCopied] = useState<'done' | 'fail' | null>(null)

  useEffect(() => {
    if (!focusId) return
    document.getElementById(`ds-${focusId}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' })
  }, [focusId, tab, version])

  if (!p) {
    return (
      <aside className="pds-panel">
        <div className="pds-pbody pds-pbody--empty">
          <AgentEmptyState title="전략이 여기에 나타납니다" description="왼쪽에서 하고 싶은 일을 말하면, 검증된 데이터·실측된 조인 경로·실행 코드를 이 자리에 펼칩니다." />
          <TrustLegend />
        </div>
      </aside>
    )
  }

  const leadsN = p.candidates.length + p.unverified_leads.length
  const ds = new Map(p.datasets.map((d) => [d.id, d]))
  const name = (id?: string) => (id ? (ds.get(id) ? shortTitle(ds.get(id)!.title, 22) : p.hubs[id] ?? id) : '')
  const excluded = (focusable: boolean) => p.not_recommended.map((x) => (
    <div key={x.id} id={focusable ? `ds-${x.id}` : undefined} className={`pds-excluded${focusable && focusId === x.id ? ' pds-card--focus' : ''}`}>
      <TrustIcon trust="excluded" />
      <AgentChip variant="hot">제외</AgentChip>
      <button type="button" className="pds-card-title" onClick={() => open(x.id)}>{x.title ?? x.id}</button>
      <span className="pds-ev">{x.reason}</span>
    </div>
  ))

  let content: ReactNode
  if (tab === 'map') {
    content = (
      <>
        {p.datasets.length ? <JoinMap plan={p} onSelect={(id) => { onTab('data'); onFocus(id) }} /> : null}
        <TrustLegend />
        {p.joins.length === 0 ? <p className="pds-note">선언된 조인이 없습니다 — 각 데이터를 따로 받아 참고용으로 씁니다.</p> : null}
        {p.gaps.length ? <div className="pds-note"><b>공백</b><ul>{p.gaps.map((g, i) => <li key={i}>{g}</li>)}</ul></div> : null}
        {p.not_recommended.length ? <><h3 className="pds-sec">제외한 데이터</h3>{excluded(false)}</> : null}
      </>
    )
  } else if (tab === 'data') {
    content = (
      <>
        {p.datasets.map((d) => <DataCard key={d.id} d={d} plan={p} focus={focusId === d.id} open={open} />)}
        {excluded(true)}
      </>
    )
  } else if (tab === 'pipe') {
    content = (
      <AgentPlan
        title="실행 순서"
        description={p.schedule ? `갱신: ${p.schedule.reason}` : '갱신 주기: 실측 관찰(7일 재호출) 전 — 근거 없음'}
        items={p.pipeline.map((s) => {
          const j = s.edge ? p.joins.find((x) => x.edge === s.edge) : undefined
          return {
            id: `s${s.step}`,
            status: 'pending' as const,
            label: s.do === 'fetch' ? `받기 — ${name(s.dataset)}` : `잇기 — ${name(j?.left)} ⋈ ${name(j?.right)}`,
            description: s.do === 'fetch'
              ? ds.get(s.dataset!)?.badges.filter((b) => b.kind === 'access' || b.kind === 'pitfall').map((b) => b.label).join(' · ')
              : j ? `${(j.on.left ?? []).join('+')} = ${(j.on.right ?? []).join('+')}${j.on.transform ? ` · 규칙 ${j.on.transform}` : ''} · ${j.match_rate == null ? '미측정' : `실측 ${Math.round(j.match_rate * 100)}%`}` : s.note,
          }
        })}
      />
    )
  } else if (tab === 'code') {
    content = (
      <>
        <p className="pds-note">필요한 키: {keysNeeded(p) || '없음'}</p>
        <pre className="pds-pre">{p.code}</pre>
      </>
    )
  } else {
    content = leadsN ? (
      <>
        <p className="pds-note">추천이 아니라 단서입니다. 호출·내용이 확인되지 않았으니 직접 확인한 뒤 쓰세요.</p>
        {p.candidates.map((c) => (
          <div key={c.id} className="pds-lead">
            <div className="pds-card-name"><TrustIcon trust="lead" /><AgentChip variant="neutral">후보</AgentChip>
              <button type="button" className="pds-card-title" onClick={() => open(c.id)}>{c.title}</button></div>
            <span className="pds-ev">{[c.status, c.blocked_by].filter(Boolean).join(' · ')}</span>
          </div>
        ))}
        {p.unverified_leads.map((l) => (
          <div key={l.id} className="pds-lead">
            <div className="pds-card-name"><TrustIcon trust="lead" />
              <a href={l.portal_url} target="_blank" rel="noreferrer">{l.title}</a></div>
            <span className="pds-ev">{l.agency}{l.kind ? ` · ${l.kind}` : ''} · 유사도 {l.similarity}</span>
            <span className="pds-ev">확인할 것: 활용신청 승인유형 · 조인 키(법정동·PNU·사업자번호) · 최근 수정일</span>
          </div>
        ))}
      </>
    ) : <AgentEmptyState compact title="단서 없음" description="포털 목록에서도 비슷한 데이터를 찾지 못했습니다." />
  }

  const download = () => {
    const url = URL.createObjectURL(new Blob([p.code], { type: 'text/x-python' }))
    const a = document.createElement('a')
    a.href = url
    a.download = `pds_strategy_v${version ?? 1}.py`
    a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <aside className="pds-panel">
      <header className="pds-phead">
        <div className="pds-phead-row">
          <h2 className="pds-ptitle">{p.goal} <span className="pds-pver">전략 v{version}</span></h2>
          {versions.length > 1 ? (
            <AgentSegmentedControl size="sm" label="전략 버전" value={String(version)} onChange={(v) => onVersion(Number(v))}
              options={versions.map((v) => ({ value: String(v), label: `v${v}` }))} />
          ) : null}
        </div>
        <div className="pds-row">
          <AgentChip variant="live">검증 {p.datasets.length}</AgentChip>
          {p.not_recommended.length ? <AgentChip variant="hot">제외 {p.not_recommended.length}</AgentChip> : null}
          {leadsN ? <AgentChip variant="neutral">단서 {leadsN}</AgentChip> : null}
          <span className="pds-ev">{p.context ? `맥락 ${p.context} · ` : ''}신뢰도 {p.confidence} · 지식 {p.knowledge_version}</span>
        </div>
        <AgentTabs
          label="전략 구성"
          value={tab}
          onChange={(t) => onTab(t as PlanTab)}
          items={[
            { id: 'map', label: '조인 지도' },
            { id: 'data', label: `데이터 ${p.datasets.length}` },
            { id: 'pipe', label: `단계 ${p.pipeline.length}` },
            { id: 'code', label: '코드' },
            { id: 'leads', label: `단서 ${leadsN}` },
          ]}
        />
      </header>
      <div className="pds-pbody">{content}</div>
      <footer className="pds-actions">
        <AgentButton size="sm" variant="primary" onClick={() => void copyText(p.code).then((ok) => { setCopied(ok ? 'done' : 'fail'); setTimeout(() => setCopied(null), 2000) })}>
          {copied === 'done' ? '복사됨' : copied === 'fail' ? '복사 실패 — .py로 받으세요' : '코드 복사'}
        </AgentButton>
        <AgentButton size="sm" variant="secondary" onClick={download}>.py 내려받기</AgentButton>
      </footer>
    </aside>
  )
}
