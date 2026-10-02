import type { Plan, PlanJoin } from './api'

// 조인 지도 — 허브(PNU·법정동)를 오른쪽에, 데이터를 왼쪽에 두고 선언된 조인을 선으로 잇는다.
// 실선 = 실측된 조인(매치율), 점선 = 선언됐으나 미측정. 허브가 없으면 연결이 가장 많은 데이터를 가운데로.

const W = 220
const H = 48
const GAP = 16
const VW = 720

export function shortTitle(t: string, n = 17) {
  const s = t.includes('_') ? t.slice(t.indexOf('_') + 1) : t
  return s.length > n ? s.slice(0, n - 1) + '…' : s
}

export function fmtCount(n?: number | null) {
  if (n == null) return ''
  if (n >= 1e8) return `${(n / 1e8).toFixed(1).replace(/\.0$/, '')}억`
  if (n >= 1e4) return `${Math.round(n / 1e4).toLocaleString()}만`
  return n.toLocaleString()
}

function edgeLabel(j: PlanJoin) {
  const rate = j.match_rate == null ? '미측정' : `${Math.round(j.match_rate * 100)}%`
  return (j.on.transform ? `${j.on.transform} · ` : '') + rate
}

function edgeTitle(j: PlanJoin) {
  return `${j.edge} · ${(j.on.left ?? []).join('+')} = ${(j.on.right ?? []).join('+')}` +
    (j.via_mapping ? ` · 매핑 ${j.via_mapping}` : '') + (j.relationship ? ` · ${j.relationship}` : '')
}

export function JoinMap({ plan, onSelect }: { plan: Plan; onSelect: (id: string) => void }) {
  const ids = new Set(plan.datasets.map((d) => d.id))
  const deg = new Map<string, number>()
  for (const j of plan.joins) for (const n of [j.left, j.right]) deg.set(n, (deg.get(n) ?? 0) + 1)
  // 오른쪽 열 = 허브 + 연결이 많은 데이터(3개 이상). 허브가 없으면 연결이 가장 많은 데이터 하나
  let centers = [...deg.keys()].filter((n) => n in plan.hubs || (deg.get(n) ?? 0) >= 3)
  if (!centers.length && plan.joins.length) {
    const top = [...deg.entries()].sort((a, b) => b[1] - a[1])[0]
    if (top[1] >= 2) centers = [top[0]]
  }
  const left = [...new Set(plan.datasets.map((d) => d.id))].filter((i) => !centers.includes(i))
  for (const n of deg.keys()) if (!ids.has(n) && !centers.includes(n)) left.push(n) // 계획 밖 끝점(드묾)

  const rows = Math.max(left.length, centers.length, 1)
  const VH = rows * (H + GAP) + GAP
  const pos = new Map<string, { x: number; y: number }>()
  left.forEach((n, i) => pos.set(n, { x: 8, y: GAP + i * (H + GAP) }))
  const cTop = (VH - centers.length * (H + GAP) + GAP) / 2
  centers.forEach((n, i) => pos.set(n, { x: VW - W - 8, y: cTop + i * (H + GAP) }))

  const ds = new Map(plan.datasets.map((d) => [d.id, d]))
  const nodeTitle = (n: string) => plan.hubs[n] ?? (ds.get(n) ? shortTitle(ds.get(n)!.title) : n)
  const nodeSub = (n: string) => {
    if (plan.hubs[n]) return `허브 · ${n}`
    const d = ds.get(n)
    if (!d) return n
    return [d.role, fmtCount(d.rows)].filter(Boolean).join(' · ')
  }

  return (
    <div className="pds-map">
      <svg viewBox={`0 0 ${VW} ${VH}`} role="img" aria-label={`조인 지도: 데이터 ${plan.datasets.length}개, 조인 ${plan.joins.length}개`}>
        {plan.joins.map((j) => {
          const a = pos.get(j.left)
          const b = pos.get(j.right)
          if (!a || !b) return null
          const cls = `pds-edge ${j.match_rate == null ? 'pds-edge--declared' : 'pds-edge--verified'}`
          let d: string
          let lx: number
          let ly: number
          if (a.x !== b.x) {
            const [l, r] = a.x < b.x ? [a, b] : [b, a]
            const x1 = l.x + W, y1 = l.y + H / 2, x2 = r.x, y2 = r.y + H / 2
            const mx = (x1 + x2) / 2
            d = `M${x1} ${y1} C ${mx} ${y1}, ${mx} ${y2}, ${x2} ${y2}`
            lx = mx - 30 // 곡선 가운데 — 같은 허브로 모이는 선들의 라벨이 겹치지 않게
            ly = (y1 + y2) / 2 - 4
          } else { // 같은 열끼리 — 오른쪽으로 부풀린 호
            const x = a.x + W, y1 = a.y + H / 2, y2 = b.y + H / 2
            const bulge = x + 70 + Math.abs(y2 - y1) * 0.15
            d = `M${x} ${y1} C ${bulge} ${y1}, ${bulge} ${y2}, ${x} ${y2}`
            lx = x + 14
            ly = (y1 + y2) / 2 + 4
          }
          return (
            <g key={j.edge}>
              <title>{edgeTitle(j)}</title>
              <path d={d} className={cls} />
              <text x={lx} y={ly} className="pds-edge-label">{edgeLabel(j)}</text>
            </g>
          )
        })}
        {[...pos.entries()].map(([n, p]) => {
          const hub = n in plan.hubs || centers.includes(n)
          const d = ds.get(n)
          const isolated = d && !deg.has(n)
          const cls = `pds-node${hub ? ' pds-node--hub' : ''}${d?.role === 'primary' ? ' pds-node--primary' : ''}${isolated ? ' pds-node--isolated' : ''}`
          return (
            <g key={n} className={cls} onClick={() => (d ? onSelect(n) : undefined)} style={d ? { cursor: 'pointer' } : undefined}>
              <title>{d ? d.title : plan.hubs[n] ?? n}{isolated ? ' — 조인 경로 없음(참고용)' : ''}</title>
              <rect x={p.x} y={p.y} width={W} height={H} rx={8} />
              <text x={p.x + 12} y={p.y + 20} className="pds-node-title">{nodeTitle(n)}</text>
              <text x={p.x + 12} y={p.y + 37} className="pds-node-sub">{nodeSub(n)}{isolated ? ' · 조인 없음' : ''}</text>
            </g>
          )
        })}
      </svg>
    </div>
  )
}
