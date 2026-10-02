"""2차 확대 확정분 → 검증 대상(knowledge/targets.json, round "4") (python -m pds.expand.targets).

대상: 부문 검토 final_decision ∈ {keep, move} + absorb-std가 가리키는 전국 표준데이터(아직 지식 체계에 없으면).
자치단체 가족은 대표 1건만 검증한다 (같은 형식이라 하나가 되면 나머지도 된다 — members에 남겨 둔다).
이후: python -m pds probe-specs 4 → probe-apply 4 (포털 로그인 세션) → probe-run 4 → gen-dataset
"""
from __future__ import annotations

import json
import sys

import pandas as pd

from pds import config
from pds.expand.wave2 import OUT

PRIORITY_MAX = 3


def build() -> list[dict]:
    q = pd.read_parquet(OUT / "queue.parquet")
    P = config.PROCESSED
    sc = pd.read_parquet(P / "score.parquet", columns=["id", "api_kind_label", "prelim_score"])
    cat = pd.read_parquet(P / "catalog.parquet", columns=["id", "title", "agency_name", "url", "usage_count"])
    cls = pd.read_parquet(P / "class.parquet", columns=["id", "sector", "subsector", "subsector_name"])
    pick = q[q["final_decision"].isin(["keep", "move"]) & (q["final_priority"].fillna(3) <= PRIORITY_MAX)].copy()
    std_ids = set(q.loc[q["final_decision"].eq("absorb"), "std_match"].dropna())
    known = {f.stem.split("_")[0].split(".")[0] for f in (config.KNOWLEDGE / "datasets").rglob("*.yaml")}
    std_ids -= known | set(pick["id"])
    rows = pick[["id", "final_priority", "final_reason", "final_move_to", "final_subsector"]].rename(
        columns={"final_priority": "priority", "final_reason": "why", "final_move_to": "move_to", "final_subsector": "sub"})
    rows = pd.concat([rows, pd.DataFrame({"id": sorted(std_ids), "priority": 2, "why": "자치단체 파일들을 대신하는 전국 표준데이터",
                                          "move_to": "", "sub": ""})], ignore_index=True)
    d = rows.merge(cat, on="id").merge(sc, on="id").merge(cls, on="id")
    out = []
    for r in d.sort_values(["priority", "prelim_score"], ascending=[True, False]).itertuples():
        kind = r.api_kind_label if r.api_kind_label in ("REST", "SOAP", "STD", "FILE", "API_LINK", "FILE_LINK") else "FILE"
        sub = r.sub if isinstance(r.sub, str) and r.sub and not r.sub.startswith("new:") else (r.subsector or "misc")
        note = f"wave2 p{int(r.priority)}" + (f" · 이동 제안 → {r.move_to}" if isinstance(r.move_to, str) and r.move_to else "") + \
               (f" · 새 세부 부문 {r.sub[4:]}" if isinstance(r.sub, str) and r.sub.startswith("new:") else "")
        out.append({"id": r.id, "title": r.title, "agency": r.agency_name, "sector": r.sector, "subsector": sub,  # 이동 제안은 note에 — 부문 재배치는 사람이 확정
                    "subsector_name": r.subsector_name if sub == r.subsector else sub, "kind": kind,
                    "prelim_score": round(float(r.prelim_score), 3), "usage": int(r.usage_count or 0), "url": r.url,
                    "round": "external" if kind in ("API_LINK", "FILE_LINK") else "4", "why": str(r.why), "status": "pending",
                    "note": note})
    return out


def write() -> dict:
    path = config.KNOWLEDGE / "targets.json"
    cur = json.loads(path.read_text(encoding="utf-8"))
    have = {t["id"] for t in cur}
    new = [t for t in build() if t["id"] not in have]
    path.write_text(json.dumps(cur + new, ensure_ascii=False, indent=1), encoding="utf-8")
    from collections import Counter
    return {"added": len(new), "by_kind": dict(Counter(t["kind"] for t in new)), "by_round": dict(Counter(t["round"] for t in new))}


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    print(write())
