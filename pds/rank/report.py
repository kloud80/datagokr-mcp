"""Phase 1 HTML 리포트 (BUILD-PLAN §1.4) → reports/phase1_ranking.html

단일 HTML, 외부 의존 없음. 데이터는 JSON → gzip → base64로 페이지에 넣고 브라우저의 DecompressionStream으로 푼다.
- 핵심 컬럼은 96k 전체 (검색·히트맵·트리 집계용).
- 메타 원문(설명·요청변수·출력결과·보유근거·한계)은 상세 대상만: API·STD 전부 + 정책영역별 상위 FILE.
  전부 넣으면 설명만 76MB라 단일 파일로 못 연다.
"""
from __future__ import annotations

import base64
import gzip
import json
from datetime import datetime
from pathlib import Path

import pandas as pd

from pds import config
from pds.rank.score import WEIGHTS

TEMPLATE = Path(__file__).parent / "templates" / "phase1_ranking.html"
FILE_DETAIL_PER_AREA = 60
TRUNC = {"description": 400, "output_cols": 700, "request_vars": 400, "legal_basis": 200,
         "data_limit": 300, "keywords": 150, "spatial_scope": 80, "temporal_scope": 80, "notes": 200}

EXTERNAL_KINDS = {"API_LINK", "FILE_LINK"}


def _load() -> pd.DataFrame:
    p = config.PROCESSED
    return (pd.read_parquet(p / "catalog.parquet")
            .merge(pd.read_parquet(p / "class.parquet"), on="id")
            .merge(pd.read_parquet(p / "score.parquet"), on="id")
            .query("excluded_by.isna()", engine="python"))  # 프로젝트 제외 규칙 (knowledge/sectors/exclusions.yaml)


def _codes(s: pd.Series, order: list[str] | None = None) -> tuple[list[str], list[int]]:
    values = order or sorted(s.dropna().unique().tolist())
    idx = {v: i for i, v in enumerate(values)}
    return values, [idx.get(v, -1) if isinstance(v, str) else -1 for v in s]


def _num(s: pd.Series, nd: int | None = None) -> list:
    out = []
    for v in s:
        if v is None or pd.isna(v):
            out.append(None)
        else:
            out.append(round(float(v), nd) if nd is not None else int(v))
    return out


def _txt(v, n: int | None = None):
    if not isinstance(v, str) or not v.strip():
        return None
    v = v.strip()
    return v if n is None or len(v) <= n else v[:n] + "…"


