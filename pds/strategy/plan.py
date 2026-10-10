"""전략 플래너 (KNOWLEDGE-SPEC §4·§6, BUILD-PLAN Phase 4) — 목표 문장 → 구조화된 전략 응답.

순서
  1 맥락 매칭(question) → 레시피가 있으면 그 데이터·조인·파이프라인 (골든셋 경로)
  2 없으면 넓게 찾기 — BM25(글자 겹침) 상위 60 + 의미 검색(e5 임베딩) 상위 60을 합쳐 관련도(0~1)로 매기고,
    고정 개수가 아니라 기준값(1위 대비 REL_MIN)으로 자른다. 맥락 멤버 가산점·지역 가중치. rerank=True면 LLM이 관련도 0~3을 다시 매긴다
  3 조합 — primary + 선언된 Edge로 이어지는 데이터(핵심, 최대 max_datasets) + 이어지지 않아도 관련도 높은 데이터(참고, 최대 max_refs, role=context)
    조인 경로 = edges.yaml의 선언된 Edge만 (networkx 최단 경로, 실측 높은 Edge 우선, 매칭률 0 제외)
  4 candidates = 검색된 candidate 층 (조인 참여 불가) · unverified_leads = catalog 층 상위 MAX_LEADS (단서)
  5 LLM은 summary·why 문장만 — 입력은 선택된 claim, 출력은 claim id 인용 (pds/service/llm.py). LLM 없이도 규칙 문장으로 응답
  6 §4 검증 규칙을 통과해야 반환 (validate)
  · 지역 범위가 목표와 어긋나는 데이터(부산 데이터 ↔ 성수동)는 고르기 전에 빼서 not_recommended에 사유와 함께 (region.py)
  · progress(stage, status, detail) 콜백으로 단계 진행을 알린다 — 웹은 SSE로 받아 단계 체크리스트를 그린다
"""
from __future__ import annotations

import datetime as dt
import os
import re
import subprocess
import time
from functools import lru_cache
from typing import Callable

import networkx as nx

from pds import config
from pds.schema import GROUNDED
from pds.service import index as sindex
from pds.strategy import fit
from pds.strategy import badges as bdg
from pds.strategy import region as rgn
from pds.strategy import signup

HUBS = {"15123287": "법정동 코드표", "15123899": "연속지적도(PNU)"}
ROLE_KINDS = ("access", "key", "cadence", "coverage", "legal_basis", "admin_note")


@lru_cache
def _commit() -> str:
    """지식 버전 = knowledge/를 마지막으로 바꾼 커밋 (설명서 머리말과 같은 기준 — 코드만 바뀐 커밋으로 어긋나지 않게)."""
    return subprocess.run(["git", "log", "-1", "--format=%h", "--", "knowledge"], capture_output=True, text=True,
                          cwd=config.ROOT).stdout.strip()


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
            "latency_ms": (d.get("verification") or {}).get("latency_ms"),
            "signup": signup.note(d["id"], d["channel"] == "external", sec.get("issuer"), (d.get("agency") or {}).get("name"))}


def _lead_access(row: dict) -> dict:
    ext = signup.catalog_external(row)
    return {"channel": "external" if ext else "portal", "signup": signup.note(str(row["id"]), ext, agency=row.get("agency_name"))}


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


POOL_K = 60          # 검색마다 가져오는 수 (BM25·의미 각각)
POOL_MAX = 40        # 조합에 넘기는 후보 풀 상한
REL_MIN = 0.42       # 1위 관련도 대비 이 비율 미만은 풀에서 뺀다
REF_MIN = 0.5        # 조인 없이 '참고'로 넣으려면 1위 대비 이 비율 이상
W_SEM = 0.6          # 관련도 = (1-W_SEM)·BM25 + W_SEM·의미 (의미 검색이 없으면 BM25만)
MAX_LEADS = 10
GRADE_WEIGHT = {"보조": 0.6, "3순위": 0.85, "가족판": 0.9}  # 6차 확대 등급 (facets.grade) — 보조 자료가 핵심 원장을 밀어내지 않게


def _relevance(q: str, sem_q: str) -> list[tuple[dict, float]]:
    """BM25와 의미 검색을 0~1로 맞춰 합친 관련도 — 글자가 겹치거나 뜻이 가깝거나."""
    from pds.service import semantic
    ix = sindex.get()
    bm = ix.search_datasets(q, POOL_K, tiers=("verified",), graded=False)
    sem, floor = semantic.search_floor(sem_q, POOL_K, tiers=("verified",))
    rel: dict[str, float] = {}
    by = {}
    btop = bm[0][1] if bm else 1.0
    for d, sc in bm:
        by[d["id"]] = d
        rel[d["id"]] = (sc / btop) * ((1 - W_SEM) if sem else 1.0)
    if sem:
        stop = max(sem[0][1], floor + 1e-6)
        for d, c in sem:
            by[d["id"]] = d
            rel[d["id"]] = rel.get(d["id"], 0.0) + W_SEM * max(0.0, (c - floor) / (stop - floor))
    return sorted(((by[i], r) for i, r in rel.items()), key=lambda x: -x[1])


