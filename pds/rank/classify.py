"""3축 분류: 부문(sector) · 기관(agency tier) · 행정단위(admin_unit).

- 부문: 1차는 BRM 분류체계(정책분야 - 정책영역) 그대로. 병합·분할은 Phase 1 대화에서 knowledge/sectors/로 확정.
- 기관 계층: 행정표준기관코드 앞자리 + 기관명 규칙.
- 행정단위: 제목·출력결과·요청변수의 단서어로 "가장 세밀한 공간 단위"를 규칙 추정. 근거 토큰과 신뢰도를 남기고
  애매한 건(unknown/low)은 이후 LLM 보정 대상.
"""
from __future__ import annotations

import re

import pandas as pd

# ---------------------------------------------------------------- 기관 계층

AGENCY_TIERS = ("중앙행정기관", "광역자치단체", "기초자치단체", "교육청", "공공기관", "기타")

_METRO_SUFFIX = re.compile(r"(특별시|광역시|특별자치시|특별자치도|통합특별시|도)$")


def agency_tier(code: str | None, name: str | None) -> str:
    code = code or ""
    name = (name or "").strip()
    head = code[:1]
    if "교육청" in name:
        return "교육청"
    if head == "1":
        return "중앙행정기관"
    if head in "3456" and head:
        # 광역: 기관명이 한 토큰이고 광역 접미사로 끝남 (예: 서울특별시, 경상북도, 전남광주통합특별시)
        first, *rest = name.split()
        if not rest and _METRO_SUFFIX.search(first):
            return "광역자치단체"
        return "기초자치단체"
    if head == "B":
        return "공공기관"
    if head == "9":
        return "중앙행정기관"  # 국회·선관위 등 헌법기관은 중앙에 포함
    return "기타"


def coverage_from_tier(tier: str) -> str:
    """기관 계층으로 본 데이터의 기본 공간 범위(포괄 범위, 세밀도와 별개)."""
    return {
        "중앙행정기관": "전국",
        "공공기관": "전국",
        "광역자치단체": "시도",
        "교육청": "시도",
        "기초자치단체": "시군구",
    }.get(tier, "미상")


# ---------------------------------------------------------------- 행정단위

ADMIN_UNITS = ("필지·건물", "개별(주소·좌표)", "읍면동", "시군구", "시도", "전국·비공간")

# 가장 세밀한 것부터 검사한다. (단위, 컬럼 토큰 패턴, 제목 패턴)
# 컬럼 패턴은 쉼표로 나눈 컬럼명 하나하나에 적용한다. 부분문자열로 전체를 훑으면
# '페이지번호'가 '지번'에, '지번주소'가 필지에 걸린다.
_ADMIN_RULES: list[tuple[str, re.Pattern, re.Pattern | None]] = [
    ("필지·건물",
     re.compile(r"^(PNU|필지.*|지번|본번|부번|대지위치|(토지|필지)고유번호|건물관리번호|단지코드|단지명|아파트명?|동호.*|.*(건축물|토지|임야)대장.*)$"),
     re.compile(r"필지|지적|토지대장|건축물대장|실거래|공시지가|공동주택가격|개별주택가격|토지이용")),
    ("개별(주소·좌표)",
     re.compile(r"위도|경도|좌표|주소|소재지|WGS84|GRS80|EPSG|\(지번\)"),
     None),
    ("읍면동",
     re.compile(r"읍면동|법정동|행정동|^동명$|^리명$|동코드"),
     re.compile(r"읍면동|행정동|법정동")),
    ("시군구",
     re.compile(r"시군구|^구군|자치구|^시군$|^시군명$|^지역코드$|시·군·구"),
     re.compile(r"시군구|시·군·구|자치구별|시군별")),
    ("시도",
     re.compile(r"^시도|시·도"),
     re.compile(r"시도별|시·도별")),
]


def _tokens(*texts: str | None) -> list[str]:
    out: list[str] = []
    for t in texts:
        if isinstance(t, str):
            out.extend(x.strip() for x in t.split(",") if x.strip())
    return out


def admin_unit(title: str | None, output_cols: str | None, request_vars: str | None,
               keywords: str | None) -> tuple[str, str, str]:
    """→ (admin_unit, confidence[high|medium|low], evidence)."""
    cols = _tokens(output_cols, request_vars)
    title_text = " ".join(x for x in (title, keywords) if isinstance(x, str))
    for unit, col_pat, title_pat in _ADMIN_RULES:
        for tok in cols:
            if col_pat.search(tok):
                return unit, "high", f"col:{tok}"
    for unit, col_pat, title_pat in _ADMIN_RULES:
        pat = title_pat or col_pat
        m = pat.search(title_text)
        if m:
            return unit, "medium", f"title:{m.group(0)}"
    if not cols:
        return "전국·비공간", "low", "no-columns"
    return "전국·비공간", "medium", "no-spatial-token"


def classify(df: pd.DataFrame) -> pd.DataFrame:
    out = pd.DataFrame({"id": df["id"]})
    # 부문 = BRM 정책영역에서 출발, sector_map.yaml로 재배치 (원래 BRM은 catalog.brm에 남는다)
    from pds.rank.exclude import assign_subsector, excluded_by, remap_sector
    base = pd.DataFrame({"id": df["id"].to_numpy(), "sector": df["brm"].to_numpy(),
                         "agency_name": df["agency_name"].to_numpy(), "title": df["title"].to_numpy(),
                         "list_type": df["list_type"].to_numpy()}, index=df.index)
    out["sector"], out["sector_rule"] = remap_sector(base)
    sub = assign_subsector(base.assign(sector=out["sector"]))
    for c in sub.columns:
        out[c] = sub[c]
    split = out["sector"].str.split(" - ", n=1, expand=True)
    out["sector_field"] = split[0]
    out["sector_area"] = split[1]
    out["agency_tier"] = [agency_tier(c, n) for c, n in zip(df["agency_code"], df["agency_name"])]
    out["coverage"] = out["agency_tier"].map(coverage_from_tier)
    au = [admin_unit(t, o, r, k) for t, o, r, k in
          zip(df["title"], df["output_cols"], df["request_vars"], df["keywords"])]
    out["admin_unit"] = [a[0] for a in au]
    out["admin_unit_conf"] = [a[1] for a in au]
    out["admin_unit_evidence"] = [a[2] for a in au]
    out["admin_unit_method"] = "rule"
    out["excluded_by"] = excluded_by(out.assign(agency_name=df["agency_name"].to_numpy(),
                                                title=df["title"].to_numpy(), list_type=df["list_type"].to_numpy(),
                                                output_cols=df["output_cols"].to_numpy(),
                                                request_vars=df["request_vars"].to_numpy(),
                                                brm=df["brm"].to_numpy()))
    return out
