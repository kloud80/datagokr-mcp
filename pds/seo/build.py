"""공개 전략 페이지(/data)의 재료를 모은다 → seo/strategies.json (python -m pds.seo.build).

전략 사례 두 갈래 (docs/seo/기획.md §3·§4)
  portal_1k  포털 AI 비교 1천 문항 중 우리가 이긴 답 — 판정 점수 합(20점 만점) 16 이상, 핵심 데이터 수가 포털 이상
  롱테일     pds/seo/questions/*.yaml 의 질문에 받아 둔 답(seo/answers) — 답과 데이터가 있는 것만
페이지마다 관련 전략(같은 데이터를 쓰는 것 → 같은 분야)과 '비슷한 질문으로 물어보기'(메인 /?q= 로 보내는 변형 질문)를 붙인다.
데이터 사전(/data/d/{id})을 만들 id = 전략에 나온 검증 데이터 ∪ 공공행정 검증 데이터.
"""
from __future__ import annotations

import datetime as dt
import json
import re
import sys
from collections import Counter, defaultdict

import yaml

from pds import config

E = config.ROOT / "evals" / "portal_1k"
ANS = config.ROOT / "seo" / "answers"
QDIR = config.ROOT / "pds" / "seo" / "questions"
OUT = config.ROOT / "seo" / "strategies.json"
DATASET_SECTORS = ("공공행정",)  # 1차 — 이 분야 검증 데이터는 전략에 안 나와도 데이터 사전을 만든다
MIN_SCORE, MIN_GAP = 16, 0

VARIANTS = {  # 질문 유형별 '비슷한 질문' 틀 — {t}는 주제
    "lookup": ["{t} 데이터의 필드와 호출 방법을 알려줘", "{t} 데이터를 우리 지역만 골라서 보려면?", "{t}와 함께 엮으면 좋은 공공데이터는?"],
    "combine": ["{t}를 시군구 단위로 맞춰서 비교하려면?", "{t} 분석을 월 단위로 하려면 어떤 데이터가 필요해?", "{t}를 지도로 그리려면 어떤 키로 이어야 해?"],
    "region": ["{t}를 다른 지역과 비교하려면?", "{t}를 읍면동 단위로 더 잘게 보려면?", "{t} 추이를 연도별로 보려면?"],
    "analysis": ["{t}에 쓸 데이터를 파이썬으로 받는 코드까지 알려줘", "{t}를 시군구별 순위로 보려면?", "{t}에서 빠진 데이터나 한계는 뭐야?"],
    "casual": ["{t} 데이터를 직접 받아 보려면 어떻게 해?", "{t}를 우리 동네 기준으로 보려면?", "{t}와 관련된 다른 공공데이터도 있어?"],
}


def _core(rel: dict, ids: list[str]) -> int:
    return sum(1 for i in set(ids) if rel.get(i) == 2)


def _topic(rec: dict) -> str:
    if rec.get("topic"):
        return rec["topic"]
    heads = (rec.get("plan") or {}).get("heads") or []
    if heads:
        return heads[0]["name"]
    return re.sub(r"\s*(있나요|있어요|어디|받는|방법|데이터|보고 싶어요|하고 싶어요|\?).*$", "", rec["q"])[:30] or rec["q"][:30]


def _cited(reply: str) -> list[str]:
    return list(dict.fromkeys(re.findall(r"\[\[(\d+)\]\]", reply or "")))


def _page(rec: dict, source: str, judge: dict | None = None) -> dict | None:
    chat = rec.get("chat") or {}
    reply = chat.get("reply")
    plan = rec.get("plan") or {}
    if not reply or not plan.get("datasets"):
        return None
    p = {"id": rec["id"], "q": rec["q"].strip(), "type": rec.get("type") or "lookup", "sector": rec.get("sector") or "분야 넘나듦",
         "topic": _topic(rec), "source": source, "reply": reply, "cited": _cited(reply),
         "datasets": [{k: d.get(k) for k in ("id", "title", "role")} for d in plan["datasets"]],
         "leads": [{k: x.get(k) for k in ("id", "title")} for x in plan.get("leads") or []],
         "heads": [h["name"] for h in plan.get("heads") or []], "gaps": plan.get("gaps") or [], "joins": plan.get("joins") or 0}
    if judge:
        p["compare"] = judge
    return p