def select(goal: str, rerank: bool = False) -> dict:
    ix = sindex.get()
    region = rgn.goal_regions(goal)
    q = clean_goal(goal)
    for n in region["names"]:  # 지명은 검색어가 아니라 필터 — '성수동'이 '성수기'와 겹치지 않게
        q = q.replace(n, " ")
    q = re.sub(r"\s+", " ", q).strip() or clean_goal(goal)
    ctx_hits = ix.search_contexts(q, 3)
    ctx = ctx_hits[0][0] if ctx_hits and ctx_hits[0][1] >= 3.5 else None
    ctxs = [c for c, sc in ctx_hits if ctx and sc >= 0.8 * ctx_hits[0][1]][:2]
    recipe = ix.recipes.get(ctx["recipe"].split("/")[-1].removesuffix(".yaml")) if ctx and ctx.get("recipe") else None
    sem_q = goal
    for n in region["names"]:
        sem_q = sem_q.replace(n, " ")
    hits = _relevance(q, sem_q)
    members = set()
    for c in ctxs:
        for i, d in ix.datasets.items():
            f, a, s = d["sector"].split("/")
            if any(m.get("dataset") == i or (m.get("sector") == f"{f} - {a}" and m.get("subsector") in (None, s)) for m in c["members"]):
                members.add(i)
    if recipe and recipe.get("status") != "approved":  # 초안 레시피는 통째로 쓰지 않고 가산점으로만
        members |= {x["id"] for x in recipe["datasets"]}
        recipe = None
    pinned = {m["dataset"] for c in ctxs for m in c["members"] if m.get("dataset")}
    have = {d["id"] for d, _ in hits}
    if hits and pinned:  # 데이터 단위로 지정된 맥락 멤버는 검색 점수가 낮거나 안 걸려도 풀에 넣는다 (국민연금 사업장 ↔ "회사 상태")
        base = 0.5 * hits[0][1]
        hits = [(d, max(s, base) if d["id"] in pinned else s) for d, s in hits]
        hits += [(ix.datasets[i], base) for i in sorted(pinned - have) if i in ix.datasets and ix.datasets[i]["tier"] == "verified"]
    # 실측 메타 적합도 — 제목이 비슷해도 실측 필드·단위가 질문과 어긋나면 내린다 (pds/strategy/fit.py)
    hits = [(d, s * _region_weight(d, region) * GRADE_WEIGHT.get(((d.get("facets") or {}).get("grade") or [""])[0], 1.0)) for d, s in hits]
    raw = {d["id"]: s * (1.6 if d["id"] in members else 1.0) for d, s in hits}  # 풀에 남길지는 메타 보정 전 관련도로 — 순서만 메타로 바꾼다
    # 맥락이 데이터 단위로 고른 멤버는 적힌 순서가 곧 사람 검토의 우선순위다 (앞 멤버 ×1.4 → 끝 멤버 ×1.0)
    order = {}
    for c in ctxs:
        ms = [m["dataset"] for m in c["members"] if m.get("dataset")]
        for k, i in enumerate(ms):
            order.setdefault(i, 1.0 + 0.4 * (1 - k / max(len(ms) - 1, 1)))
    mw = {d["id"]: fit.meta_weight(sem_q, d) for d, _ in hits}
    hits = [(d, s * (max(mw[d["id"]], 1.0) if d["id"] in pinned else mw[d["id"]])) for d, s in hits]
    if order:  # 맥락이 질문과 맞으면 그 멤버끼리는 글자 관련도가 아니라 적힌 순서 × 실측 메타 적합도로
        mtop = max((s for d, s in hits if d["id"] in order), default=0)   # ('상장 기업 재무제표'처럼 대상을 짚으면 그 멤버가 앞선다)
        hits = [(d, mtop * order[d["id"]] * mw[d["id"]] if d["id"] in order else s) for d, s in hits]
    scored = sorted(((d, s * (1.6 if d["id"] in members else 1.0)) for d, s in hits), key=lambda x: -x[1])
    excluded, kept = [], []
    for d, s in scored:  # 지역이 어긋나면 주제가 맞아도 쓰지 않는다 — 상위권이었던 것만 사유와 함께 남긴다
        why = rgn.mismatch(d, region)
        if not why:
            kept.append((d, s))
        elif s >= 0.4 * scored[0][1]:
            excluded.append({"id": d["id"], "title": d["title"], "reason": why, "kind": "region", "evidence": []})
    scored = kept
    if scored:  # 1순위 대비 REL_MIN 미만은 관련이 약하다 — 허브(PNU·법정동)로 아무거나 이어 붙이지 않게
        top = scored[0][1]
        rtop = max((raw.get(d["id"], 0) for d, _ in scored), default=0)
        keep = [(d, s) for d, s in scored if s >= REL_MIN * top or raw.get(d["id"], 0) >= REL_MIN * rtop]
        scored = keep[:POOL_MAX] + [(d, s) for d, s in keep[POOL_MAX:] if d["id"] in pinned]  # 맥락이 지정한 데이터는 상한에 밀리지 않게
    reranked = None
    if rerank and scored:
        from pds.strategy.rerank import rerank as llm_rerank
        sc = llm_rerank(goal, [d for d, _ in scored[:30]])
        if sc:  # 2점 이상만 — 순서는 LLM 점수, 같으면 검색 관련도
            top = [(d, s) for d, s in scored[:30] if sc.get(d["id"], 0) >= 2]
            if top:
                scored = sorted(top, key=lambda x: (-sc[x[0]["id"]], -x[1]))
                reranked = sc
    return {"ctx": ctx, "ctx_hits": ctx_hits, "recipe": recipe, "scored": scored, "members": members, "q": q,
            "region": region, "excluded": excluded[:4], "reranked": reranked}


