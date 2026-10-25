"""7차 확대 — 포털에서 확인 가능한 데이터 전수 (python -m pds.expand.wave7).

6차까지는 부문 검토 판정(keep·move·defer)을 받은 단위만 골랐다. 7차는 판정 없이 나머지를 모두 검증한다.
  대상  포털 파일(FILE·STD) · 포털 API(REST) — 활용신청으로 받는다
        링크형(API_LINK·FILE_LINK) 중 키 보유·검증 또는 키 불필요 사이트
        이전에 실패(failed)·대기(pending)였던 것 중 위와 같은 조건 — 다시 시도
  제외  키 미보유·승인 대기 사이트 링크 (키가 생기면 다시 고른다)
등급: 부문 검토 판정이 있으면 6차와 같은 규칙(가족판·3순위·보조), 판정이 없으면 '전수' — 플래너가 보조처럼 낮춰 쓴다.
출력: logs/wave7_targets.json (round "10", 링크형은 "external") → sync4 register 로 knowledge/targets.json에 붙인다.
"""
from __future__ import annotations

import json
import sys
from collections import Counter

import pandas as pd

from pds import config
from pds.expand.wave6 import _decisions

ROUND = "10"
PORTAL = ("REST", "FILE", "STD")
LINK = ("API_LINK", "FILE_LINK")
OK_KEYS = ("보유·검증", "키 불필요")


def build() -> list[dict]:
    P = config.PROCESSED
    cat = pd.read_parquet(P / "catalog.parquet", columns=["id", "title", "agency_name", "url", "usage_count"])
    sc = pd.read_parquet(P / "score.parquet", columns=["id", "api_kind_label", "prelim_score"])
    cls = pd.read_parquet(P / "class.parquet", columns=["id", "sector", "subsector", "subsector_name"])
    st = {t["id"]: t["status"] for t in json.loads((config.KNOWLEDGE / "targets.json").read_text(encoding="utf-8"))}
    cov = json.loads((config.KNOWLEDGE / "expansion" / "site_coverage.json").read_text(encoding="utf-8"))
    ok_hosts = {x["host"] for x in cov["sites"] if x["key"] in OK_KEYS}
    links = pd.read_parquet(config.KNOWLEDGE / "expansion" / "site_links.parquet", columns=["id", "host"]).drop_duplicates("id")

    d = cat.merge(sc, on="id").merge(cls, on="id", how="left").merge(links, on="id", how="left")
    d = d.merge(_decisions()[["id", "decision", "priority", "rep", "wave", "reason"]], on="id", how="left")
    d["prev"] = d["id"].map(st)
    d = d[d["prev"].isna() | d["prev"].isin(["failed", "pending"])]
    d = d[d["api_kind_label"].isin(PORTAL) | (d["api_kind_label"].isin(LINK) & d["host"].isin(ok_hosts))]
    keep = d["decision"].isin(["keep", "move"])
    pr = d["priority"].fillna(3)
    d["grade"] = "전수"
    d.loc[keep & (pr <= 2) & ~d["rep"].fillna(False).astype(bool), "grade"] = "가족판"
    d.loc[keep & (pr <= 2) & d["rep"].fillna(False).astype(bool), "grade"] = ""  # 대표인데 아직 못 한 것 — 등급 없음(핵심)
    d.loc[keep & (pr >= 3), "grade"] = "3순위"
    d.loc[d["decision"].eq("defer"), "grade"] = "보조"
    d = d.sort_values("prelim_score", ascending=False)
    out = []
    for r in d.itertuples():
        kind = r.api_kind_label
        note = f"wave7 · 등급:{r.grade}" if r.grade else "wave7"
        if isinstance(r.decision, str):
            note += f" · {r.wave} 판정 {r.decision}"
        if isinstance(r.prev, str):
            note += f" · 재시도(이전 {r.prev})"
        out.append({"id": r.id, "title": r.title, "agency": r.agency_name, "sector": r.sector, "subsector": r.subsector or "misc",
                    "subsector_name": r.subsector_name if isinstance(r.subsector_name, str) else "", "kind": kind,
                    "prelim_score": round(float(r.prelim_score), 3), "usage": int(r.usage_count or 0), "url": r.url,
                    "round": "external" if kind in LINK else ROUND,
                    "why": (r.reason if isinstance(r.reason, str) else "")[:200], "status": "pending", "note": note,
                    "retry": isinstance(r.prev, str)})
    return out


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    t = build()
    (config.ROOT / "logs" / "wave7_targets.json").write_text(json.dumps(t, ensure_ascii=False, indent=1), encoding="utf-8")
    print(len(t))
    for k, v in sorted(Counter((x["kind"], x["retry"], (x["note"].split("등급:")[1].split(" ")[0] if "등급:" in x["note"] else "핵심")) for x in t).items()):
        print(k, v)


if __name__ == "__main__":
    main()
