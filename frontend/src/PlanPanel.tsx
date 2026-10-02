import { useState } from 'react'
import {
  AgentButton,
  AgentChip,
  AgentEmptyState,
  AgentPlan,
  AgentSectionPanel,
  AgentTabs,
} from '@bv-ds/ui'
import type { Plan, PlanJoin } from './api'
import { DsLink, type OpenDataset } from './md'

function Rate({ j }: { j: PlanJoin }) {
  if (j.match_rate == null) return <AgentChip variant="neutral">실측 보류</AgentChip>
  const p = Math.round(j.match_rate * 100)
  return <AgentChip variant={p >= 80 ? 'live' : 'secondary'}>실측 {p}%</AgentChip>
}

function access(d: Plan['datasets'][number]) {
  const a = d.access
  const ch = a.channel === 'external' ? `외부 사이트 키 ${a.issuer ?? ''}` : `포털 활용신청 ${a.approval ?? ''}`
  return [d.agency, ch, a.daily_limit ? `일 ${a.daily_limit.toLocaleString()}회` : ''].filter(Boolean).join(' · ')
}

export function PlanPanel({ plan, open }: { plan: Plan; open: OpenDataset }) {
  const [tab, setTab] = useState('data')
  const [copied, setCopied] = useState(false)
  const p = plan

  const data = p.datasets.length ? (
    <div className="pds-stack">
      {p.datasets.map((d) => (
        <AgentSectionPanel
          key={d.id}
          title={d.title}
          description={access(d)}
          action={<DsLink id={d.id} open={open} />}
        >
          <div className="pds-row">
            <AgentChip variant={d.role === 'context' ? 'secondary' : 'primary'}>{d.role}</AgentChip>
            <AgentChip variant="neutral">{d.tier}</AgentChip>
          </div>
          <p className="pds-body">{d.why}</p>
          <span className="pds-ev">
            근거 {d.evidence.join(', ')}
            {d.caveats.length ? ` · 주의 ${d.caveats.join(', ')}` : ''}
          </span>
        </AgentSectionPanel>
      ))}
    </div>
  ) : (
    <AgentEmptyState compact title="검증 데이터 없음" description="목표에 맞는 verified 데이터를 찾지 못했습니다. 후보·단서 탭을 보세요." />
  )

  const joins = (
    <div className="pds-stack">
      {p.joins.map((j) => (
        <AgentSectionPanel key={j.edge} title={`${j.edge} · ${j.rel}`} action={<Rate j={j} />}>
          <div className="pds-row">
            <DsLink id={j.left} open={open} /> <span>⋈</span> <DsLink id={j.right} open={open} />
            {j.hub ? <AgentChip variant="secondary">허브 {j.hub}</AgentChip> : null}
          </div>
          <span className="pds-ev">
            {(j.on.left ?? []).join('+')} = {(j.on.right ?? []).join('+')}
            {j.on.transform ? ` · 규칙 ${j.on.transform}` : ''}
            {j.via_mapping ? ` · 매핑 ${j.via_mapping}` : ''}
            {j.relationship ? ` · ${j.relationship}` : ''}
          </span>
        </AgentSectionPanel>
      ))}
      {p.gaps.length ? (
        <AgentSectionPanel title="공백 · 경로 없음" variant="filled">
          <ul className="pds-list">{p.gaps.map((g, i) => <li key={i}>{g}</li>)}</ul>
        </AgentSectionPanel>
      ) : null}
      {!p.joins.length && !p.gaps.length ? <AgentEmptyState compact title="조인 없음" description="단일 데이터로 충분한 목표입니다." /> : null}
    </div>
  )

  const pipe = (
    <div className="pds-stack">
      <AgentPlan
        title="실행 순서"
        description={p.schedule ? `갱신: ${p.schedule.reason}` : '갱신 주기: 실측 관찰(7일 재호출) 전 — 근거 없음'}
        items={p.pipeline.map((s, i) => ({
          id: `s${i}`,
          status: 'pending' as const,
          label: s.do === 'fetch' ? `받기 ${s.dataset}` : `조인 ${s.edge}`,
          description: s.do === 'fetch' ? p.datasets.find((d) => d.id === s.dataset)?.title : s.note,
        }))}
      />
    </div>
  )

  const code = (
    <div className="pds-stack">
      <div>
        <AgentButton
          variant="secondary"
          size="sm"
          onClick={() => navigator.clipboard.writeText(p.code).then(() => { setCopied(true); setTimeout(() => setCopied(false), 1500) })}
        >
          {copied ? '복사됨' : '코드 복사'}
        </AgentButton>
      </div>
      <pre className="pds-pre">{p.code}</pre>
    </div>
  )

  const more = (
    <div className="pds-stack">
      <AgentSectionPanel title="선정됐지만 미검증 (candidate)" description="지식 체계에 올라 있으나 호출 실측이 끝나지 않은 데이터">
        {p.candidates.length ? (
          <ul className="pds-list">
            {p.candidates.map((c) => (
              <li key={c.id}>
                {c.title} <DsLink id={c.id} open={open} />
                <span className="pds-ev">{[c.status, c.blocked_by].filter(Boolean).join(' · ')}</span>
              </li>
            ))}
          </ul>
        ) : <span className="pds-ev">없음</span>}
      </AgentSectionPanel>
      <AgentSectionPanel title="단서 — 포털 목록에서 비슷한 것 (catalog)" description="직접 확인이 필요합니다. 전략에는 쓰이지 않았습니다.">
        {p.unverified_leads.length ? (
          <ul className="pds-list">
            {p.unverified_leads.map((l) => (
              <li key={l.portal_url}>
                <a href={l.portal_url} target="_blank" rel="noreferrer">{l.title}</a>
                <span className="pds-ev">{l.agency} · 유사도 {l.similarity} · {l.why_maybe}</span>
              </li>
            ))}
          </ul>
        ) : <span className="pds-ev">없음</span>}
      </AgentSectionPanel>
    </div>
  )

  return (
    <div className="pds-plan">
      <p className="pds-body">{p.summary}</p>
      <div className="pds-row">
        {p.context ? <AgentChip variant="secondary">맥락 {p.context}</AgentChip> : null}
        <AgentChip variant="primary">신뢰도 {p.confidence}</AgentChip>
        <AgentChip variant="neutral">지식 {p.knowledge_version}</AgentChip>
      </div>
      <AgentTabs
        label="전략 구성"
        value={tab}
        onChange={setTab}
        items={[
          { id: 'data', label: `데이터 ${p.datasets.length}`, content: data },
          { id: 'joins', label: `조인 ${p.joins.length}`, content: joins },
          { id: 'pipe', label: '순서', content: pipe },
          { id: 'code', label: '코드', content: code },
          { id: 'more', label: `단서 ${p.candidates.length + p.unverified_leads.length}`, content: more },
        ]}
      />
    </div>
  )
}
