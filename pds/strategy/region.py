"""지역 범위 판단 — 목표 문장의 지역 vs 데이터가 다루는 지역.

부산광역시가 낸 '상권 점포이력'은 주제가 맞아도 성수동(서울) 목표에는 쓸 수 없다. 검색 점수는 주제만 보므로
플래너가 고르기 전에 여기서 걸러 not_recommended(지역 불일치)로 보낸다.

  목표 지역: 법정동 코드표(bjd_cd, 현행)에서 시도·시군구·읍면동 이름을 찾는다. 성수동 → 성수동1가·2가 → 서울특별시.
             이름이 여러 시도에 걸치면(중구·신흥동…) 시도가 함께 나오지 않는 한 판단에 쓰지 않는다.
  데이터 지역: 제공기관 이름 또는 제목 머리('부산광역시_…')가 시도로 시작하면 그 시도. 아니면 전국(None).
"""
from __future__ import annotations

import re
from functools import lru_cache

import pandas as pd

from pds import config

SIDO_ALIAS = {
    "서울특별시": ["서울"], "부산광역시": ["부산"], "대구광역시": ["대구"], "인천광역시": ["인천"], "광주광역시": ["광주"],
    "대전광역시": ["대전"], "울산광역시": ["울산"], "세종특별자치시": ["세종"], "경기도": ["경기"],
    "강원특별자치도": ["강원도", "강원"], "충청북도": ["충북"], "충청남도": ["충남"], "전북특별자치도": ["전라북도", "전북"],
    "전라남도": ["전남"], "경상북도": ["경북"], "경상남도": ["경남"], "제주특별자치도": ["제주도", "제주"],
}
_ALIAS = sorted(((a, s) for s, al in SIDO_ALIAS.items() for a in [s, *al]), key=lambda x: -len(x[0]))
PLACE = re.compile(r"[가-힣]{1,8}?(?:시|군|구|동|읍|면|가|리)(?=$|[^가-힣]|[은는이가을를의에도와과로])")


@lru_cache
def _places() -> dict[str, set[str]]:
    """지명(마지막 토막, 숫자·'가' 떼고) → 시도 집합."""
    t = pd.read_parquet(config.KNOWLEDGE / "codes" / "bjd_cd.parquet")
    t = t[t["valid"]]
    out: dict[str, set[str]] = {}
    for name in t["name"]:
        parts = name.split()
        sido = parts[0]
        for p in parts[1:]:
            for k in {p, re.sub(r"\d*가$", "", p), re.sub(r"\d+(동)$", r"\1", p)}:
                if len(k) >= 2:
                    out.setdefault(k, set()).add(sido)
    return out


def _sido_of(text: str) -> str | None:
    for a, s in _ALIAS:
        if text.startswith(a):
            return s
    return None


def goal_regions(goal: str) -> dict:
    """{'sido': {시도…}, 'names': [근거 지명…]} — 지역 언급이 없으면 sido가 빈 집합."""
    sidos, names = set(), []
    for a, s in _ALIAS:
        if re.search(rf"(?<![가-힣]){a}", goal):
            sidos.add(s)
            names.append(a)
    places = _places()
    for m in PLACE.finditer(goal):
        w = m.group(0)
        hit = places.get(w) or places.get(re.sub(r"\d*가$", "", w))
        if not hit:
            continue
        if len(hit) == 1:
            sidos |= hit
            names.append(w)
        elif hit & sidos:  # 여러 시도에 있는 이름(중구 등)은 함께 적힌 시도로만 좁힌다
            names.append(w)
    return {"sido": sidos, "names": names}


def dataset_region(d: dict) -> str | None:
    """데이터가 다루는 시도 (전국이면 None)."""
    agency = (d.get("agency") or {}).get("name") or d.get("agency_name") or ""
    title = d.get("title") or ""
    return _sido_of(agency) or _sido_of(title.split("_")[0])


def mismatch(d: dict, region: dict) -> str | None:
    """지역이 어긋나면 사유 문장, 아니면 None."""
    if not region["sido"]:
        return None
    r = dataset_region(d)
    if r and r not in region["sido"]:
        return f"지역 불일치 — 데이터는 {r}, 목표는 {'·'.join(region['names'])} ({'·'.join(sorted(region['sido']))})"
    return None
