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


def _vworld() -> tuple[str, str]:
    """브이월드 키: VWORLD_API_KEY(+VWORLD_DOMAIN) 환경변수 → secrets/keys.json['vworld']."""
    import json
    import os
    from pds import config
    if os.getenv("VWORLD_API_KEY"):
        return os.environ["VWORLD_API_KEY"], os.getenv("VWORLD_DOMAIN", "")
    v = json.loads((config.ROOT / "secrets" / "keys.json").read_text(encoding="utf-8"))["vworld"]
    return v["key"], v.get("domain", "bv")


def coord_to_pnu(lat: float, lon: float, client=None) -> str | None:
    """R-12 좌표(WGS84) → 그 점을 포함하는 필지의 PNU (브이월드 연속지적도 LP_PA_CBND_BUBUN, POINT 필터)."""
    import httpx
    key, domain = _vworld()
    c = client or httpx.Client(timeout=30)
    r = c.get("https://api.vworld.kr/req/data", params={"service": "data", "request": "GetFeature", "data": "LP_PA_CBND_BUBUN",
              "geomFilter": f"POINT({lon} {lat})", "format": "json", "size": 1, "geometry": "false", "key": key, "domain": domain})
    try:
        feats = ((r.json()["response"].get("result") or {}).get("featureCollection") or {}).get("features") or []
    except (ValueError, KeyError):
        return None
    return feats[0]["properties"].get("pnu") if feats else None


def address_to_coord(address: str, client=None) -> tuple[float, float] | None:
    """R-13 주소 → 좌표 (브이월드 지오코더: 도로명 먼저, 실패하면 지번). 이어서 R-12로 PNU."""
    import httpx
    key, _ = _vworld()
    c = client or httpx.Client(timeout=30)
    for typ in ("road", "parcel"):
        r = c.get("https://api.vworld.kr/req/address", params={"service": "address", "request": "getcoord", "crs": "epsg:4326",
                  "address": address, "format": "json", "type": typ, "key": key})
        try:
            res = r.json()["response"]
        except (ValueError, KeyError):
            continue
        if res.get("status") == "OK":
            pt = res["result"]["point"]
            return float(pt["y"]), float(pt["x"])
    return None


_BJD_NAMES: dict | None = None


def admin_name_to_code(name: str, parent: str | None = None) -> str | None:
    """R-14 행정구역 이름 → 코드 (법정동 코드표 knowledge/codes/bjd_cd.parquet의 현행 코드). '종로구'처럼 모호하면 parent(시도 이름)로 좁힌다.
    시군구는 5자리, 시도는 2자리, 읍면동은 10자리로 돌려준다."""
    global _BJD_NAMES
    if _BJD_NAMES is None:
        from pds import config
        t = pd.read_parquet(config.KNOWLEDGE / "codes" / "bjd_cd.parquet")
        t = t[t["valid"].astype(str).isin(["True", "true", "1"])]
        _BJD_NAMES = {}
        for code, full in zip(t["code"], t["name"]):
            toks = full.split()
            level = 2 if code[2:] == "0" * 8 else 5 if code[5:] == "0" * 5 else 10
            _BJD_NAMES.setdefault(toks[-1], []).append((code[:level], full))
    n = str(name or "").strip().split()[-1] if name else ""
    hits = _BJD_NAMES.get(n, []) if n else []
    if parent:
        hits = [h for h in hits if str(parent).strip()[:2] in h[1]] or hits
    codes = {h[0] for h in hits}
    return codes.pop() if len(codes) == 1 else None


RULES = {"R-02": sgg_from_bjd, "R-07": pnu_from_parts, "R-07-rtms": pnu_from_rtms, "R-11": road_key,
         "R-12": coord_to_pnu, "R-13": address_to_coord, "R-14": admin_name_to_code}


# ─────────────────────────── 느슨한 조인 (정렬 조인) — 공통 단위로 내린 뒤 집계해 잇는다 (R-20 ~ R-23)
LEVEL_LEN = {"bjd": 10, "emd": 8, "sgg": 5, "sido": 2}


def admin_rollup(code: str, level: str) -> str | None:
    """R-20·R-21 — PNU(19)·법정동(10)·읍면동(8)·시군구(5) 코드를 앞자리로 상위 단위로 (PNU 앞 10자리 = 법정동)."""
    c = re.sub(r"\D", "", str(code or ""))
    n = LEVEL_LEN.get(level)
    if not n or len(c) < n:
        return None
    return c[:n]


def time_floor(value, grain: str) -> str | None:
    """R-22 — 날짜·시각 값을 공통 시점으로 내림: day YYYYMMDD · month YYYYMM · quarter YYYYQn · year YYYY."""
    d = re.sub(r"\D", "", str(value or ""))
    if len(d) < 4:
        return None
    if grain == "year":
        return d[:4]
    if len(d) == 5 and d[4] in "1234":  # 연도+분기 코드(서울 STDR_YYQU_CD 20243 = 2024년 3분기)
        return f"{d[:4]}Q{d[4]}" if grain == "quarter" else None
    if len(d) < 6:
        return None
    if grain == "month":
        return d[:6]
    if grain == "quarter":
        return f"{d[:4]}Q{(int(d[4:6]) - 1) // 3 + 1}"
    return d[:8] if len(d) >= 8 else None


def category_prefix(code: str, digits: int) -> str | None:
    """R-23 — 분류 코드(KSIC·HS 등)를 앞자리로 상위 분류에 맞춘다 (KSIC 대분류는 알파벳 1자, 중분류 2자리 …)."""
    c = str(code or "").strip()
    return c[:digits] if len(c) >= digits else None


RULES.update({"R-20": admin_rollup, "R-21": admin_rollup, "R-22": time_floor, "R-23": category_prefix})
