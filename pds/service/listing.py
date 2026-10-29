"""데이터셋 목록 — 부처·분야·데이터 유형·지역 범위로 거르고 쪽 단위로 전부 받는다 (MCP list_datasets · GET /api/datasets).

검색(search_datasets)은 상위 몇 건만 주지만, 목록은 조건에 맞는 것 전체의 총수(total)와 쪽(offset·limit)을 준다.
purpose(목적·키워드)를 주면 검색 순위로 넓게(최대 3,000건) 모은 뒤 같은 조건으로 거른다.
facets는 거른 결과의 부처·분야·유형별 건수 — 부처 이름을 정확히 모를 때 먼저 facets만 보고 고른다.
"""
from __future__ import annotations

from collections import Counter

TYPES = {  # data_type → 내부 kind
    "api": {"API", "EXTERNAL_API"}, "file": {"FILE", "EXTERNAL_FILE"}, "std": {"STD"},
    "API": {"API"}, "FILE": {"FILE"}, "EXTERNAL_API": {"EXTERNAL_API"}, "EXTERNAL_FILE": {"EXTERNAL_FILE"}, "STD": {"STD"},
}
POOL = 3000


def _norm(s: str | None) -> str:
    return (s or "").replace(" ", "").lower()


def _row_known(d: dict, region) -> dict:
    v = d.get("verification") or {}
    return {"id": d["id"], "title": d["title"], "tier": d["tier"], "agency": (d.get("agency") or {}).get("name"), "sector": d.get("sector"),
            "data_type": d.get("kind"), "channel": d.get("channel"), "region": region or "전국",
            "fields": len((d.get("schema") or {}).get("fields") or []), "rows": v.get("rows"), "probed_at": v.get("probed_at")}


def _row_catalog(r: dict, region) -> dict:
    return {"id": r["id"], "title": r["title"], "tier": "catalog", "agency": r.get("agency_name"), "sector": r.get("sector"),
            "data_type": r.get("list_type"), "api_type": r.get("api_type"), "region": region or "전국", "portal_url": r.get("url")}


def list_datasets(agency: str | None = None, sector: str | None = None, data_type: str = "any", tier: str = "verified",
                  purpose: str | None = None, channel: str = "any", scope: str = "any", offset: int = 0, limit: int = 50,
                  facets: bool = True) -> dict:
    from pds.service import index as sindex
    from pds.strategy import region as rgn
    ix = sindex.get()
    kinds = TYPES.get(data_type) if data_type not in ("any", "", None) else None
    if data_type not in ("any", "", None) and kinds is None:
        raise ValueError(f"data_type은 any·api·file·std 또는 {sorted(k for k in TYPES if k.isupper())} 중 하나")
    ag, sc = _norm(agency), _norm(sector)

    def region_ok(reg) -> bool:
        return scope == "any" or (scope == "national") == (reg is None)

    rows: list[dict] = []
    if tier == "catalog":
        cat = ix.catalog
        if purpose:
            src = [r for r, _ in ix.search_catalog(purpose, POOL)]
        else:
            src = cat.sort_values(["agency_name", "title"]).to_dict("records")
        for r in src:
            if r["id"] in ix.datasets:  # 지식 체계에 들어온 것은 verified·candidate 층으로 본다
                continue
            if ag and ag not in _norm(r.get("agency_name")) or sc and sc not in _norm(str(r.get("sector") or "")):
                continue
            if kinds and r.get("list_type") not in kinds:
                continue
            reg = rgn.dataset_region({"agency_name": r.get("agency_name"), "title": r.get("title")})
            if region_ok(reg):
                rows.append(_row_catalog(r, reg))
    else:
        tiers = ("verified", "candidate") if tier == "any" else (tier,)
        if purpose:
            src = [d for d, _ in ix.search_datasets(purpose, POOL, tiers=tiers)]
        else:
            src = sorted((d for d in ix.datasets.values() if d["tier"] in tiers),
                         key=lambda d: ((d.get("agency") or {}).get("name") or "", d["title"]))
        for d in src:
            if ag and ag not in _norm((d.get("agency") or {}).get("name")) or sc and sc not in _norm(d.get("sector")):
                continue
            if kinds and d.get("kind") not in kinds or channel != "any" and d.get("channel") != channel:
                continue
            reg = rgn.dataset_region(d)
            if region_ok(reg):
                rows.append(_row_known(d, reg))
    out = {"total": len(rows), "offset": offset, "limit": limit, "items": rows[offset:offset + limit]}
    out["next_offset"] = offset + limit if offset + limit < len(rows) else None
    if purpose:
        out["note"] = f"purpose로 검색 순위 상위 {POOL:,}건 안에서 거른 결과 — 순서는 관련도순"
    if facets:
        out["facets"] = {k: dict(Counter(str(r.get(f) or "") for r in rows).most_common(30))
                         for k, f in (("agency", "agency"), ("sector", "sector"), ("data_type", "data_type"))}
    return out
