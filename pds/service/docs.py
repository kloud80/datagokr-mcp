"""Docs 화면용 집계 (GET /api/docs) — 지식 체계에서 바로 센다. 데이터가 늘면 문서 숫자도 따라 바뀐다.

규모 · 깔때기 · 라운드별 검증 · 부문별 · 근거(claim·evidence) · 조인(관계·규칙·허브·실측률) · 키 · 맥락 · 매핑 · 커버리지 분포 ·
데이터별 표(범위·커버리지 수준) · 실제 파일 예시(YAML)
"""
from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from functools import lru_cache

from pds import config
from pds.schema import GROUNDED
from pds.service import index as sindex

HUBS = {"15123899": "연속지적도(PNU)", "15123287": "법정동 코드표"}


def _lag(d: dict) -> int | None:
    for c in d.get("claims") or []:
        if c["kind"] == "cadence":
            m = re.search(r"관측일 기준 (\d+)일 전", c["value"])
            if m:
                return int(m.group(1))
    return None


def _rows(d: dict) -> int | None:
    v = (d.get("verification") or {}).get("total_count")
    if isinstance(v, int) and v > 0:
        return v
    for c in d.get("claims") or []:
        if c["kind"] == "coverage":
            m = re.search(r"전체 건수 ([\d,]+)", c["value"])
            if m:
                return int(m.group(1).replace(",", ""))
    return None


def _bucket(v, edges: list[tuple[float, str]], none: str) -> str:
    if v is None:
        return none
    for lim, name in edges:
        if v <= lim:
            return name
    return edges[-1][1]


def _yaml_example(rel: str, keep: int = 60) -> str:
    p = config.KNOWLEDGE / rel
    if not p.exists():
        return ""
    lines = p.read_text(encoding="utf-8").splitlines()
    return "\n".join(lines[:keep]) + ("\n# … (이하 생략)" if len(lines) > keep else "")


def _edge_example(edges: list[dict]) -> str:
    import yaml
    e = next((x for x in edges if (x.get("on") or {}).get("transform") == "R-13" and (x.get("verified") or {}).get("match_rate")), edges[0])
    return yaml.safe_dump(e, allow_unicode=True, sort_keys=False)


