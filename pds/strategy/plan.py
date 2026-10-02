"""전략 플래너 (KNOWLEDGE-SPEC §4·§6, BUILD-PLAN Phase 4) — 목표 문장 → 구조화된 전략 응답.

순서
  1 맥락 매칭(question) → 레시피가 있으면 그 데이터·조인·파이프라인 (골든셋 경로)
  2 없으면 verified 검색 + 맥락 멤버 가산점 → primary 1 + 후보 5
  3 조인 경로 = edges.yaml의 선언된 Edge만 (networkx 최단 경로, 실측 높은 Edge 우선, 매칭률 0 제외). 경로 없으면 gaps에 "조인 경로 미선언"
  4 candidates = 검색된 candidate 층 (조인 참여 불가) · unverified_leads = catalog 층 상위 5 (단서)
  5 LLM은 summary·why 문장만 — 입력은 선택된 claim, 출력은 claim id 인용 (pds/service/llm.py). LLM 없이도 규칙 문장으로 응답
  6 §4 검증 규칙을 통과해야 반환 (validate)
  · 지역 범위가 목표와 어긋나는 데이터(부산 데이터 ↔ 성수동)는 고르기 전에 빼서 not_recommended에 사유와 함께 (region.py)
  · progress(stage, status, detail) 콜백으로 단계 진행을 알린다 — 웹은 SSE로 받아 단계 체크리스트를 그린다
"""
from __future__ import annotations

import datetime as dt
import re
import subprocess
import time
from functools import lru_cache
from typing import Callable

import networkx as nx

from pds import config
from pds.schema import GROUNDED
from pds.service import index as sindex
from pds.strategy import badges as bdg
from pds.strategy import region as rgn

HUBS = {"15123287": "법정동 코드표", "15123899": "연속지적도(PNU)"}
ROLE_KINDS = ("access", "key", "cadence", "coverage", "legal_basis", "admin_note")


@lru_cache
def _commit() -> str:
    return subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=config.ROOT).stdout.strip()


@lru_cache
def _graph() -> nx.Graph:
    ix = sindex.get()
    g = nx.Graph()
    for e in ix.edges:
        if e["rel"] not in ("joinable", "lookup"):
            continue
        rate = (e.get("verified") or {}).get("match_rate")
        if rate == 0:
            continue
        a, b = e["src"], e["dst"]
        for x in (a, b):
            d = ix.datasets.get(x)
            if d is not None and d["tier"] != "verified":  # candidate는 조인 참여 불가 (§4)
                break
        else:
            w = 1.2 - (rate if rate is not None else e.get("confidence", 0.5) * 0.8)
            if not g.has_edge(a, b) or g[a][b]["weight"] > w:
                g.add_edge(a, b, weight=w, edge=e["id"])
    return g


def _claim_ids(dsid: str, kinds: tuple[str, ...]) -> list[str]:
    return [c["id"] for c in sindex.get().grounded_claims(dsid, kinds)]


def _access(d: dict) -> dict:
    s = (d.get("services") or [{}])[0]
    sec = s.get("security") or {}
    return {"channel": d["channel"], "issuer": sec.get("issuer") or ("data.go.kr" if d["channel"] == "portal" else None),
            "scheme": f"{sec.get('scheme', 'apiKey')}:{sec.get('in', 'query')}:{sec.get('name', 'serviceKey')}" if sec else "file",
            "approval": s.get("approval"), "daily_limit": (s.get("traffic") or {}).get("dev"),
            "latency_ms": (d.get("verification") or {}).get("latency_ms")}


def _fetch(d: dict) -> dict:
    s = next((x for x in d.get("services") or [] if x.get("verified_ok")), None) or (d.get("services") or [None])[0]
    if not s:
        dist = (d.get("distributions") or [{}])[0]
        return {"kind": "file", "portal_url": d.get("portal_url"), "file": dist.get("title"), "format": dist.get("format")}
    return {"op": s["op"], "endpoint": s["endpoint"], "method": s.get("method", "GET"),
            "params": {p["name"]: p.get("example") for p in s.get("params") or [] if p.get("required")},
            "paging": s.get("paging"), "format": s.get("format")}