def _region_weight(d: dict, region: dict) -> float:
    """목표에 지역이 없으면 한 지역 데이터(부산 심야약국·대전 유치원)는 전국 데이터 뒤로, 같은 지역이면 조금 앞으로."""
    r = rgn.dataset_region(d)
    if r is None:
        return 1.0
    if not region["sido"]:
        return 0.45
    return 1.15 if r in region["sido"] else 1.0


Progress = Callable[[str, str, str], None]


HEADS = os.environ.get("PDS_HEADS", "1") != "0"  # 멀티헤드 전략 (pds/strategy/multihead.py) — LLM 키가 없거나 실패하면 기존 검색으로


def plan(goal: str, use_llm: bool = True, max_datasets: int = 6, progress: Progress | None = None, rerank: bool = False,
         max_refs: int = 8, heads: bool | None = None) -> dict:
    ix = sindex.get()
    t0 = time.time()
    say = progress or (lambda *_: None)
    heads = HEADS if heads is None else heads
    mh = None
    say("context", "running", "")
    sel = select(goal, rerank=rerank and not heads)
    say("context", "done", sel["ctx"]["id"] if sel["ctx"] else "맥락 없음 — 검색만")
    n_ex = len(sel["excluded"])
    say("candidates", "done", f"검증 후보 {len(sel['scored'])}개" + (" · LLM 재순위" if sel.get("reranked") else "")
        + (f" · 지역 불일치 제외 {n_ex}개" if n_ex else ""))
    say("joins", "running", "")
    g = _graph()
    edges = {e["id"]: e for e in ix.edges}
    gaps = []

    if sel["recipe"]:  # 승인된 레시피 = 골든셋 경로
        r = sel["recipe"]
        chosen = list(dict.fromkeys(x["id"] for x in r["datasets"]))[:max_datasets + 2]
        join_ids = [j for j in r["joins"] if all(n in chosen or n in HUBS for n in (edges[j]["src"], edges[j]["dst"]))]
        source = f"recipe:{r['id']} ({r.get('status')})"
    elif heads and (mh := _run_heads(goal, sel, say)) is not None:
        chosen, join_ids, gaps = _compose_heads(mh, max_datasets, max_refs)
        source = "heads"
    else:
        cands = [d["id"] for d, _ in sel["scored"]]
        if not cands:
            return validate({"goal": goal, "summary": "관련 검증 데이터를 찾지 못했습니다.", "datasets": [], "joins": [], "pipeline": [],
                             "schedule": None, "candidates": [], "unverified_leads": _leads(goal, set(), sel["region"]),
                             "not_recommended": sel["excluded"], "hubs": {},
                             "gaps": [g["name"] for g, _ in ix.search_gaps(goal)], "confidence": 0.0,
                             "knowledge_version": _commit(), "source": "search"})
        primary = cands[0]
        rel = {d["id"]: s for d, s in sel["scored"]}
        chosen, join_ids, refs = [primary], [], []
        for other in cands[1:20]:
            if other in chosen:
                continue
            if len(chosen) < max_datasets and primary in g and other in g:
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
            # 이어지지 않아도 관련도가 높으면 '참고(조인 없음)'로 — 좋은 데이터를 조인 유무로 버리지 않는다
            if len(refs) < max_refs and rel.get(other, 0) >= REF_MIN * rel[primary]:
                refs.append(other)
        chosen += [r for r in refs if r not in chosen]
        if refs:
            gaps.append(f"참고 데이터 {len(refs)}개는 {ix.datasets[primary]['title'][:30]}와(과) 선언된 조인 경로가 없어 따로 받아 봐야 한다")
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
    aligned = _aligned_joins(datasets, joins)
    hubs_used = sorted({j["hub"] for j in joins if j.get("hub")})
    say("joins", "done", f"선언된 조인 {len(joins)}개" + (f" · 허브 {', '.join(hubs_used)}" if hubs_used else "") + f" ({time.time() - t0:.1f}s)")
    pipeline = [{"step": k + 1, "do": "fetch", "dataset": x["id"], "produces": f"{x['id']}.parquet"} for k, x in enumerate(datasets)]
    for j in joins:
        pipeline.append({"step": len(pipeline) + 1, "do": "join", "edge": j["edge"],
                         "note": f"{j['left']} ⋈ {j['right']}" + (f" via {j['hub']}" if j.get("hub") else "") +
                                 (f" ({j['on']['transform']})" if j["on"].get("transform") else "")})
    known = {x["id"] for x in datasets}
    q = sel["q"]
    if mh:  # 헤드별 대표·상위 후보 — 데이터 카드에 어느 주제 몫인지 붙인다
        for x in datasets:
            x["heads"] = [h["name"] for h in mh["heads"] if any(p["id"] == x["id"] for p in h["picks"])]
            x["head_rep"] = any(h["rep"] == x["id"] for h in mh["heads"])
        cand = [_cand_entry(ix.datasets[p["id"]], p) for p in _head_picks(mh, "candidate") if p["id"] not in known][:6]
    else:
        cand = [_cand_entry(d) for d, s in _cand_hits(q) if not rgn.mismatch(d, sel["region"])]
    gaps += [f"{g['name']}: {g['reason'][:120]}" for g, s in ix.search_gaps(q) if s > 6]
    gaps += unit_gaps(goal, datasets)
    counts = join_counts(joins)
    conf = _confidence(datasets, joins, counts, gaps, sel["ctx"])
    out = {"goal": goal, "context": sel["ctx"]["id"] if sel["ctx"] else None, "summary": None, "datasets": datasets, "joins": joins,
           "aligned": aligned,
           "pipeline": pipeline, "schedule": _schedule(datasets), "candidates": cand,
           "unverified_leads": _head_leads(mh) if mh else _leads(q, known | {c["id"] for c in cand}, sel["region"]),
           "heads": _heads_view(mh) if mh else None, "head_links": mh["links"] if mh else None,
           "not_recommended": sel["excluded"] + _not_recommended(chosen),
           "hubs": {h: n for h, n in HUBS.items() if any(h in (j["left"], j["right"]) for j in joins)},
           "region": {"names": sel["region"]["names"], "sido": sorted(sel["region"]["sido"])},
           "gaps": gaps, "confidence": conf, "join_counts": counts, "knowledge_version": _commit(),
           "source": source, "generated_at": dt.datetime.now().isoformat(timespec="seconds")}
    out["external_signup"] = signup.summarize(out)
    out["credentials"] = signup.credentials(out)  # 받는 데 필요한 키 — 에이전트가 사용자에게 .env를 채워 달라고 요청하는 근거
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