def strategies() -> list[dict]:
    qs = {q["id"]: q for q in yaml.safe_load((E / "questions.yaml").read_text(encoding="utf-8"))}
    out = []
    for f in sorted((E / "judge").glob("*.json")):
        j = json.loads(f.read_text(encoding="utf-8"))
        a, rel, L = j.get("answer") or {}, j.get("relevance") or {}, j.get("lists") or {}
        if a.get("winner") != "ours":
            continue
        po, oo = _core(rel, L.get("portal_top5") or []), _core(rel, (L.get("ours_top5") or []) + (L.get("ours_cited") or []))
        so, sp = sum((a.get("ours") or {}).values()), sum((a.get("portal") or {}).values())
        if so < MIN_SCORE or oo - po < MIN_GAP:
            continue
        rec = json.loads((E / "ours" / f.name).read_text(encoding="utf-8"))
        rec.update({k: qs.get(j["id"], {}).get(k, rec.get(k)) for k in ("type", "topic", "sector")})
        pg = _page(rec, "portal_1k", {"portal_core": po, "ours_core": oo, "portal_score": sp, "ours_score": so,
                                      "portal_missing": a.get("portal_missing"), "scores": {"ours": a.get("ours"), "portal": a.get("portal")}})
        if pg:
            pg["date"] = "2026-10-08"
            out.append(pg)
    meta = {}
    for f in sorted(QDIR.glob("*.yaml")):
        for x in yaml.safe_load(f.read_text(encoding="utf-8")) or []:
            meta[x["id"]] = {**x, "set": f.stem}
    for f in sorted(ANS.glob("*.json")) if ANS.exists() else []:
        rec = json.loads(f.read_text(encoding="utf-8"))
        rec.update({k: v for k, v in meta.get(rec["id"], {}).items() if k in ("type", "sector", "topic")})
        pg = _page(rec, meta.get(rec["id"], {}).get("set", "longtail"))
        if pg:
            pg["date"] = dt.date.fromtimestamp(f.stat().st_mtime).isoformat()
            out.append(pg)
    return out


def link(pages: list[dict]) -> None:
    """관련 전략(같은 데이터 → 같은 분야)과 변형 질문."""
    by_ds = defaultdict(set)
    for p in pages:
        for d in p["datasets"]:
            by_ds[d["id"]].add(p["id"])
    by_sec = defaultdict(list)
    for p in pages:
        by_sec[p["sector"]].append(p["id"])
    have = {p["q"] for p in pages}
    for p in pages:
        score = Counter()
        for d in p["datasets"]:
            for o in by_ds[d["id"]]:
                if o != p["id"]:
                    score[o] += 2 if d["role"] == "primary" else 1
        rel = [o for o, _ in score.most_common(6)]
        for o in by_sec[p["sector"]]:
            if len(rel) >= 8:
                break
            if o != p["id"] and o not in rel:
                rel.append(o)
        p["related"] = rel
        t = p["topic"]
        p["variants"] = [v.format(t=t) for v in VARIANTS.get(p["type"], VARIANTS["lookup"]) if v.format(t=t) not in have]


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    from pds.service import index
    ix = index.get()
    pages = strategies()
    link(pages)
    ds = {d["id"] for p in pages for d in p["datasets"] if d["id"] in ix.datasets}
    ds |= {i for p in pages for i in p["cited"] if i in ix.datasets}
    ds |= {d["id"] for d in ix.datasets.values() if (d.get("sector") or "").startswith(DATASET_SECTORS)}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"built": dt.datetime.now().isoformat(timespec="seconds"), "knowledge_version": getattr(ix, "version", None),
                               "strategies": pages, "datasets": sorted(ds)}, ensure_ascii=False, indent=0), encoding="utf-8")
    print({"전략": len(pages), "출처": dict(Counter(p["source"] for p in pages)), "분야": dict(Counter(p["sector"] for p in pages).most_common()),
           "데이터 사전": len(ds)})


if __name__ == "__main__":
    main()
