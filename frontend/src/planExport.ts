// 전략 결과물 내려받기 — JSON(서버 응답 그대로, 에이전트·코드가 읽는 용)과 Markdown(사람이 읽는 보고서).
import type { Plan } from './api'

export function saveFile(name: string, text: string, type: string) {
  const url = URL.createObjectURL(new Blob([text], { type: `${type};charset=utf-8` }))
  const a = document.createElement('a')
  a.href = url
  a.download = name
  a.click()
  URL.revokeObjectURL(url)
}

const cell = (s: unknown) => String(s ?? '').replace(/\|/g, '\\|').replace(/\n/g, ' ')

export function planMarkdown(p: Plan, version: number | null): string {
  const title = new Map(p.datasets.map((d) => [d.id, d.title]))
  const name = (id: string) => title.get(id) ?? p.hubs[id] ?? id
  const out: string[] = [
    `# ${p.goal}`, '',
    `전략 v${version ?? 1} · 지식 ${p.knowledge_version} · 신뢰도 ${p.confidence}${p.context ? ` · 맥락 ${p.context}` : ''} · 내려받은 때 ${new Date().toLocaleString('ko-KR')}`, '',
  ]
  if (p.summary) out.push('## 요약', '', p.summary, '')
  if (p.heads?.length) {
    out.push('## 주제별 대표 데이터', '', '| 주제 | 필요 | 대표 | 후보 |', '|---|---|---|---|')
    for (const h of p.heads) {
      const rep = h.picks.find((x) => x.id === h.rep)
      out.push(`| ${cell(h.name)} | ${cell(h.need)} | ${rep ? `${cell(rep.title)} (${rep.id}, ${rep.tier})` : '-'} | ${h.picks.filter((x) => x.id !== h.rep).slice(0, 4).map((x) => `${cell(x.title)} (${x.id})`).join('<br>')} |`)
    }
    out.push('')
  }
  out.push('## 데이터', '')
  for (const d of p.datasets) {
    out.push(`### ${d.title} (${d.id})`, '', `- 역할: ${d.role} · 기관: ${d.agency} · 등급: ${d.tier}${d.rows != null ? ` · 실측 ${d.rows.toLocaleString()}행` : ''}`)
    out.push(`- 받는 곳: ${d.access.channel === 'external' ? '외부 사이트' : 'data.go.kr'}${d.access.approval ? ` · 승인 ${d.access.approval}` : ''}${d.portal_url ? ` · ${d.portal_url}` : ''}`)
    if (d.access.signup) out.push(`- 가입: ${d.access.signup.text}`)
    out.push(`- 고른 이유: ${d.why}`)
    for (const e of d.evidence) out.push(`  - 근거: ${e}`)
    for (const c of d.caveats) out.push(`  - 주의: ${c}`)
    out.push('')
  }
  if (p.joins.length) {
    out.push('## 조인', '', '| 왼쪽 | 오른쪽 | 키 | 관계 | 매칭률 |', '|---|---|---|---|---|')
    for (const j of p.joins) {
      const on = [j.on.left?.join(','), j.on.right?.join(',')].filter(Boolean).join(' = ') + (j.on.transform ? ` (${j.on.transform})` : '') + (j.via_mapping ? ` · 매핑 ${j.via_mapping}` : '')
      out.push(`| ${cell(name(j.left))} | ${cell(name(j.right))} | ${cell(on || j.hub || '')} | ${cell(j.relationship ?? j.rel)} | ${j.match_rate != null ? `${Math.round(j.match_rate * 1000) / 10}%` : '-'} |`)
    }
    out.push('')
  }
  if (p.aligned?.length) {
    out.push('## 단위 맞춤(느슨한 조인)', '')
    for (const a of p.aligned) out.push(`- ${name(a.left)} ↔ ${name(a.right)}: ${a.align.label} — ${a.note}`)
    out.push('')
  }
  if (p.pipeline.length) {
    out.push('## 단계', '')
    for (const s of p.pipeline) out.push(`${s.step}. ${s.do}${s.dataset ? ` (${name(s.dataset)})` : ''}${s.note ? ` — ${s.note}` : ''}`)
    out.push('')
  }
  if (p.gaps.length) out.push('## 공백 (채우지 못한 부분)', '', ...p.gaps.map((g) => `- ${g}`), '')
  if (p.external_signup?.length) {
    out.push('## 외부 사이트 가입', '')
    for (const s of p.external_signup) out.push(`- ${s.site}: ${s.how} — ${s.datasets.map((d) => `${d.title} (${d.id})`).join(', ')}`)
    out.push('')
  }
  if (p.not_recommended.length) out.push('## 제외', '', ...p.not_recommended.map((x) => `- ${x.title ?? x.id} (${x.id}): ${x.reason}`), '')
  const leads = [...p.candidates.map((c) => `- [선정·미검증] ${c.title} (${c.id})${c.blocked_by ? ` — ${c.blocked_by}` : ''}`),
    ...p.unverified_leads.map((l) => `- [포털 단서] ${l.title} (${l.id}, ${l.agency}) — ${l.portal_url}`)]
  if (leads.length) out.push('## 단서 (직접 확인 필요)', '', ...leads, '')
  if (p.code) out.push('## 실행 코드', '', '```python', p.code.trimEnd(), '```', '')
  return out.join('\n')
}