def build_payload(df: pd.DataFrame) -> dict:
    df = df.sort_values("rank_overall").reset_index(drop=True)
    from pds.rank.classify import ADMIN_UNITS, AGENCY_TIERS
    dicts, cols = {}, {}

    for name, col, order in [
        ("agency", "agency_name", None), ("field", "sector_field", None), ("area", "sector", None),
        ("tier", "agency_tier", list(AGENCY_TIERS)), ("kind", "api_kind_label",
                                                       ["REST", "API_LINK", "SOAP", "STD", "FILE", "FILE_LINK"]),
        ("unit", "admin_unit", list(ADMIN_UNITS)), ("cycle", "update_cycle", None),
    ]:
        dicts[name], cols[name] = _codes(df[col], order)
    # 세부 부문: "정책영역|slug|이름|깊이" 한 문자열로 코드화 (정책영역마다 slug가 겹칠 수 있음)
    sub_key = [f"{a}|{s}|{n}|{d}" if isinstance(s, str) else None
               for a, s, n, d in zip(df["sector"], df["subsector"], df["subsector_name"], df["subsector_depth"])]
    dicts["subsector"], cols["subsector"] = _codes(pd.Series(sub_key, index=df.index))

    cols.update({
        "id": df["id"].tolist(),
        "title": df["title"].tolist(),
        "unit_conf": [{"high": 2, "medium": 1, "low": 0}[c] for c in df["admin_unit_conf"]],
        "score": _num(df["prelim_score"], 4),
        "s_usage": _num(df["s_usage"], 3), "s_designation": _num(df["s_designation"], 2),
        "s_api_kind": _num(df["s_api_kind"], 2), "s_freshness": _num(df["s_freshness"], 3),
        "s_meta_fill": _num(df["s_meta_fill"], 3),
        "s_granularity": _num(df["s_granularity"], 2), "s_linkable": _num(df["s_linkable"], 2),
        "s_coverage": _num(df["s_coverage"], 2),
        "s_novelty": _num(df["s_novelty"], 2),
        "imputed": [v if isinstance(v, str) else "" for v in df["imputed"]],
        "usage": _num(df["usage_count"]), "views": _num(df["view_count"]),
        "nk": [1 if v else 0 for v in df["national_key"]],
        "std": [1 if v else 0 for v in df["standard"]],
        "modified": [v.isoformat() if hasattr(v, "isoformat") and not pd.isna(v) else None
                     for v in df["modified_at"]],
        "rank": _num(df["rank_overall"]), "rank_sector": _num(df["rank_in_sector"]),
    })

    # 상세 대상
    is_file = df["api_kind_label"].isin(["FILE", "FILE_LINK"])
    file_top = df[is_file].groupby("sector", group_keys=False).head(FILE_DETAIL_PER_AREA).index
    detail_idx = df.index[~is_file].union(file_top)
    detail = {}
    for i in detail_idx:
        r = df.loc[i]
        detail[r["id"]] = {
            "desc": _txt(r["description"], TRUNC["description"]),
            "out": _txt(r["output_cols"], TRUNC["output_cols"]),
            "req": _txt(r["request_vars"], TRUNC["request_vars"]),
            "law": _txt(r["legal_basis"], TRUNC["legal_basis"]),
            "limit": _txt(r["data_limit"], TRUNC["data_limit"]),
            "kw": _txt(r["keywords"], TRUNC["keywords"]),
            "space": _txt(r["spatial_scope"], TRUNC["spatial_scope"]),
            "time": _txt(r["temporal_scope"], TRUNC["temporal_scope"]),
            "notes": _txt(r["notes"], TRUNC["notes"]),
            "fmt": _txt(r["formats"], 60),
            "rows": None if pd.isna(r["row_count"]) else int(r["row_count"]),
            "reg": r["registered_at"].isoformat() if hasattr(r["registered_at"], "isoformat") and not pd.isna(r["registered_at"]) else None,
            "next": r["next_reg_date"].isoformat() if hasattr(r["next_reg_date"], "isoformat") and not pd.isna(r["next_reg_date"]) else None,
            "appr": [r["approval_dev"], r["approval_ops"]] if isinstance(r["approval_dev"], str) else None,
            "traffic": None if pd.isna(r["daily_traffic_dev"]) else int(r["daily_traffic_dev"]),
            "unit_ev": r["admin_unit_evidence"],
            "shape_ev": [r["granularity_ev"], r["linkable_ev"], r["coverage_ev"]],
            "provide": _txt(r["provide_form"], 60),
        }

    return {
        "meta": {
            "snapshot": str(df["snapshot_date"].iloc[0]),
            "generated": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "weights": WEIGHTS,
            "total": len(df),
            "detail_count": len(detail),
            "file_detail_per_area": FILE_DETAIL_PER_AREA,
            "external_kinds": sorted(EXTERNAL_KINDS),
            "top100_available": bool(df["top100_available"].iloc[0]),
        },
        "dict": dicts,
        "cols": cols,
        "detail": detail,
    }


def render(out: Path | None = None) -> Path:
    payload = build_payload(_load())
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=str).encode("utf-8")
    b64 = base64.b64encode(gzip.compress(raw, 9)).decode("ascii")
    html = TEMPLATE.read_text(encoding="utf-8").replace("__PAYLOAD_B64__", b64)
    out = out or (config.REPORTS / "phase1_ranking.html")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    return out