def _cand_entry(d: dict, pick: dict | None = None) -> dict:
    out = {"id": d["id"], "tier": "candidate", "title": d["title"], "sector": d["sector"],
           "status": (d.get("verification") or {}).get("verdict"), "why_maybe": pick["why"] if pick else _why_rule(d, "candidate"),
           "blocked_by": next((c["value"] for c in d.get("claims") or [] if c["kind"] == "pitfall"), None),
           "access": {"channel": d["channel"], "signup": _access(d)["signup"]}}
    if pick:
        out["head"] = pick["head"]
    return out


# ─────────────────────────── 멀티헤드 (pds/strategy/multihead.py) → 플래너 출력
def _run_heads(goal: str, sel: dict, say: Progress) -> dict | None:
    from pds.strategy import multihead
    mh = multihead.run(goal, sel["region"], say, whole=[d["id"] for d, _ in sel["scored"][:15]])
    if mh is None or not any(h["rep"] or h["picks"] for h in mh["heads"]):
        return None
    return mh


def _head_picks(mh: dict, tier: str, min_score: int = 2) -> list[dict]:
    """헤드를 돌아가며 그 층의 후보를 하나씩 — 대표 먼저, 한 주제가 목록을 독차지하지 않게."""
    per = [[{**p, "head": h["name"], "rep": p["id"] == h["rep"]}
            for p in sorted(h["picks"], key=lambda p: (p["id"] != h["rep"], -p["fit"]))
            if p["tier"] == tier and p["score"] >= min_score] for h in mh["heads"]]
    out, seen = [], set()
    for k in range(max((len(x) for x in per), default=0)):
        for x in per:
            if k < len(x) and x[k]["id"] not in seen:
                seen.add(x[k]["id"])
                out.append(x[k])
    return out


