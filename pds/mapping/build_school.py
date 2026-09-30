"""학교: 표준데이터 학교ID(B000…, 15021148) ↔ 나이스 교육청코드+학교코드(15122331 schoolInfo 전수).

Phase 2에서 두 체계의 값이 하나도 겹치지 않음을 확인(0/12,011)했다 → 이름+주소로 잇는다.
나이스 쪽 값은 'ATPT_OFCDC_SC_CODE:SD_SCHUL_CODE' (급식·시간표 API가 두 값을 함께 요구하므로).
"""
from __future__ import annotations

import glob

import pandas as pd

from pds import config
from pds.mapping.common import match, prepare, write


def build() -> dict:
    P = config.ROOT / "probe" / "data"
    std = pd.read_parquet(sorted(glob.glob(str(P / "15021148" / "*.parquet")))[-1])
    neis = pd.read_parquet(sorted(glob.glob(str(P / "15122331" / "schoolInfo_*.parquet")))[-1])
    neis["neis_id"] = neis["ATPT_OFCDC_SC_CODE"].str.strip() + ":" + neis["SD_SCHUL_CODE"].str.strip()
    L = prepare(std, "학교ID", "학교명", ["소재지도로명주소", "소재지지번주소"])
    R = prepare(neis, "neis_id", "SCHUL_NM", ["ORG_RDNMA"])
    t = match(L, R)
    # 운영상태 — 폐교·휴교는 나이스에 없을 수 있다 (미매칭 설명용)
    t = t.merge(std[["학교ID", "운영상태", "학교급구분"]].rename(columns={"학교ID": "left_value", "운영상태": "left_status",
                                                                  "학교급구분": "left_kind"}), on="left_value", how="left")
    un = t[t["right_value"].isna()]
    return write("school_cd__neis_school_cd", {"key": "school_cd", "system": "표준데이터 학교ID (전국초중등학교위치표준데이터 15021148)"},
                 {"key": "neis_school_cd", "system": "나이스 ATPT_OFCDC_SC_CODE:SD_SCHUL_CODE (schoolInfo 전수)"},
                 "composite", t, "keep_left", ["15021148", "15122331"],
                 f"표준 {len(L):,}교 · 나이스 {len(R):,}교. 미매칭 {len(un):,} — 운영상태 {un['left_status'].value_counts().to_dict()}")


if __name__ == "__main__":
    r = build()
    print({k: r[k] for k in ("rows", "match_rate", "notes")})
