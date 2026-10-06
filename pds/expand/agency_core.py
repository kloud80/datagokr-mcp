"""기관 분석이 찾은 '빠진 핵심 원장'(agencies/*.yaml core_missing)과 경기데이터드림 링크형을 검증 대상으로 (python -m pds.expand.agency_core).

출력: logs/wave7_targets.json (round "9", 링크형은 external) → sync4 register. 등급 없음(핵심) — 기관 분석이 핵심이라 판정했다.
경기데이터드림은 gg_sites 실측 기록이 있으므로 status를 바로 맞춘다 (성공 verified · 실패 failed).
"""
from __future__ import annotations

import json
import sys
from collections import Counter

import pandas as pd

from pds import config
from pds.schema import store

KINDS = ("REST", "SOAP", "STD", "FILE", "API_LINK", "FILE_LINK")
SITE_NAMES = {"data.gg.go.kr": "경기데이터드림 (경기도 자체 개방 포털)", "safetydata.go.kr": "재난안전데이터공유플랫폼 (샘플 다운로드)",
              "open.assembly.go.kr": "열린국회정보 (인증키)", "data.mafra.go.kr": "농림축산식품 공공데이터 포털",
              "lofin365.go.kr": "지방재정365 (인증키, 제목 유사도로 짝지음)", "foodsafetykorea": "식품안전나라 (sample 키)",
              "data.ex.co.kr": "한국도로공사 공공데이터 포털 (key=test)", "opendart": "OpenDART (인증키)",
              "culture.go.kr": "문화공공데이터광장 (API별 서비스키)", "jigu.go.kr": "택지정보시스템",
              "jejudatahub": "제주데이터허브 (상세 페이지 미리보기 — 원본·API는 projectKey)", "work24": "고용24 (서비스별 인증키)",
              "safemap": "생활안전지도 (인증키 승인 대기)", "apihub.kma": "기상청 API허브 (키 + API별 활용신청)"}


def build() -> list[dict]:
    P = config.PROCESSED
    cat = pd.read_parquet(P / "catalog.parquet", columns=["id", "title", "agency_name", "url", "usage_count"])
    sc = pd.read_parquet(P / "score.parquet", columns=["id", "api_kind_label", "prelim_score"])
    cls = pd.read_parquet(P / "class.parquet", columns=["id", "sector", "subsector", "subsector_name"])
    have = {t["id"] for t in json.loads((config.KNOWLEDGE / "targets.json").read_text(encoding="utf-8"))}
    known = {f.stem for f in (config.KNOWLEDGE / "datasets").rglob("*.yaml")}
    why = {}
    for a, _ in store.iter_raw("agency"):
        for i in a.get("core_missing") or []:
            why[i] = f"기관 분석 핵심 원장 — {a['name']}"
    links = pd.read_parquet(config.KNOWLEDGE / "expansion" / "site_links.parquet", columns=["id", "host"]).drop_duplicates("id")
    for i, h in zip(links["id"], links["host"].fillna("")):  # 기관 자체 개방 사이트 — 사이트별 검증기(pds/probe/*_sites·*_files)로 확인한 것
        site = next((n for k, n in SITE_NAMES.items() if k in h), None)
        if site:
            why.setdefault(i, site)
    d = (pd.DataFrame({"id": list(why), "why": list(why.values())}).merge(cat, on="id").merge(sc, on="id")
         .merge(cls, on="id", how="left"))
    d = d[~d["id"].isin(have | known) & d["api_kind_label"].isin(KINDS)]
    out = []
    for r in d.itertuples():
        kind = r.api_kind_label
        run = config.ROOT / "probe" / "runs" / f"{r.id}.json"
        status = "pending"
        if any(n == r.why for n in SITE_NAMES.values()) and run.exists():
            status = "verified" if json.loads(run.read_text(encoding="utf-8")).get("ok_ops") else "failed"
        out.append({"id": r.id, "title": r.title, "agency": r.agency_name, "sector": r.sector if isinstance(r.sector, str) else "미분류", "subsector": r.subsector if isinstance(r.subsector, str) and r.subsector else "misc",
                    "subsector_name": r.subsector_name if isinstance(r.subsector_name, str) else "", "kind": kind,
                    "prelim_score": round(float(r.prelim_score), 3), "usage": int(r.usage_count or 0), "url": r.url,
                    "round": "external" if kind in ("API_LINK", "FILE_LINK") else "9", "why": r.why, "status": status,
                    "note": "wave7 · 기관 분석"})
    return out


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    t = build()
    (config.ROOT / "logs" / "wave7_targets.json").write_text(json.dumps(t, ensure_ascii=False, indent=1), encoding="utf-8")
    print(len(t), Counter((x["round"], x["kind"], x["status"]) for x in t).most_common())
