// 신뢰 단계 기호 — 카드·조인 지도·본문 참조·단서 탭 어디서나 같은 모양.
//   ● 검증(실호출 + 조인 실측)  ◐ 선언됐으나 미측정  ○ 단서(미검증)  × 제외
export type Trust = 'verified' | 'declared' | 'lead' | 'excluded'

const LABEL: Record<Trust, string> = {
  verified: '검증됨 — 실호출·실측',
  declared: '선언됐으나 미측정',
  lead: '미검증 단서',
  excluded: '제외',
}

export function TrustIcon({ trust }: { trust: Trust }) {
  return <span className={`pds-trust pds-trust--${trust}`} role="img" aria-label={LABEL[trust]} title={LABEL[trust]} />
}

export function TrustLegend() {
  return (
    <div className="pds-legend">
      {(['verified', 'declared', 'lead', 'excluded'] as Trust[]).map((t) => (
        <span key={t}><TrustIcon trust={t} />{LABEL[t]}</span>
      ))}
    </div>
  )
}