def _compose_heads(mh: dict, max_datasets: int, max_refs: int) -> tuple[list[str], list[str], list[str]]:
    """헤드별 검증 대표(대표가 목록·선정이면 그 헤드의 검증 1위)를 핵심으로, 대표끼리 선언된 조인 경로를 잇고, 나머지 검증 상위는 참고로."""
    ix = sindex.get()
    g = _graph()
    core = []

    def head_fit(h):
        r = next((p for p in h["picks"] if p["id"] == h["rep"]), None)
        return r["fit"] if r else 0.0
    for h in sorted(mh["heads"], key=lambda h: (not h["must"], -head_fit(h))):
        # 핵심 = 헤드 대표가 검증이면 그것, 아니면 그 헤드의 검증 3점짜리 (2점 대안은 핵심이 아니라 참고로)
        vs = sorted((p for p in h["picks"] if p["tier"] == "verified" and (p["id"] == h["rep"] or p["score"] >= 3)),
                    key=lambda p: (p["id"] != h["rep"], -p["fit"]))
        if vs and vs[0]["id"] not in core:
            core.append(vs[0]["id"])
    chosen, join_ids = list(core), []
    for k, a in enumerate(core):
        for b in core[k + 1:]:
            if a not in g or b not in g:
                continue

            def cost(u, v, d, ends=(a, b)):
                return d["weight"] + (0.0 if v in HUBS or v in ends or v in core else 0.8)
            try:
                path = nx.shortest_path(g, a, b, weight=cost)
            except nx.NetworkXNoPath:
                continue
            if len(path) > 4:
                continue
            for mid in path[1:-1]:
                if mid not in HUBS and mid not in chosen and len(chosen) < max_datasets:
                    chosen.append(mid)
            for x, y in zip(path, path[1:]):
                if g[x][y]["edge"] not in join_ids:
                    join_ids.append(g[x][y]["edge"])
    # 핵심과 선언된 조인(직접 또는 PNU·법정동 허브 경유)으로 이어지는 검증 후보 — 실측 매칭률이 있는 조인을 주제 분리로 잃지 않게
    for p in _head_picks(mh, "verified"):
        if len(chosen) >= max_datasets or p["id"] in chosen or p["id"] not in g:
            continue
        best = None
        for c in list(chosen):
            if c not in g:
                continue
            try:
                path = nx.shortest_path(g, c, p["id"], weight="weight")
            except nx.NetworkXNoPath:
                continue
            if len(path) == 2 or (len(path) == 3 and path[1] in HUBS):
                w = sum(g[x][y]["weight"] for x, y in zip(path, path[1:]))
                if best is None or w < best[0]:
                    best = (w, path)
        if best:
            chosen.append(p["id"])
            for x, y in zip(best[1], best[1][1:]):
                if g[x][y]["edge"] not in join_ids:
                    join_ids.append(g[x][y]["edge"])
    refs = [p["id"] for p in _head_picks(mh, "verified") if p["id"] not in chosen]
    chosen += refs[:max(0, min(max_refs, max_datasets + 4 - len(chosen)))]
    gaps = []
    for h in mh["heads"]:
        if not h["rep"]:
            gaps.append(f"주제 '{h['name']}'({h['need'][:40]})에 맞는 데이터를 찾지 못했다" + (" — 필수 주제" if h["must"] else ""))
        elif ix.datasets.get(h["rep"], {}).get("tier") != "verified":
            r = next(p for p in h["picks"] if p["id"] == h["rep"])
            gaps.append(f"주제 '{h['name']}'의 대표 데이터 '{r['title'][:40]}'는 미검증(포털 목록) — 직접 확인 후 사용")
    for lk in mh["links"]:
        if lk["kind"] == "none" and not lk.get("alt"):
            gaps.append(f"'{lk['heads'][0]}'와 '{lk['heads'][1]}' 대표 데이터는 공통 키·단위가 없어 따로 분석해야 한다")
    return chosen, join_ids, gaps