def _why_rule(d: dict, role: str) -> str:
    cl = d.get("classification") or {}
    base = d.get("summary_user") or cl.get("why") or cl.get("subsector_name") or d["title"]
    return base.split(". ")[0].strip()[:220]


def _join_entry(e: dict, ix) -> dict:
    on = e.get("on") or {}
    return {"edge": e["id"], "left": e["src"], "right": e["dst"], "rel": e["rel"],
            "on": {"left": on.get("left"), "right": on.get("right"), "transform": on.get("transform")},
            "relationship": e.get("relationship"), "via_mapping": on.get("via_mapping"),
            "confidence": e.get("confidence"), "match_rate": (e.get("verified") or {}).get("match_rate"),
            "hub": HUBS.get(e["dst"]) or HUBS.get(e["src"])}


INTENT = re.compile(r"(하고\s*싶[다어음]|싶다|싶어|알고|알려\s*줘|보여\s*줘|찾아\s*줘|추적|분석|변화|확인|비교|어디|어떻게|무엇|뭐가|월\s*단위|"
                    r"단위로|데이터|정보|현황|목록|필요|하려면|보내지|믿어도\s*되나|되나|할까|인가)")


def clean_goal(goal: str) -> str:
    """목표 문장에서 의도·서술 표현을 빼고 대상어만 (검색 잡음 제거)."""
    return re.sub(r"\s+", " ", INTENT.sub(" ", goal)).strip() or goal


def select(goal: str) -> dict:
    ix = sindex.get()
    q = clean_goal(goal)
    ctx_hits = ix.search_contexts(q, 3)
    ctx = ctx_hits[0][0] if ctx_hits and ctx_hits[0][1] >= 3.5 else None
    ctxs = [c for c, sc in ctx_hits if ctx and sc >= 0.8 * ctx_hits[0][1]][:2]
    recipe = ix.recipes.get(ctx["recipe"].split("/")[-1].removesuffix(".yaml")) if ctx and ctx.get("recipe") else None
    hits = ix.search_datasets(q, 20, tiers=("verified",))
    members = set()
    for c in ctxs:
        for i, d in ix.datasets.items():
            f, a, s = d["sector"].split("/")
            if any(m.get("dataset") == i or (m.get("sector") == f"{f} - {a}" and m.get("subsector") in (None, s)) for m in c["members"]):
                members.add(i)
    if recipe and recipe.get("status") != "approved":  # 초안 레시피는 통째로 쓰지 않고 가산점으로만
        members |= {x["id"] for x in recipe["datasets"]}
        recipe = None
    scored = sorted(((d, s * (1.6 if d["id"] in members else 1.0)) for d, s in hits), key=lambda x: -x[1])
    region = rgn.goal_regions(goal)
    excluded, kept = [], []
    for d, s in scored:  # 지역이 어긋나면 주제가 맞아도 쓰지 않는다 — 상위권이었던 것만 사유와 함께 남긴다
        why = rgn.mismatch(d, region)
        if not why:
            kept.append((d, s))
        elif s >= 0.4 * scored[0][1]:
            excluded.append({"id": d["id"], "title": d["title"], "reason": why, "kind": "region", "evidence": []})
    scored = kept
    if scored:  # 1순위의 40% 미만은 관련이 약하다 — 허브(PNU·법정동)로 아무거나 이어 붙이지 않게
        scored = [(d, s) for d, s in scored if s >= 0.4 * scored[0][1]]
    return {"ctx": ctx, "ctx_hits": ctx_hits, "recipe": recipe, "scored": scored, "members": members, "q": q,
            "region": region, "excluded": excluded[:4]}


Progress = Callable[[str, str, str], None]


