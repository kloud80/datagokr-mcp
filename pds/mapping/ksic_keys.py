"""산업분류 조인 키 선언 — knowledge/keys/{ksic, ksic10, ksic9, industry_nm, sbiz_inds}.yaml (통계 분해 연구안 1단계).

KSIC 코드 열은 이름만으로 정하지 않는다. 검증 데이터의 실측 표본(probe/data)을 읽어 값이 KSIC 코드표에 있는지 재고,
차수(9·10·11차)도 값으로 가린다 — 같은 번호가 차수마다 다른 업종일 수 있어서 차수가 다른 열끼리는 바로 잇지 않고
매핑(ksic9__ksic10 · ksic10__ksic)을 거친다.
  일치율   칸을 , / + 로 나눈 낱말 중 9·10·11차 어느 코드표에든 있는 비율 (서로 다른 값 기준). RATE 이상이면 KSIC 열
  차수     그 차수에만 있는 코드 개수가 가장 많은 차수. 모두 0이면(공통 코드뿐) 11차
업종 이름 열(industry_nm)은 build_industry.FIELD_RX 그대로 — 값은 industry_nm__ksic 매핑으로 KSIC에 붙는다.
실행: python -m pds.mapping.ksic_keys  (그 뒤 gen-dataset → pds.edges.auto)
"""
from __future__ import annotations

import glob
import re
from collections import defaultdict

import pandas as pd

from pds import config
from pds.mapping.build_industry import FIELD_RX, _codes
from pds.schema import store

P = config.ROOT / "probe" / "data"
K = config.KNOWLEDGE / "keys"
RATE = 0.8
CAND = re.compile(r"^(산업분류코드|표준산업분류코드|KSIC_CD|ksic_cd|ksic|최종업종코드|indutype_cd|indutype_cd_info|indutyNo|업종코드|indutyCode|"
                  r"induty_code|INDUTY_CODE|INDUTY_CD|업종분류코드|indutyCd|rprsntvIndutyCode)$", re.I)
SBIZ = ["상권업종소분류코드"]
EXCLUDE = {"15064297": "무역보험공사 업종코드표 — ksure_industry_cd 키",
           "15136423": "상수도 요금 업종(용도) 번호 — 우연히 KSIC 중분류와 겹침"}


def _ksic9() -> set[str]:
    return set(pd.read_parquet(config.KNOWLEDGE / "mappings" / "ksic9__ksic10.parquet")["left_value"].astype(str))


def measure() -> list[dict]:
    """검증 데이터의 코드 열마다 일치율·차수."""
    k11, k10, k9 = set(_codes("ksic")["code"]), set(_codes("ksic10")["code"]), _ksic9()
    out = []
    for d, _ in store.iter_raw("dataset"):
        if d.get("tier") != "verified" or d["id"] in EXCLUDE:
            continue
        hit = [f["name"] for f in (d.get("schema") or {}).get("fields") or [] if CAND.match(f["name"])]
        files = sorted(glob.glob(str(P / d["id"] / "*.parquet"))) if hit else []
        if not files:
            continue
        df = pd.read_parquet(files[-1])
        for n in hit:
            if n not in df:
                continue
            tok = df[n].dropna().astype(str).str.split(r"\s*[,/+]\s*").explode().str.strip()
            tok = tok[tok != ""].str.replace(r"^[A-U](?=\d)", "", regex=True).str.replace(r"(\.0|_\d{1,2})$", "", regex=True)
            u = set(tok.unique())
            if not u:
                continue
            rate = sum(len(x) >= 2 and (x in k11 or x in k10 or x in k9) for x in u) / len(u)
            only = {"ksic": sum(x in k11 and x not in k10 for x in u),
                    "ksic10": sum(x in k10 and x not in k11 and x not in k9 for x in u),
                    "ksic9": sum(x in k9 and x not in k10 and x not in k11 for x in u)}
            key = max(only, key=lambda k: (only[k], k == "ksic")) if any(only.values()) else "ksic"
            out.append({"ds": d["id"], "field": n, "rate": round(rate, 3), "key": key, "only": only,
                        "multi": bool(tok.size > df[n].notna().sum())})
    return out


def _fields(rows: list[dict]) -> list[dict]:
    by = defaultdict(list)
    for r in rows:
        by[r["field"]].append(r["ds"])
    return [{"names": [n], "datasets": sorted(set(ds))} for n, ds in sorted(by.items())]


