import { useState, type ReactNode } from 'react'

// 상자와 선으로 된 도식 — 상자를 누르면 아래에 설명이 열린다. 색·글꼴은 토큰(클래스)으로.

export interface DNode {
  id: string
  x: number
  y: number
  w?: number
  h?: number
  label: string
  sub?: string
  tone?: 'core' | 'source' | 'derived' | 'service' | 'use' | 'ext'
  detail?: ReactNode
}

export interface DLink {
  from: string
  to: string
  label?: string
  dashed?: boolean
}

const W = 168
const H = 52

function anchor(a: DNode, b: DNode) {
  const aw = a.w ?? W, ah = a.h ?? H, bw = b.w ?? W, bh = b.h ?? H
  const ax = a.x + aw / 2, ay = a.y + ah / 2, bx = b.x + bw / 2, by = b.y + bh / 2
  const dx = bx - ax, dy = by - ay
  // 상자 테두리에서 출발·도착하도록 — 더 긴 축 방향의 변을 쓴다
  const pa = Math.abs(dx) * ah > Math.abs(dy) * aw
    ? { x: ax + Math.sign(dx) * aw / 2, y: ay + (dy * (aw / 2)) / Math.abs(dx || 1) }
    : { x: ax + (dx * (ah / 2)) / Math.abs(dy || 1), y: ay + Math.sign(dy) * ah / 2 }
  const pb = Math.abs(dx) * bh > Math.abs(dy) * bw
    ? { x: bx - Math.sign(dx) * bw / 2, y: by - (dy * (bw / 2)) / Math.abs(dx || 1) }
    : { x: bx - (dx * (bh / 2)) / Math.abs(dy || 1), y: by - Math.sign(dy) * bh / 2 }
  return { pa, pb }
}

export function Diagram({ nodes, links, width, height, title, initial }: {
  nodes: DNode[]
  links: DLink[]
  width: number
  height: number
  title: string
  initial?: string
}) {
  const [sel, setSel] = useState<string | null>(initial ?? null)
  const by = new Map(nodes.map((n) => [n.id, n]))
  const cur = sel ? by.get(sel) : undefined
  return (
    <figure className="doc-figure">
      <div className="doc-diagram">
        <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label={title}>
          <defs>
            <marker id={`arr-${title.length}`} viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto">
              <path d="M0 0L10 5L0 10z" className="doc-arrow" />
            </marker>
          </defs>
          {links.map((l, i) => {
            const a = by.get(l.from), b = by.get(l.to)
            if (!a || !b) return null
            const { pa, pb } = anchor(a, b)
            const on = sel && (l.from === sel || l.to === sel)
            return (
              <g key={i} className={`doc-link${on ? ' doc-link--on' : ''}`}>
                <line x1={pa.x} y1={pa.y} x2={pb.x} y2={pb.y} strokeDasharray={l.dashed ? '5 4' : undefined} markerEnd={`url(#arr-${title.length})`} />
                {l.label ? <text x={(pa.x + pb.x) / 2 + 4} y={(pa.y + pb.y) / 2 - 4} className="doc-link-label">{l.label}</text> : null}
              </g>
            )
          })}
          {nodes.map((n) => (
            <g key={n.id} className={`doc-node doc-node--${n.tone ?? 'derived'}${sel === n.id ? ' doc-node--on' : ''}`}
              onClick={() => setSel(sel === n.id ? null : n.id)} role="button" tabIndex={0}
              onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') setSel(sel === n.id ? null : n.id) }}>
              <rect x={n.x} y={n.y} width={n.w ?? W} height={n.h ?? H} rx={10} />
              <text x={n.x + (n.w ?? W) / 2} y={n.y + (n.sub ? 22 : 30)} textAnchor="middle" className="doc-node-label">{n.label}</text>
              {n.sub ? <text x={n.x + (n.w ?? W) / 2} y={n.y + 39} textAnchor="middle" className="doc-node-sub">{n.sub}</text> : null}
            </g>
          ))}
        </svg>
      </div>
      <figcaption className="doc-caption">
        {cur ? <><b>{cur.label}</b>{cur.sub ? ` · ${cur.sub}` : ''}<div>{cur.detail}</div></> : <span>상자를 누르면 설명이 열립니다.</span>}
      </figcaption>
    </figure>
  )
}
