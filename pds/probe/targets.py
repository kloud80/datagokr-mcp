"""Phase 2 검증 대상 선정 — 세부 부문(front)마다 대표 데이터 1건, 점수순.

대표 선정: 같은 세부 부문 안에서 channel(portal 우선) → 형태(REST·STD > FILE > 외부 링크) → prelim_score → 활용 순.
라운드: round=1은 포털에서 바로 검증 가능한 상위 N건, 나머지는 round=2(포털) / external(외부 사이트 절차 필요).
출력: knowledge/targets.json — 사람이 사유를 덧붙여 확정하는 파일 (why는 세부 부문 value_source에서 시작)
"""
from __future__ import annotations

import json

import pandas as pd

from pds import config

KIND_RANK = {"REST": 0, "STD": 0, "SOAP": 1, "FILE": 2, "API_LINK": 3, "FILE_LINK": 4}


def select(round1: int = 80) -> list[dict]:
    p = config.PROCESSED
    d = (pd.read_parquet(p / "class.parquet").merge(pd.read_parquet(p / "catalog.parquet"), on="id")
         .merge(pd.read_parquet(p / "score.parquet"), on="id"))
    d = d[d["excluded_by"].isna() & d["subsector_depth"].eq("front")].copy()
    d["kind_rank"] = d["api_kind_label"].map(KIND_RANK).fillna(5)
    d = d.sort_values(["sector", "subsector", "kind_rank", "prelim_score", "usage_count"],
                      ascending=[True, True, True, False, False])
    rep = d.groupby(["sector", "subsector"], as_index=False).head(1)
    rep = rep.sort_values(["kind_rank", "prelim_score"], ascending=[True, False]).reset_index(drop=True)
    out, n1 = [], 0
    for r in rep.itertuples():
        external = r.api_kind_label in ("API_LINK", "FILE_LINK")
        rnd = "external" if external else ("1" if n1 < round1 else "2")
        n1 += rnd == "1"
        out.append({"id": r.id, "title": r.title, "agency": r.agency_name, "sector": r.sector, "subsector": r.subsector,
                    "subsector_name": r.subsector_name, "kind": r.api_kind_label, "prelim_score": round(float(r.prelim_score), 3),
                    "usage": int(r.usage_count or 0), "url": r.url, "round": rnd,
                    "why": next((v for v in (r.value_source, r.subsector_name) if isinstance(v, str)), "").strip(),
                    "status": "pending"})
    return out


def write(round1: int = 80) -> str:
    targets = select(round1)
    path = config.KNOWLEDGE / "targets.json"
    old = {t["id"]: t for t in json.loads(path.read_text(encoding="utf-8"))} if path.exists() else {}
    for t in targets:  # 사람이 고친 사유·상태는 보존
        if t["id"] in old:
            t.update({k: old[t["id"]][k] for k in ("why", "status", "note") if k in old[t["id"]]})
    path.write_text(json.dumps(targets, ensure_ascii=False, indent=1), encoding="utf-8")
    return str(path)