def _head_leads(mh: dict) -> list[dict]:
    out = []
    for p in _head_picks(mh, "catalog")[:MAX_LEADS]:
        it = mh["items"][p["id"]]
        out.append({"id": p["id"], "tier": "catalog", "title": it["title"], "agency": it.get("agency_name"),
                    "kind": it.get("api_type") or it.get("list_type"), "portal_url": it.get("url"), "similarity": round(p["score"] / 3, 2),
                    "head": p["head"], "rep": p["rep"], "score": p["score"], "unit": p.get("unit"),
                    "why_maybe": f"[{p['head']}] {p['why']}" + (f" — 프로젝트 제외 규칙 {p['excluded_by']}(검증 순서만 뒤)" if p.get("excluded_by") else ""),
                    "access": (acc := _lead_access(it)),
                    "what_to_check": [acc["signup"]["text"] if acc["signup"] else "활용신청 승인유형",
                                      "응답 필드로 추정한 연결 단위(" + (p.get("unit") or "없음") + ")가 실제로 맞는지", "최근 수정일·갱신 주기"],
                    "note": "미검증 — 직접 확인 후 판단"})
    return out


def _heads_view(mh: dict) -> list[dict]:
    keep = ("id", "tier", "title", "agency", "score", "why", "unit", "unit_estimated", "excluded_by", "links")
    ix = sindex.get()

    def signup_of(p: dict) -> str | None:  # 외부 사이트 가입이 따로 필요한지 — 카드마다 한 줄
        d = ix.datasets.get(p["id"]) if p["tier"] != "catalog" else None
        n = _access(d)["signup"] if d else _lead_access(mh["items"][p["id"]])["signup"]
        return n["text"] if n else None
    return [{"name": h["name"], "need": h["need"], "must": h["must"], "rep": h["rep"], "queries": h["queries"],
             "picks": [{k: p.get(k) for k in keep} | {"signup": signup_of(p)} for p in h["picks"][:6]]} for h in mh["heads"]]


def _cand_hits(q: str) -> list[tuple[dict, float]]:
    """candidate 층 — 1위 대비 40% 이상, 점수 5 초과, 최대 6."""
    hits = sindex.get().search_datasets(q, 6, tiers=("candidate",))
    top = hits[0][1] if hits else 0
    return [(d, s) for d, s in hits if s > 5 and s >= 0.4 * top]


SPACE_ORDER = ("point", "parcel", "bjd", "emd", "sgg", "sido", "national")
TIME_ORDER = ("realtime", "day", "month", "quarter", "year")
SPACE_NAME = {"point": "좌표", "parcel": "필지", "bjd": "법정동", "emd": "읍면동", "sgg": "시군구", "sido": "시도", "national": "전국"}
TIME_NAME = {"realtime": "실시간", "day": "일", "month": "월", "quarter": "분기", "year": "연"}
SPACE_RULE = {"point": "R-12", "parcel": "R-20", "bjd": "R-21", "emd": "R-21", "sgg": "R-21", "sido": "R-21"}


def align_pair(ga: dict | None, gb: dict | None) -> dict | None:
    """두 데이터의 단위(grain)로 느슨한 조인을 계산한다 — 공간·시간은 거친 쪽, 분류는 공통 체계. 맞출 축이 없으면 None."""
    if not ga or not gb:
        return None
    out, rules = {}, []
    sa, sb = ga.get("space"), gb.get("space")
    if sa and sb and "national" not in (sa, sb):
        lv = max(sa, sb, key=SPACE_ORDER.index)
        if lv == "point":
            lv = "parcel"  # 좌표끼리는 필지(R-12)로 모아 잇는다
        out["space"] = lv
        for g in (ga, gb):
            if g.get("space_via") == "address":
                rules.append("R-13")
            elif g.get("space_via") == "coord":
                rules.append("R-12")
            elif g.get("space_via") == "name":
                rules.append("R-14")
        rules.append(SPACE_RULE.get(lv, "R-21"))
    ta, tb = ga.get("time"), gb.get("time")
    if ta and tb:
        out["time"] = max(ta, tb, key=TIME_ORDER.index)
        if out["time"] != "realtime":
            rules.append("R-22")
    cat = sorted(set(ga.get("category") or []) & set(gb.get("category") or []))
    if cat:
        out["category"] = cat[0]
        rules.append("R-23")
    if not out.get("space") and not (out.get("time") and out.get("category")):
        return None  # 공간 축 없이 시간만 맞는 쌍은 너무 느슨하다 — 시간+분류가 함께 맞을 때만
    out["rules"] = list(dict.fromkeys(rules))
    out["label"] = " × ".join(x for x in (SPACE_NAME.get(out.get("space")), TIME_NAME.get(out.get("time")),
                                            ({"ksic": "업종", "seoul_svc": "서울 서비스업종", "hs_cd": "품목(HS)"}.get(out.get("category"), out.get("category")))) if x)
    return out