def plan(goal: str, use_llm: bool = True, max_datasets: int = 6, progress: Progress | None = None) -> dict:
    ix = sindex.get()
    t0 = time.time()
    say = progress or (lambda *_: None)
    say("context", "running", "")
    sel = select(goal)
    say("context", "done", sel["ctx"]["id"] if sel["ctx"] else "맥락 없음 — 검색만")
    n_ex = len(sel["excluded"])
    say("candidates", "done", f"검증 후보 {len(sel['scored'])}개" + (f" · 지역 불일치 제외 {n_ex}개" if n_ex else ""))
    say("joins", "running", "")
    g = _graph()
    edges = {e["id"]: e for e in ix.edges}
    gaps = []

    if sel["recipe"]:  # 승인된 레시피 = 골든셋 경로
        r = sel["recipe"]
        chosen = list(dict.fromkeys(x["id"] for x in r["datasets"]))[:max_datasets + 2]
        join_ids = [j for j in r["joins"] if all(n in chosen or n in HUBS for n in (edges[j]["src"], edges[j]["dst"]))]
        source = f"recipe:{r['id']} ({r.get('status')})"
    else:
        cands = [d["id"] for d, _ in sel["scored"]]
        if not cands:
            return validate({"goal": goal, "summary": "관련 검증 데이터를 찾지 못했습니다.", "datasets": [], "joins": [], "pipeline": [],
                             "schedule": None, "candidates": [], "unverified_leads": _leads(goal, set(), sel["region"]),
                             "not_recommended": sel["excluded"], "hubs": {},
                             "gaps": [g["name"] for g, _ in ix.search_gaps(goal)], "confidence": 0.0,
                             "knowledge_version": _commit(), "source": "search"})
        primary = cands[0]
        chosen, join_ids = [primary], []
        for other in cands[1:]:
            if len(chosen) >= max_datasets:
                break
            if primary in g and other in g:
                def cost(u, v, d, target=other):  # 허브가 아닌 무관한 데이터를 경유하면 벌점 — 목표와 상관없는 데이터가 끼지 않게
                    return d["weight"] + (0.0 if v in HUBS or v == target or v in cands else 0.8)
                try:
                    path = nx.shortest_path(g, primary, other, weight=cost)
                except nx.NetworkXNoPath:
                    path = None
                if path and len(path) <= 4:
                    for mid in path[1:-1]:  # 경로 가운데 데이터도 받아야 조인이 된다 (허브 제외)
                        if mid not in HUBS and mid not in chosen:
                            chosen.append(mid)
                    if other not in chosen:
                        chosen.append(other)
                    for a, b in zip(path, path[1:]):
                        if g[a][b]["edge"] not in join_ids:
                            join_ids.append(g[a][b]["edge"])
                    continue
            if len(chosen) < 3 and other not in chosen:  # 이어지지 않아도 상위 관련 데이터는 context 역할로
                chosen.append(other)
                gaps.append(f"{ix.datasets[primary]['title'][:30]} ↔ {ix.datasets[other]['title'][:30]}: 조인 경로 미선언")
        source = "search"

    connected = {primary_id for primary_id in chosen[:1]}
    for j in join_ids:
        connected |= {edges[j]["src"], edges[j]["dst"]}
    datasets = []
    for n, i in enumerate(chosen):
        d = ix.datasets.get(i)
        if d is None or d["tier"] != "verified":
            continue
        role = "primary" if n == 0 else ("lookup" if any(edges[j]["rel"] == "lookup" and edges[j]["dst"] == i for j in join_ids)
                                         else "join" if i in connected else "context")
        acc = _access(d)
        datasets.append({"id": i, "tier": "verified", "role": role, "title": d["title"], "agency": d["agency"]["name"],
                         "why": _why_rule(d, role), "evidence": _claim_ids(i, ROLE_KINDS)[:6],
                         "access": acc, "fetch": _fetch(d), "caveats": _claim_ids(i, ("pitfall",))[:4],
                         "portal_url": d.get("portal_url"), "rows": bdg.rows(d), "badges": bdg.badges(d, acc),
                         "claims": bdg.claims_view(d)})
    joins = [_join_entry(edges[j], ix) for j in join_ids]
    hubs_used = sorted({j["hub"] for j in joins if j.get("hub")})
    say("joins", "done", f"선언된 조인 {len(joins)}개" + (f" · 허브 {', '.join(hubs_used)}" if hubs_used else "") + f" ({time.time() - t0:.1f}s)")
    pipeline = [{"step": k + 1, "do": "fetch", "dataset": x["id"], "produces": f"{x['id']}.parquet"} for k, x in enumerate(datasets)]
    for j in joins:
        pipeline.append({"step": len(pipeline) + 1, "do": "join", "edge": j["edge"],
                         "note": f"{j['left']} ⋈ {j['right']}" + (f" via {j['hub']}" if j.get("hub") else "") +
                                 (f" ({j['on']['transform']})" if j["on"].get("transform") else "")})
    known = {x["id"] for x in datasets}
    q = sel["q"]
    cand = [{"id": d["id"], "tier": "candidate", "title": d["title"], "sector": d["sector"],
             "status": (d.get("verification") or {}).get("verdict"), "why_maybe": _why_rule(d, "candidate"),
             "blocked_by": next((c["value"] for c in d.get("claims") or [] if c["kind"] == "pitfall"), None)}
            for d, s in ix.search_datasets(q, 3, tiers=("candidate",)) if s > 5 and not rgn.mismatch(d, sel["region"])]
    gaps += [f"{g['name']}: {g['reason'][:120]}" for g, s in ix.search_gaps(q) if s > 6]
    rates = [j["match_rate"] if j["match_rate"] is not None else j["confidence"] or 0.5 for j in joins]
    conf = round(min(0.95, 0.35 + 0.1 * min(len(datasets), 4) + (0.25 * (sum(rates) / len(rates)) if rates else 0)
                     + (0.1 if sel["ctx"] else 0)), 2)
    out = {"goal": goal, "context": sel["ctx"]["id"] if sel["ctx"] else None, "summary": None, "datasets": datasets, "joins": joins,
           "pipeline": pipeline, "schedule": _schedule(datasets), "candidates": cand, "unverified_leads": _leads(q, known | {c["id"] for c in cand}, sel["region"]),
           "not_recommended": sel["excluded"] + _not_recommended(chosen),
           "hubs": {h: n for h, n in HUBS.items() if any(h in (j["left"], j["right"]) for j in joins)},
           "region": {"names": sel["region"]["names"], "sido": sorted(sel["region"]["sido"])},
           "gaps": gaps, "confidence": conf, "knowledge_version": _commit(),
           "source": source, "generated_at": dt.datetime.now().isoformat(timespec="seconds")}
    out["summary"] = _summary_rule(out)
    if use_llm:
        from pds.service import llm
        try:
            out = llm.explain(out)
        except Exception as e:  # noqa: BLE001 — LLM 실패해도 규칙 문장으로 응답
            out["llm_error"] = f"{type(e).__name__}: {str(e)[:200]}"
    from pds.strategy.codegen import render as codegen
    out["code"] = codegen(out)
    return validate(out)


