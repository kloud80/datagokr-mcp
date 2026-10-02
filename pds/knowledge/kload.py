"""지식 엔티티 → Postgres (KNOWLEDGE-SPEC §5). 검증(validate) 통과한 것만 적재하고, 테이블은 통째로 교체한다(멱등).

pds_k_* 테이블은 knowledge/*.yaml의 파생물이다. catalog 층(9.6만)은 기존 load-db의 pds_catalog_dataset이고,
pds_k_catalog_tier 뷰가 두 층을 잇는다. 임베딩은 DB 밖(적용 메모 1).
"""
from __future__ import annotations

import json
import subprocess

import pandas as pd

from pds import config, db
from pds.schema import GROUNDED
from pds.schema import store
from pds.schema.validate import run as validate

TABLES = ["pds_k_dataset", "pds_k_claim", "pds_k_edge", "pds_k_key", "pds_k_mapping", "pds_k_code", "pds_k_code_value",
          "pds_k_context", "pds_k_recipe"]


def _j(x) -> str:
    """Postgres json은 NaN·Infinity를 받지 않는다 — 셀 통계의 무한대 값(예: max=inf)은 null로."""
    from pds.strategy.plan import jsonable
    return json.dumps(jsonable(x), ensure_ascii=False, default=str)


def frames() -> dict[str, pd.DataFrame]:
    ds = [d for d, _ in store.iter_raw("dataset")]
    out = {
        "pds_k_dataset": pd.DataFrame([{"id": d["id"], "tier": d["tier"], "title": d["title"], "sector": d["sector"], "kind": d["kind"],
                                        "channel": d["channel"], "family": d.get("family"), "summary": d.get("summary_user"),
                                        "review": (d.get("review") or {}).get("summary"), "doc": _j(d)} for d in ds]),
        "pds_k_claim": pd.DataFrame([{"id": c["id"], "dataset_id": d["id"], "kind": c["kind"], "value": c["value"],
                                      "grounded": any(e["type"] in GROUNDED for e in c["evidence"]), "rank": c.get("rank"),
                                      "evidence": _j(c["evidence"])} for d in ds for c in d.get("claims") or []]),
        "pds_k_edge": pd.DataFrame([{"id": e["id"], "src": e["src"], "dst": e["dst"], "rel": e["rel"], "relationship": e.get("relationship"),
                                     "via_mapping": (e.get("on") or {}).get("via_mapping"), "transform": (e.get("on") or {}).get("transform"),
                                     "confidence": e.get("confidence"), "match_rate": (e.get("verified") or {}).get("match_rate"),
                                     "source": e.get("source"), "doc": _j(e)} for e in store.load("edge")]),
        "pds_k_key": pd.DataFrame([{"id": k["id"], "name": k["name"], "doc": _j(k)} for k in store.load("key")]),
        "pds_k_mapping": pd.DataFrame([{"id": m["id"], "left_key": m["left"]["key"], "right_key": m["right"]["key"],
                                        "match_rate": m["match_rate"], "rows": m["rows"], "doc": _j(m)} for m in store.load("mapping")]),
        "pds_k_context": pd.DataFrame([{"id": c["id"], "dimension": c["dimension"], "question": c.get("question"), "doc": _j(c)}
                                       for c in store.load("context")]),
        "pds_k_recipe": pd.DataFrame([{"id": r["id"], "context": r.get("context"), "status": r.get("status"), "doc": _j(r)}
                                      for r in store.load("recipe")], columns=["id", "context", "status", "doc"]),
    }
    codes, values = [], []
    for c in store.load("code"):
        codes.append({"id": c["id"], "name": c["name"], "completeness": c["completeness"], "key": c.get("key"), "rows": c["rows"],
                      "doc": _j({k: v for k, v in c.items() if k != "values"})})
        if c.get("values"):
            values += [{"code_list": c["id"], "code": v["code"], "name": v["name"], "valid": v.get("valid", True)} for v in c["values"]]
        elif c.get("file"):
            t = pd.read_parquet(config.KNOWLEDGE / c["file"])
            values += [{"code_list": c["id"], "code": str(a), "name": str(b), "valid": bool(v) if not isinstance(v, str) else v in ("True", "true")}
                       for a, b, v in zip(t["code"], t["name"], t["valid"] if "valid" in t else [True] * len(t))]
    out["pds_k_code"] = pd.DataFrame(codes)
    out["pds_k_code_value"] = pd.DataFrame(values).drop_duplicates(["code_list", "code"])
    return out


def load() -> dict:
    rep, _ = validate()
    if not rep.ok:
        raise RuntimeError(f"validate 오류 {len(rep.errors)}건 — 적재하지 않는다: {rep.errors[:3]}")
    fr = frames()
    commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=config.ROOT).stdout.strip()
    with db.connect() as conn:
        applied = db.migrate(conn)
        conn.execute("truncate " + ", ".join(TABLES))
        for t in TABLES:
            if len(fr[t]):
                db._copy(conn, t, fr[t])
        counts = {t: len(fr[t]) for t in TABLES}
        conn.execute("insert into pds_k_build (git_commit, counts) values (%s, %s)", (commit, _j(counts)))
        tiers = dict(conn.execute("select tier, count(*) from pds_k_catalog_tier group by tier").fetchall())
        conn.commit()
    return {"migrations": applied, "counts": counts, "catalog_tiers": tiers, "commit": commit}