def _aligned_joins(datasets: list[dict], joins: list[dict]) -> list[dict]:
    """선언된 조인이 없는 데이터(참고)를 핵심(primary)·조인 데이터와 공통 단위로 잇는다 — 느슨한 조인(집계 후 결합).
    정확한 키 조인이 아니므로 joins와 분리하고, 해당 데이터의 역할을 'aligned'로 바꾼다."""
    ix = sindex.get()
    if not datasets:
        return []
    linked = {n for j in joins for n in (j["left"], j["right"])} | {datasets[0]["id"]}
    anchors = [d for d in datasets if d["id"] in linked and (ix.datasets.get(d["id"]) or {}).get("grain")]
    if not anchors:  # 핵심·조인 데이터에 단위가 없으면 단위가 있는 가장 앞 데이터를 기준으로
        first = next((d for d in datasets if ((ix.datasets.get(d["id"]) or {}).get("grain") or {}).get("space")), None)
        if first:
            anchors, linked = [first], linked | {first["id"]}
    out = []
    for d in datasets:
        if d["id"] in linked:
            continue
        g = (ix.datasets.get(d["id"]) or {}).get("grain")
        best = None
        for a in anchors:
            al = align_pair((ix.datasets.get(a["id"]) or {}).get("grain"), g)
            if al and (best is None or SPACE_ORDER.index(al.get("space", "national")) < SPACE_ORDER.index(best[1].get("space", "national"))):
                best = (a["id"], al)
        if best:
            gl, gr = (ix.datasets[best[0]].get("grain") or {}), (g or {})
            out.append({"kind": "aligned", "left": best[0], "right": d["id"], "align": best[1], "grain_left": gl, "grain_right": gr,
                        "on": {"left": (gl.get("space_fields") or []) + (gl.get("time_fields") or [])[:1],
                               "right": (gr.get("space_fields") or []) + (gr.get("time_fields") or [])[:1]},
                        "note": f"느슨한 조인 — {best[1]['label']} 단위로 집계한 뒤 결합 ({', '.join(best[1]['rules'])})"
                                + (" · 읍면동은 행정동·법정동 경계가 다를 수 있다 — 체계가 다르면 시군구로 올려 잇는다" if best[1].get("space") == "emd" else "")})
            d["role"] = "aligned"
    return out


TIME_ORDER = ["realtime", "day", "month", "quarter", "year"]
TIME_KO = {"realtime": "실시간", "day": "일", "month": "월", "quarter": "분기", "year": "연"}
TIME_ASK = [("realtime", r"실시간"), ("day", r"일별|일 단위|일단위|매일|하루 단위|일자별"),
            ("month", r"월별|월 단위|월단위|매월|월간|달마다"), ("quarter", r"분기"), ("year", r"연도별|연 단위|연단위|연간|매년|해마다")]


def unit_gaps(goal: str, datasets: list[dict]) -> list[str]:
    """목표가 시간 단위를 요구하는데 고른 데이터가 그보다 거칠면 공백으로 밝힌다 (예: 월 단위 요청 → 분기 데이터)."""
    want = next((u for u, pat in TIME_ASK if re.search(pat, goal)), None)
    if not want:
        return []
    ix = sindex.get()
    out = []
    for x in datasets:
        have = ((ix.datasets.get(x["id"]) or {}).get("grain") or {}).get("time")
        if have in TIME_ORDER and TIME_ORDER.index(have) > TIME_ORDER.index(want):
            out.append(f"단위 불일치 — 목표는 {TIME_KO[want]} 단위인데 {x['title'][:30]}({x['id']})는 {TIME_KO[have]} 단위다")
    return out


def join_counts(joins: list[dict]) -> dict:
    """조인을 데이터끼리 직접 잇는 것과 코드표·지적도(허브)로 정규화하는 것으로 나눠 센다 — 허브 연결만으로 '조인 n개'가 부풀지 않게."""
    hub = sum(1 for j in joins if j["left"] in HUBS or j["right"] in HUBS)
    return {"dataset_to_dataset": len(joins) - hub, "via_hub": hub}


