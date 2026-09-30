"""레시피 초안 (KNOWLEDGE-SPEC §7-10) — Context의 멤버 데이터를 선언된 Edge만으로 잇는 파이프라인. 골든셋 정답의 출발점.

규칙 (원칙 §10-1: 조인은 선언된 것만)
  · 멤버 = 맥락의 세부 부문(또는 데이터셋)에 속한 verified Dataset
  · 그래프 = edges.yaml의 joinable·lookup (실측 매칭률 0인 것 제외) + 허브(법정동 코드표·연속지적도)
  · primary = 멤버 중 다른 멤버와 가장 많이 이어진 것, 나머지는 primary에서 최단 경로(networkx)로 — 경로 위 Edge만 joins에
  · 이어지지 않는 멤버는 레시피에 넣지 않고 note에 남긴다 (조인 경로 미선언 → 전략 응답의 gaps)
status: draft, author: claude-draft — 구름이 정답으로 확정하면 approved.
"""
from __future__ import annotations

import networkx as nx

from pds.schema import Recipe
from pds.schema import store

HUBS = {"15123287": "법정동 코드표", "15123899": "연속지적도(PNU)"}


def _graph() -> nx.Graph:
    g = nx.Graph()
    for e in store.load("edge"):
        if e["rel"] not in ("joinable", "lookup"):
            continue
        rate = (e.get("verified") or {}).get("match_rate")
        if rate is not None and rate == 0:
            continue
        w = 1.0 - (rate if rate is not None else e.get("confidence", 0.5)) * 0.5  # 실측 높을수록 가까움
        if g.has_edge(e["src"], e["dst"]) and g[e["src"]][e["dst"]]["weight"] <= w:
            continue
        g.add_edge(e["src"], e["dst"], weight=w, edge=e["id"], rel=e["rel"])
    return g


def _members(ctx: dict, ds: dict) -> list[str]:
    out = []
    for i, d in ds.items():
        f, a, s = d["sector"].split("/")
        for m in ctx["members"]:
            if m.get("dataset") == i or (m.get("sector") == f"{f} - {a}" and m.get("subsector") in (None, s)):
                out.append(i)
                break
    return out


def draft(ctx: dict, g: nx.Graph, ds: dict) -> dict | None:
    mem = [m for m in _members(ctx, ds) if m in g]
    if len(mem) < 2:
        return None
    best, reach = None, {}
    for m in mem:
        lengths = nx.single_source_dijkstra_path(g, m, weight="weight")
        r = {x: p for x, p in lengths.items() if x in mem and x != m and len(p) <= 4}
        if best is None or len(r) > len(reach):
            best, reach = m, r
    if not reach:
        return None
    joins, steps, fetched = [], [], [best]
    steps.append({"step": 1, "do": "fetch", "dataset": best, "produces": f"{best}.parquet"})
    for target, path in sorted(reach.items(), key=lambda kv: len(kv[1])):
        for a, b in zip(path, path[1:]):
            if b not in fetched and b not in HUBS:
                steps.append({"step": len(steps) + 1, "do": "fetch", "dataset": b, "produces": f"{b}.parquet"})
                fetched.append(b)
            eid = g[a][b]["edge"]
            if eid not in joins:
                joins.append(eid)
                steps.append({"step": len(steps) + 1, "do": "join", "edge": eid,
                              "note": f"{a} ⋈ {b}" + (f" (허브 {HUBS[b]})" if b in HUBS else "") + (f" (허브 {HUBS[a]})" if a in HUBS else "")})
    unreached = [m for m in mem if m != best and m not in reach]
    rec = {"id": ctx["id"], "goal_examples": [q for q in [ctx.get("question")] if q] or [ctx["name"]], "context": ctx["id"],
           "datasets": [{"id": best, "role": "primary"}] + [{"id": x, "role": "join"} for x in fetched[1:]],
           "joins": joins, "pipeline": steps, "author": "claude-draft", "status": "draft"}
    Recipe.model_validate(rec)
    return {"recipe": rec, "reached": len(reach), "members": len(mem), "unreached": unreached}


def write(top: int = 10) -> dict:
    ds = {d["id"]: d for d, _ in store.iter_raw("dataset") if d.get("tier") == "verified"}
    g = _graph()
    drafts = []
    for ctx, path in store.iter_raw("context"):
        r = draft(ctx, g, ds)
        if r:
            drafts.append((r, ctx, path))
    drafts.sort(key=lambda x: (-x[0]["reached"], -x[0]["members"]))
    written = []
    for r, ctx, path in drafts[:top]:
        rec = r["recipe"]
        header = (f"레시피 초안 — 맥락 {ctx['name']} (KNOWLEDGE-SPEC §3.7). pds/strategy/recipe_draft.py 생성, 구름 확정 전(draft).\n"
                  f"멤버 {r['members']}개 중 선언된 Edge로 이어진 {r['reached'] + 1}개. 이어지지 않은 멤버: {', '.join(r['unreached'][:10]) or '없음'}")
        store.dump(rec, store.PATHS["recipe"] / f"{rec['id']}.yaml", header=header)
        ctx["recipe"] = f"recipes/{rec['id']}.yaml"
        store.dump(ctx, path)
        written.append((rec["id"], r["reached"] + 1, r["members"], len(rec["joins"])))
    return {"candidates": len(drafts), "written": written}


if __name__ == "__main__":
    print(write())
