"""6차 확대 — 검증 2만 목표 (python -m pds.expand.wave6 [N_DEFER]). 새 부문 검토 없이 이미 내린 판정을 넓혀 쓴다.

순서
  ① 가족판   유지·이동 판정(우선순위 1·2) 단위의 나머지 구성원 — 대표 1건만 검증했던 같은 형식의 시군구판
  ② 3순위    우선순위 3 유지·이동과 그 가족판
  ③ 보조     부문 검토에서 미룸(defer) — 통계·보조 자료·한 시군 소규모 목록. 점수(prelim_score) 높은 순 N_DEFER건
등급은 메모(note)에 '등급:가족판|3순위|보조'로 남기고, gen_dataset이 facets.grade로 옮긴다 →
전략 플래너가 보조 등급을 낮춰 핵심 데이터를 밀어내지 않게 한다 (pds/strategy/plan.py GRADE_WEIGHT).
키를 새로 받지 않는다: 포털(파일·API) + 키 보유·불필요 사이트 링크만.
출력: logs/wave6_targets.json (round "8") → sync4 register 로 knowledge/targets.json에 붙인다.
"""
from __future__ import annotations

import json
import sys

import pandas as pd

from pds import config

WAVES = ("wave2", "wave3", "wave4", "wave4r", "wave5")
KINDS = ("REST", "SOAP", "STD", "FILE", "API_LINK", "FILE_LINK")


def _decisions() -> pd.DataFrame:
    rows = []
    for w in WAVES:
        q = pd.read_parquet(config.KNOWLEDGE / "expansion" / w / "queue.parquet")
        for r in q.itertuples():
            d = getattr(r, "final_decision", None)
            pr = getattr(r, "final_priority", None)
            for m in str(r.members).split(","):
                if m:
                    rows.append({"id": m, "decision": str(d), "priority": pr, "rep": m == r.id, "wave": w,
                                 "reason": str(getattr(r, "final_reason", "") or getattr(r, "reason", ""))})
    return pd.DataFrame(rows).drop_duplicates("id", keep="last")


def build(n_defer: int = 12000) -> list[dict]:
    P = config.PROCESSED
    cat = pd.read_parquet(P / "catalog.parquet", columns=["id", "title", "agency_name", "url", "usage_count"])
    sc = pd.read_parquet(P / "score.parquet", columns=["id", "api_kind_label", "prelim_score"])
    cls = pd.read_parquet(P / "class.parquet", columns=["id", "sector", "subsector", "subsector_name"])
    have = {t["id"] for t in json.loads((config.KNOWLEDGE / "targets.json").read_text(encoding="utf-8"))}
    known = {f.stem.split("_")[0].split(".")[0] for f in (config.KNOWLEDGE / "datasets").rglob("*.yaml")}
    cov = json.loads((config.KNOWLEDGE / "expansion" / "site_coverage.json").read_text(encoding="utf-8"))
    ok_hosts = {x["host"] for x in cov["sites"] if x["key"] in ("보유·검증", "키 불필요")}
    links = pd.read_parquet(config.KNOWLEDGE / "expansion" / "site_links.parquet", columns=["id", "host"]).drop_duplicates("id")

    d = _decisions().merge(cat, on="id").merge(sc, on="id").merge(cls, on="id", how="left").merge(links, on="id", how="left")
    d = d[~d["id"].isin(have | known) & d["api_kind_label"].isin(KINDS)]
    d = d[~d["api_kind_label"].isin(["API_LINK", "FILE_LINK"]) | d["host"].isin(ok_hosts)]
    keep = d["decision"].isin(["keep", "move"])
    pr = d["priority"].fillna(3)
    d.loc[keep & (pr <= 2) & ~d["rep"], "grade"] = "가족판"
    d.loc[keep & (pr >= 3), "grade"] = "3순위"
    d.loc[d["decision"].eq("defer"), "grade"] = "보조"
    d = d[d["grade"].notna()]
    order = {"가족판": 0, "3순위": 1, "보조": 2}
    d = d.assign(o=d["grade"].map(order)).sort_values(["o", "prelim_score"], ascending=[True, False])
    d = pd.concat([d[d["grade"] != "보조"], d[d["grade"] == "보조"].head(n_defer)])
    out = []
    for r in d.itertuples():
        kind = r.api_kind_label
        out.append({"id": r.id, "title": r.title, "agency": r.agency_name, "sector": r.sector, "subsector": r.subsector or "misc",
                    "subsector_name": r.subsector_name if isinstance(r.subsector_name, str) else "", "kind": kind,
                    "prelim_score": round(float(r.prelim_score), 3), "usage": int(r.usage_count or 0), "url": r.url,
                    "round": "external" if kind in ("API_LINK", "FILE_LINK") else "8",
                    "why": (r.reason or "")[:200], "status": "pending", "note": f"wave6 · 등급:{r.grade} · {r.wave} 판정 {r.decision}"})
    return out


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 12000
    t = build(n)
    (config.ROOT / "logs" / "wave6_targets.json").write_text(json.dumps(t, ensure_ascii=False, indent=1), encoding="utf-8")
    from collections import Counter
    print(len(t), Counter((x["note"].split("등급:")[1].split(" ")[0], x["kind"]) for x in t))


if __name__ == "__main__":
    main()