def _confidence(datasets: list, joins: list, counts: dict, gaps: list, ctx) -> float:
    """0~0.95. 검증 데이터 수·데이터끼리 조인의 실측 매칭률·맥락에서 올리고, 공백(gaps)·데이터 간 직접 조인 부재에서 깎는다."""
    if not datasets:
        return 0.0
    direct = [j for j in joins if not (j["left"] in HUBS or j["right"] in HUBS)]
    rates = [j["match_rate"] if j["match_rate"] is not None else j["confidence"] or 0.5 for j in direct]
    c = 0.3 + 0.08 * min(len(datasets), 4) + (0.25 * (sum(rates) / len(rates)) if rates else 0) + (0.08 if ctx else 0)
    if len(datasets) > 1 and not direct:
        c -= 0.1  # 데이터끼리 직접 잇는 조인이 없다 — 허브 정규화나 느슨한 결합에 기댄다
    c -= min(0.3, 0.08 * len(gaps))
    return round(max(0.05, min(0.95, c)), 2)


def _summary_rule(p: dict) -> str:
    n = len(p["datasets"])
    ctx = f"맥락 '{p['context']}' 기준으로 " if p.get("context") else ""
    if not n:
        lead = len(p.get("unverified_leads") or []) + len(p.get("candidates") or [])
        return ("목표에 맞는 검증 데이터를 찾지 못했다." + (f" 미검증 단서 {lead}개를 포털에서 직접 확인해야 한다." if lead else "")
                + (f" 공백: {len(p['gaps'])}건." if p.get("gaps") else ""))
    jc = p.get("join_counts") or join_counts(p["joins"])
    al = len(p.get("aligned") or [])
    d, h = jc["dataset_to_dataset"], jc["via_hub"]
    hub = f"코드표·지적도로 정규화하는 연결 {h}개" if h else ""
    link = (f"데이터끼리 직접 조인 {d}개" + (f", {hub}" if hub else "")) if d else (f"데이터끼리 직접 잇는 조인은 없고 {hub}" if hub else "데이터끼리 직접 잇는 조인은 없다")
    return (f"{ctx}검증된 데이터 {n}개 — {link}." + (f" {al}개는 공통 단위(지역·시점)로 집계해 느슨하게 잇는다." if al else "")
            + (f" 공백 {len(p['gaps'])}건 — 목표의 일부는 이 조합으로 채우지 못한다." if p["gaps"] else "")
            + (" 외부 사이트 가입이 따로 필요한 데이터가 있다: " + ", ".join(g["site"] for g in p["external_signup"]) + "."
               if p.get("external_signup") else ""))


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
    res = ix.search_catalog(goal, MAX_LEADS * 2, exclude=known)
    if region:
        res = [(r, s) for r, s in res if not rgn.mismatch({"agency_name": r["agency_name"], "title": r["title"]}, region)]
    top0 = res[0][1] if res else 0
    res = [(r, s) for r, s in res if s >= 0.35 * top0][:MAX_LEADS]
    top = res[0][1] if res else 1
    for r, s in res:
        out.append({"id": r["id"], "tier": "catalog", "title": r["title"], "agency": r["agency_name"], "kind": r.get("api_type") or r.get("list_type"),
                    "portal_url": r.get("url"), "similarity": round(s / top, 2),
                    "why_maybe": "제목·설명이 목표와 비슷함" + (f" — 프로젝트 제외 규칙 {r['excluded_by']}" if isinstance(r.get("excluded_by"), str) else ""),
                    "access": (acc := _lead_access(r)),
                    "what_to_check": [acc["signup"]["text"] if acc["signup"] else "활용신청 승인유형",
                                      "출력 컬럼에 조인 키(법정동·PNU·사업자번호) 존재 여부", "최근 수정일·갱신 주기"],
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
    gone = {a["right"] for a in p.get("aligned") or [] if a["left"] == dsid}
    p["aligned"] = [a for a in p.get("aligned") or [] if dsid not in (a["left"], a["right"])]
    for x in p["datasets"]:
        if x["id"] in gone:
            x["role"] = "context"
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
    p["join_counts"] = join_counts(p["joins"])
    p["gaps"] = [g for g in p.get("gaps") or [] if f"({dsid})" not in g]  # 뺀 데이터에 대한 공백(단위 불일치 등)은 지운다
    if not p["datasets"]:
        p["gaps"].append("남은 검증 데이터가 없다 — 미검증 단서를 포털에서 직접 확인해야 한다")
    p["confidence"] = _confidence(p["datasets"], p["joins"], p["join_counts"], p["gaps"], p.get("context"))
    p["credentials"] = signup.credentials(p)
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
    if len(p["unverified_leads"]) > MAX_LEADS or any(x["tier"] != "catalog" for x in p["unverified_leads"]):
        raise ProtocolError("unverified_leads 규칙 위반")
    cand = {c["id"] for c in p["candidates"]}
    if any(j["left"] in cand or j["right"] in cand for j in p["joins"]):
        raise ProtocolError("candidate가 조인에 참여")
    return jsonable(p)
