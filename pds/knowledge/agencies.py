"""기관 엔티티 생성 — 포털 제공기관 1,115곳마다 knowledge/agencies/{기관코드}.yaml (python -m pds.knowledge.agencies).

기계가 채우는 것: 이름·유형·상위기관(행정표준 기관코드 instt_cd 비고)·등급·집계(counts)·자체 개방 사이트.
보존하는 것(분석·사람): systems · core_missing · native_keys · relations · gaps · analyzed_by/at · note.
등급: A 중앙·공공·교육 중 목록 50건 이상 또는 검증 20건 이상인 곳의 점수 상위 150 · B 광역 · C 기초 · D 그 밖.
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter

import pandas as pd

from pds import config
from pds.schema import store

PRESERVE = ("systems", "core_missing", "native_keys", "relations", "gaps", "analyzed_by", "analyzed_at", "note")
OUT = config.KNOWLEDGE / "agencies"
A_MAX = 150  # 정밀 분석 대상 (2026-10-05 사용자 결정)


def _type(note: str, name: str) -> tuple[str, str | None]:
    m = re.search(r"상위 (\w{7})", note or "")
    parent = m.group(1) if m and m.group(1) != "0000000" else None
    n = note or ""
    if re.fullmatch(r"\S+(특별시|광역시|특별자치시|특별자치도|도|통합특별시)", name):  # 비고가 빈 기관도 이름으로
        return "metro", parent
    if re.fullmatch(r"\S+(특별시|광역시|특별자치시|특별자치도|도|통합특별시) \S+(시|군|구)( \S+구)?", name):
        return "local", parent
    if "중앙행정기관" in n or "국가행정기관" in n:
        t = "central"
    elif "광역자치단체" in n:
        t = "metro"
    elif "기초자치단체" in n or "자치행정" in n:
        t = "local"
    elif "교육" in n or "교육청" in name:
        t = "education"
    elif "산하기관" in n or "공공기관" in n or any(k in name for k in ("공사", "공단", "진흥원", "재단", "연구원", "은행", "기금")):
        t = "public"
    else:
        t = "other"
    return t, parent


def build() -> list[dict]:
    from pds.service import index
    ix = index.get()
    cat = pd.read_parquet(config.PROCESSED / "catalog.parquet", columns=["id", "agency_code", "agency_name"])
    codes = pd.read_parquet(config.KNOWLEDGE / "codes" / "instt_cd.parquet")
    note = {str(k): (v if isinstance(v, str) else "") for k, v in zip(codes["code"], codes["note"])}
    links = pd.read_parquet(config.KNOWLEDGE / "expansion" / "site_links.parquet", columns=["id", "host"])
    host_of = dict(zip(links["id"], links["host"]))
    ag_of = dict(zip(cat["id"], cat["agency_code"].astype(str)))

    ver, core = Counter(), Counter()
    for d in ix.datasets.values():
        if d["tier"] != "verified":
            continue
        a = ag_of.get(d["id"])
        ver[a] += 1
        if not (d.get("facets") or {}).get("grade"):
            core[a] += 1
    within, across = Counter(), Counter()
    for e in ix.edges:
        if e["rel"] not in ("joinable", "lookup"):
            continue
        a, b = ag_of.get(e["src"]), ag_of.get(e["dst"])
        if a and a == b:
            within[a] += 1
        else:
            for x in (a, b):
                if x:
                    across[x] += 1
    out = []
    for code, g in cat.groupby(cat["agency_code"].astype(str)):
        name = str(g["agency_name"].dropna().iloc[0]) if g["agency_name"].notna().any() else code
        t, parent = _type(note.get(code, ""), name)
        n = len(g)
        if t == "metro":
            tier = "B"
        elif t == "local":
            tier = "C"
        elif n >= 50 or ver[code] >= 20:
            tier = "A"
        else:
            tier = "D"
        hosts = Counter(host_of[i] for i in g["id"] if i in host_of and isinstance(host_of[i], str))
        portal = next((h for h, c in hosts.most_common(1) if c >= max(20, n * 0.3)), None)
        out.append({"id": code, "name": name, "type": t, "parent": parent, "tier": tier,
                    "counts": {"catalog": n, "verified": ver[code], "core": core[code], "edges_within": within[code], "edges_across": across[code]},
                    **({"external_portal": portal} if portal else {})})
    # A등급은 정밀 분석 상위 A_MAX곳만 — 목록 규모 + 검증 + 다른 기관과의 조인으로 순위
    cand = sorted((r for r in out if r["tier"] == "A"),
                  key=lambda r: -(r["counts"]["catalog"] + 3 * r["counts"]["verified"] + r["counts"]["edges_across"] / 5))
    for k, r in enumerate(cand):
        if k >= A_MAX:
            r["tier"] = "D"
    return out


def write() -> dict:
    OUT.mkdir(parents=True, exist_ok=True)
    old = {a["id"]: a for a, _ in store.iter_raw("agency")} if any(OUT.glob("*.yaml")) else {}
    recs = build()
    for r in recs:
        prev = old.get(r["id"]) or {}
        for k in PRESERVE:
            if prev.get(k) not in (None, [], ""):
                r[k] = prev[k]
        store.dump(r, OUT / f"{r['id']}.yaml",
                   header=f"Agency {r['id']} {r['name']} — 집계는 pds.knowledge.agencies가 다시 쓴다. systems·relations 등 분석 필드는 보존.")
    c = Counter(r["tier"] for r in recs)
    return {"agencies": len(recs), "tiers": dict(sorted(c.items())), "types": dict(Counter(r["type"] for r in recs))}


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(write(), ensure_ascii=False))
