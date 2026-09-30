"""변환 규칙 (KNOWLEDGE-SPEC §9-2) — Edge on.transform이 규칙 id로 참조하는 결정적 함수. 목록은 knowledge/rules.yaml.

규칙은 순수 함수(입력 → 출력)이고 테스트(tests/test_rules.py)가 있어야 한다. 코드 생성기(Phase 5)가 그대로 가져다 쓴다.
"""
from __future__ import annotations

import re

import pandas as pd

__all__ = ["pnu_from_rtms", "pnu_from_parts", "road_key", "sgg_from_bjd", "RULES"]


def pnu_from_parts(bjd_cd: str, land_cd: str | int, bonbun: str | int, bubun: str | int) -> str | None:
    """R-07 PNU 조립: 법정동코드(10) + 대장구분(1: 1=토지 2=임야) + 본번(4) + 부번(4) = 19자리."""
    try:
        b = str(bjd_cd).strip()
        lc = str(land_cd).strip() or "1"
        lc = {"0": "1", "1": "1", "2": "2"}.get(lc, lc)
        bon, bu = int(str(bonbun).strip() or 0), int(str(bubun).strip() or 0)
    except (TypeError, ValueError):
        return None
    if not re.fullmatch(r"\d{10}", b) or lc not in ("1", "2") or not (0 < bon < 10000) or not (0 <= bu < 10000):
        return None
    return f"{b}{lc}{bon:04d}{bu:04d}"


def pnu_from_rtms(df: pd.DataFrame) -> pd.Series:
    """R-07을 실거래(RTMS) 행에 적용: sggCd(5)+umdCd(5) · landCd · bonbun · bubun."""
    bjd = df["sggCd"].astype(str).str.zfill(5) + df["umdCd"].astype(str).str.zfill(5)
    return pd.Series([pnu_from_parts(b, l, bo, bu) for b, l, bo, bu in
                      zip(bjd, df.get("landCd", "1"), df["bonbun"], df["bubun"])], index=df.index)


def sgg_from_bjd(bjd_cd: str) -> str | None:
    """R-02 시군구코드 = 법정동코드 앞 5자리."""
    s = str(bjd_cd or "").strip()
    return s[:5] if re.fullmatch(r"\d{10}", s) else None


def road_key(addr: str) -> str | None:
    """R-11 도로명주소 → '도로명+건물번호' 비교 키 (시도·시군구 표기 차이를 무시)."""
    from pds.mapping.common import road_key as rk
    return rk(addr)


RULES = {"R-02": sgg_from_bjd, "R-07": pnu_from_parts, "R-07-rtms": pnu_from_rtms, "R-11": road_key}