def _summary_rule(p: dict) -> str:
    n = len(p["datasets"])
    j = len(p["joins"])
    ctx = f"맥락 '{p['context']}' 기준으로 " if p.get("context") else ""
    return f"{ctx}검증된 데이터 {n}개를 선언된 조인 {j}개로 잇는다." + (" 일부는 조인 경로가 없어 참고용이다." if p["gaps"] else "")


def _schedule(datasets: list[dict]) -> dict | None:
    ix = sindex.get()
    for x in datasets:
        for c in ix.grounded_claims(x["id"], ("cadence",)):
            if any(e["type"] == "measured" and "observe" in e["source"] for e in c["evidence"]):
                return {"cron": None, "reason": c["value"], "evidence": [c["id"]]}
    return None  # 갱신 관찰(7일 재호출) 전이라 실측 주기 근거 없음


def _leads(goal: str, known: set[str], region: dict | None = None) -> list[dict]:
    out = []
    ix = sindex.get()
    res = ix.search_catalog(goal, 10, exclude=known)
    if region:
        res = [(r, s) for r, s in res if not rgn.mismatch({"agency_name": r["agency_name"], "title": r["title"]}, region)]
    res = res[:5]
    top = res[0][1] if res else 1
    for r, s in res:
        out.append({"id": r["id"], "tier": "catalog", "title": r["title"], "agency": r["agency_name"], "kind": r.get("api_type") or r.get("list_type"),
                    "portal_url": r.get("url"), "similarity": round(s / top, 2),
                    "why_maybe": "제목·설명이 목표와 비슷함" + (f" — 프로젝트 제외 규칙 {r['excluded_by']}" if isinstance(r.get("excluded_by"), str) else ""),
                    "what_to_check": ["활용신청 승인유형", "출력 컬럼에 조인 키(법정동·PNU·사업자번호) 존재 여부", "최근 수정일·갱신 주기"],
                    "note": "미검증 — 직접 확인 후 판단"})
    return out