def write() -> dict:
    rows = [r for r in measure() if r["rate"] >= RATE]
    multi = sorted({r["ds"] for r in rows if r["multi"]})
    sbiz_ds = [d["id"] for d, _ in store.iter_raw("dataset") if d.get("tier") == "verified" and d["id"] == "15083033"]
    names = re.findall(r"[^|()^$]+", FIELD_RX.pattern)
    common = {"type": "natural", "scope": "global", "issuer": "국가데이터처 (한국표준산업분류)"}
    keys = [
        {"id": "ksic", "name": "한국표준산업분류 코드 (KSIC 11차, 2024.7 시행)", **common,
         "format": "대분류 A~U · 중분류 2 · 소분류 3 · 세분류 4 · 세세분류 5자리 (앞자리가 상위 분류). 'I56221'처럼 대분류 문자를 붙인 값은 떼고 읽는다",
         "pattern": r"^[A-U]?\d{2,5}$",
         "related_keys": [{"key": "ksic10", "relation": "maps_to", "note": "ksic10__ksic (국가데이터처 연계표 15159305)"},
                          {"key": "industry_nm", "relation": "maps_to", "note": "industry_nm__ksic — 업종 이름을 KSIC로"},
                          {"key": "sbiz_inds", "relation": "maps_to", "note": "sbiz_inds__ksic — 상가정보 실측 최빈"}],
         "fields": _fields([r for r in rows if r["key"] == "ksic"])},
        {"id": "ksic10", "name": "한국표준산업분류 코드 (KSIC 10차, 2017.7~2024.6)", **common, "format": "11차와 같은 자리 구조",
         "pattern": r"^[A-U]?\d{2,5}$",
         "related_keys": [{"key": "ksic", "relation": "maps_to", "note": "ksic10__ksic — 1:N이면 confidence 1/N"}],
         "fields": _fields([r for r in rows if r["key"] == "ksic10"])},
        {"id": "ksic9", "name": "한국표준산업분류 코드 (KSIC 9차, 2008.2~2017.6)", **common, "format": "11차와 같은 자리 구조",
         "pattern": r"^[A-U]?\d{2,5}$",
         "related_keys": [{"key": "ksic10", "relation": "maps_to", "note": "ksic9__ksic10 (국가데이터처 연계표 15159305)"}],
         "fields": _fields([r for r in rows if r["key"] == "ksic9"])},
        {"id": "industry_nm", "name": "업종·업태 이름 (인허가·공장등록·점포 현황)", "type": "natural", "scope": "global",
         "format": "자유 텍스트 — 일반음식점·식품제조가공업·'도금업(25922)'처럼 법령 업종·KSIC 항목명·코드 병기가 섞임",
         "related_keys": [{"key": "ksic", "relation": "maps_to", "note": "industry_nm__ksic"}],
         "fields": [{"names": names}]},
        {"id": "sbiz_inds", "name": "상권업종 소분류 코드 (소상공인시장진흥공단, 2023 개편 체계)", "type": "natural", "scope": "global",
         "issuer": "소상공인시장진흥공단", "format": "'I21001'처럼 영문 1 + 숫자 5", "pattern": r"^[A-Z]\d{5}$",
         "master_datasets": sbiz_ds,
         "related_keys": [{"key": "ksic", "relation": "maps_to", "note": "sbiz_inds__ksic"}],
         "fields": [{"names": SBIZ, "datasets": sbiz_ds}]},
    ]
    notes = {
        "ksic": f"검증 데이터 실측 표본으로 정한 열 (일치율 {RATE:.0%} 이상, 11차에만 있는 코드가 가장 많거나 공통 코드뿐) — pds/mapping/ksic_keys.py 생성. "
                f"한 칸에 여러 코드를 , / + 로 묶은 데이터 {len(multi)}건은 나눠서 잇는다 ({', '.join(multi)}). "
                "같은 코드끼리 바로 이으면 업종 단위 many_to_many — 업종별로 집계한 뒤 결합. 코드표 knowledge/codes/ksic.yaml",
        "ksic10": "값에 10차에만 있는 코드가 가장 많은 열 (상가정보 표준산업분류코드 등) — 11차 통계와는 ksic10__ksic로 잇는다. 코드표 knowledge/codes/ksic10.yaml",
        "ksic9": "값에 9차에만 있는 코드(예: 17201·33310·51463)가 가장 많은 열 — ksic9__ksic10 → ksic10__ksic 두 번 거친다",
        "industry_nm": "이름 그대로 데이터끼리 잇지 않는다(Edge 자동 생성에서 같은 키 연결 제외) — industry_nm__ksic로 KSIC에 붙인 뒤 업종 단위로 결합. "
                       "필드 이름은 pds/mapping/build_industry.FIELD_RX",
        "sbiz_inds": "2023 개편 체계만 (상가정보 15083033). 옛 체계('D05A03'·'S01B10', 15111532·15069540)는 다른 코드 — 이 키가 아니다",
    }
    for k in keys:
        k["notes"] = notes[k["id"]]
        k = {f: v for f, v in k.items() if v not in (None, [], {})}
        store.dump(k, K / f"{k['id']}.yaml", header=f"Key {k['id']} — 산업분류 조인 키 (pds/mapping/ksic_keys.py 생성, 손으로 고치지 않음)")
    return {k["id"]: sum(len(f.get("datasets") or []) for f in k["fields"]) for k in keys}


if __name__ == "__main__":
    print(write())