@lru_cache(maxsize=4)
def _build(stamp: float) -> dict:
    ix = sindex.get()
    ds = ix.datasets
    edges = ix.edges
    # 조인
    deg, best = Counter(), {}
    for e in edges:
        r = (e.get("verified") or {}).get("match_rate")
        for n in (e["src"], e["dst"]):
            deg[n] += 1
            if r is not None:
                best[n] = max(best.get(n, 0), r)
    rate_b = Counter(_bucket((e.get("verified") or {}).get("match_rate"), [(0.5, "50% 이하"), (0.8, "50~80%"), (0.95, "80~95%"), (0.999, "95~99%"), (1.0, "100%")], "미측정")
                     for e in edges if e["rel"] != "related_to")
    hub_n = Counter(h for e in edges for h in (e["src"], e["dst"]) if h in HUBS)
    rules = {r["id"]: r.get("name") for r in json.loads(json.dumps(__import__("yaml").safe_load((config.KNOWLEDGE / "rules.yaml").read_text(encoding="utf-8"))))}
    # 근거
    claim_kind, ev_type, grounded = Counter(), Counter(), Counter()
    for d in ds.values():
        for c in d.get("claims") or []:
            claim_kind[c["kind"]] += 1
            types = {e["type"] for e in c["evidence"]}
            for t in types:
                ev_type[t] += 1
            grounded["근거 있음" if types & set(GROUNDED) else "미확인"] += 1
    # 키 (필드의 의미 유형)
    key_ds = defaultdict(set)
    for i, d in ds.items():
        for f in (d.get("schema") or {}).get("fields") or []:
            if f.get("semantic_type"):
                key_ds[f["semantic_type"]].add(i)
    keys = sorted(({"id": k["id"], "name": k.get("name"), "type": k.get("type"), "datasets": len(key_ds.get(k["id"], ()))}
                   for k in ix.keys.values()), key=lambda x: -x["datasets"])
    # 데이터별 표
    rows = []
    for i, d in ds.items():
        cov = d.get("coverage") or {}
        rows.append({"id": i, "title": d["title"], "agency": (d.get("agency") or {}).get("name"), "sector": d["sector"].split("/")[0],
                     "tier": d["tier"], "channel": d.get("channel"), "kind": d.get("kind"), "rows": _rows(d),
                     "spatial": cov.get("spatial"), "unit": cov.get("admin_unit"), "lag": _lag(d),
                     "keys": sorted({f["semantic_type"] for f in (d.get("schema") or {}).get("fields") or [] if f.get("semantic_type")}),
                     "fields": len((d.get("schema") or {}).get("fields") or []), "edges": deg.get(i, 0),
                     "rate": best.get(i), "claims": sum(1 for c in d.get("claims") or [] if any(e["type"] in GROUNDED for e in c["evidence"]))})
    ver = [r for r in rows if r["tier"] == "verified"]
    sec = Counter(r["sector"] for r in ver)
    sec_c = Counter(r["sector"] for r in rows if r["tier"] == "candidate")
    sec_e = Counter(r["sector"] for r in ver if r["edges"])
    # 라운드·확대 차수
    t = json.loads((config.KNOWLEDGE / "targets.json").read_text(encoding="utf-8"))
    rounds = defaultdict(Counter)
    for x in t:
        rounds[x["round"]][x["status"]] += 1
    waves = {}
    for w in ("wave2", "wave3", "wave4", "wave4r", "wave5"):
        f = config.KNOWLEDGE / "expansion" / w / "queue.parquet"
        if f.exists():
            import pandas as pd
            q = pd.read_parquet(f, columns=["final_decision"])
            waves[w] = {"units": len(q), **{k: int(v) for k, v in q["final_decision"].value_counts().items()}}
    cat_n = len(ix.catalog) if ix.catalog is not None else 96110
    return {
        "knowledge_version": __import__("pds.strategy.plan", fromlist=["_commit"])._commit(),
        "totals": {"catalog": cat_n, "verified": len(ver), "candidate": sum(1 for r in rows if r["tier"] == "candidate"),
                   "edges": len(edges), "measured": sum(1 for e in edges if (e.get("verified") or {}).get("match_rate") is not None),
                   "claims": sum(claim_kind.values()), "keys": len(ix.keys), "code_lists": len(ix.codes), "contexts": len(ix.contexts),
                   "recipes": len(ix.recipes), "mappings": len(ix.mappings), "rules": len(rules),
                   "datasets_with_edge": sum(1 for r in ver if r["edges"])},
        "rounds": {k: dict(v) for k, v in sorted(rounds.items())}, "waves": waves,
        "sectors": [{"sector": s, "verified": n, "candidate": sec_c.get(s, 0), "with_edge": sec_e.get(s, 0)} for s, n in sec.most_common()],
        "channels": dict(Counter(("외부 사이트" if r["channel"] == "external" else ("파일" if r["kind"] in ("file", "FILE", "STD") else "포털 API")) for r in ver)),
        "edges": {"by_rel": dict(Counter(e["rel"] for e in edges)), "by_rule": dict(Counter((e.get("on") or {}).get("transform") or "같은 키" for e in edges if e["rel"] != "related_to")),
                  "rate": dict(rate_b), "hubs": [{"id": h, "name": HUBS[h], "edges": n} for h, n in hub_n.most_common()],
                  "via_mapping": sum(1 for e in edges if (e.get("on") or {}).get("via_mapping"))},
        "rules": rules,
        "claims": {"by_kind": dict(claim_kind.most_common()), "by_evidence": dict(ev_type.most_common()), "grounded": dict(grounded)},
        "keys": keys,
        "contexts": [{"id": c["id"], "name": c["name"], "dimension": c.get("dimension"), "question": c.get("question"),
                      "members": len(c.get("members") or []), "recipe": bool(c.get("recipe"))} for c in (ix.contexts.values() if isinstance(ix.contexts, dict) else ix.contexts)],
        "mappings": [{"id": m["id"], "rate": m.get("match_rate")} for m in ix.mappings.values()],
        "gaps": [{"name": g["name"], "status": g.get("status"), "reason": g.get("reason")} for g in __import__("pds.schema.store", fromlist=["load"]).load("gap")],
        "coverage": {
            "spatial": dict(Counter(r["spatial"] or "미상" for r in ver).most_common(8)),
            "unit": dict(Counter((r["unit"] or "미상").split("(")[0] for r in ver).most_common(8)),
            "fresh": dict(Counter(_bucket(r["lag"], [(1, "하루 이내"), (7, "1주 이내"), (31, "한 달 이내"), (365, "1년 이내"), (10**6, "1년 넘음")], "관찰 전") for r in ver)),
            "rows": dict(Counter(_bucket(r["rows"], [(999, "1천 미만"), (9999, "1만 미만"), (99999, "10만 미만"), (999999, "100만 미만"), (10**12, "100만 이상")], "미상") for r in ver)),
        },
        "datasets": rows,
        "sites": json.loads((config.KNOWLEDGE / "expansion" / "site_coverage.json").read_text(encoding="utf-8"))
        if (config.KNOWLEDGE / "expansion" / "site_coverage.json").exists() else None,
        "examples": {"dataset": _yaml_example("datasets/식품건강/15154916.yaml", 70), "edge": _edge_example(edges),
                     "rule": _yaml_example("rules.yaml", 24), "context": _yaml_example("contexts/commercial-district.yaml", 30)},
    }


def build() -> dict:
    from pds.strategy.plan import jsonable
    return jsonable(_build(sindex.get().stamp))