def _not_recommended(ids: list[str]) -> list[dict]:
    ix = sindex.get()
    out = []
    for i in ids:
        d = ix.datasets.get(i) or {}
        if d.get("status") in ("suspect_dead", "ended"):
            out.append({"id": i, "title": d.get("title"), "reason": f"상태 {d['status']}", "kind": "status", "evidence": []})
        dep = [c for c in d.get("claims") or [] if c.get("rank") == "deprecated"]
        if dep:
            out.append({"id": i, "title": d.get("title"), "reason": dep[0]["value"][:120], "kind": "deprecated", "evidence": [dep[0]["id"]]})
    return out


def exclude(p: dict, dsid: str, reason: str) -> dict:
    """전략에서 데이터 하나를 뺀다 — 채팅 LLM의 판단을 전략 JSON에 반영해 설명과 패널이 같은 말을 하게.
    그 데이터에 닿는 조인도 빼고, 남은 데이터의 역할·파이프라인·코드를 다시 만든다."""
    d = next((x for x in p["datasets"] if x["id"] == dsid), None)
    if d is None:
        return p
    p["datasets"] = [x for x in p["datasets"] if x["id"] != dsid]
    p["joins"] = [j for j in p["joins"] if dsid not in (j["left"], j["right"])]
    p["not_recommended"] = [*p["not_recommended"], {"id": dsid, "title": d["title"], "reason": reason, "kind": "review", "evidence": []}]
    linked = {n for j in p["joins"] for n in (j["left"], j["right"])}
    for k, x in enumerate(p["datasets"]):
        if k == 0:
            x["role"] = "primary"
        elif x["role"] in ("join", "lookup", "primary") and x["id"] not in linked:
            x["role"] = "context"
    p["pipeline"] = [{"step": k + 1, "do": "fetch", "dataset": x["id"], "produces": f"{x['id']}.parquet"} for k, x in enumerate(p["datasets"])]
    for j in p["joins"]:
        p["pipeline"].append({"step": len(p["pipeline"]) + 1, "do": "join", "edge": j["edge"],
                              "note": f"{j['left']} ⋈ {j['right']}" + (f" via {j['hub']}" if j.get("hub") else "")})
    p["hubs"] = {h: n for h, n in HUBS.items() if any(h in (j["left"], j["right"]) for j in p["joins"])}
    p["summary"] = _summary_rule(p)
    from pds.strategy.codegen import render as codegen
    p["code"] = codegen(p)
    return validate(p)


def jsonable(x):
    """NaN·numpy 값을 JSON 표준 값으로 (포털 카탈로그의 빈 칸이 NaN으로 들어온다)."""
    import math
    if isinstance(x, dict):
        return {k: jsonable(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [jsonable(v) for v in x]
    if hasattr(x, "item") and not isinstance(x, (str, bytes)):
        try:
            x = x.item()
        except (ValueError, AttributeError):
            pass
    if isinstance(x, float) and (math.isnan(x) or math.isinf(x)):
        return None
    return x


class ProtocolError(ValueError):
    pass


def validate(p: dict) -> dict:
    """§4 검증 규칙 — 어기면 응답 거부."""
    ix = sindex.get()
    edge_ids = {e["id"] for e in ix.edges}
    for x in p["datasets"]:
        d = ix.datasets.get(x["id"])
        if not d or d["tier"] != "verified":
            raise ProtocolError(f"datasets에 verified가 아닌 {x['id']}")
        claims = {c["id"]: c for c in d.get("claims") or []}
        for cid in x.get("evidence") or []:
            c = claims.get(cid)
            if not c:
                raise ProtocolError(f"{x['id']} evidence {cid} 없음")
            if not any(e["type"] in GROUNDED for e in c["evidence"]):
                raise ProtocolError(f"{cid}는 근거 없는(inferred만) claim")
    for j in p["joins"]:
        if j["edge"] not in edge_ids:
            raise ProtocolError(f"선언되지 않은 조인 {j['edge']}")
    if len(p["unverified_leads"]) > 5 or any(x["tier"] != "catalog" for x in p["unverified_leads"]):
        raise ProtocolError("unverified_leads 규칙 위반")
    cand = {c["id"] for c in p["candidates"]}
    if any(j["left"] in cand or j["right"] in cand for j in p["joins"]):
        raise ProtocolError("candidate가 조인에 참여")
    return jsonable(p)
