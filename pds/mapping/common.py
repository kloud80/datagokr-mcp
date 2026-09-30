"""코드 체계 매핑 공통 — 이름·주소 정규화, 단계별 매칭, 매핑 파일(yaml 헤더 + parquet) 쓰기. KNOWLEDGE-SPEC §3.3.

매칭 단계 (앞 단계에서 1:1로 정해진 것은 뒤 단계에 넘기지 않는다):
  1 name+road   정규화 이름 == 이고 도로명+건물번호 ==            confidence 1.0
  2 name+sgg    정규화 이름 == 이고 시군구 토큰 ==, 후보가 1개    confidence 0.9
  3 road+fuzzy  도로명+건물번호 == 인 곳 안에서 이름 유사도 ≥ 88     confidence 0.8
  4 coord       (선택) 좌표 50m 이내 + 이름 유사도 ≥ 80            confidence 0.7
시도명은 쓰지 않는다 — 개편(전남광주통합특별시·강원/전북특별자치도)으로 기관마다 표기가 다르다.
"""
from __future__ import annotations

import datetime as dt
import math
import re

import pandas as pd
from rapidfuzz import fuzz

from pds import config
from pds.schema import Mapping
from pds.schema import store

MAPDIR = config.KNOWLEDGE / "mappings"
SIDO_WORDS = re.compile(r"^(서울|부산|대구|인천|광주|대전|울산|세종|경기|강원|충청|충북|충남|전라|전북|전남|경상|경북|경남|제주)\S*")


def norm_name(s) -> str:
    s = str(s or "")
    s = re.sub(r"\(.*?\)|\[.*?\]", "", s)
    s = re.sub(r"(주식회사|\(주\)|㈜|의료법인|재단법인|사회복지법인|학교법인)", "", s)
    return re.sub(r"[\s·.\-_,]", "", s).lower()


def road_key(addr) -> str | None:
    """'서울특별시 송파구 송이로 42 (가락동)' → '송이로42'. 도로명(…로/길) + 건물번호(본번[-부번])."""
    a = re.sub(r"\(.*?\)", " ", str(addr or ""))
    m = re.search(r"([가-힣0-9·.]+(?:로|길))\s*(\d+(?:-\d+)?)", a)
    return f"{m.group(1)}{m.group(2)}" if m else None


def sgg_token(addr) -> str | None:
    """시도 다음 토큰(시·군·구). '경기도 수원시 장안구 …' → '수원시장안구'."""
    toks = str(addr or "").split()
    if toks and SIDO_WORDS.match(toks[0]):
        toks = toks[1:]
    out = []
    for t in toks[:2]:
        if re.search(r"(시|군|구)$", t):
            out.append(t)
        else:
            break
    return "".join(out) or None


def same_digits(a: str, b: str) -> bool:
    """이름 속 숫자(차수·단지·동 번호)가 모두 같아야 같은 대상 — '자양9차'≠'자양8차', '13단지'≠'3단지'."""
    return re.findall(r"\d+", a or "") == re.findall(r"\d+", b or "")


def _haversine(a, b) -> float:
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 6371000 * 2 * math.asin(math.sqrt(h))


def prepare(df: pd.DataFrame, id_col: str, name_col: str, addr_cols: list[str], lat: str | None = None, lon: str | None = None) -> pd.DataFrame:
    out = pd.DataFrame({"value": df[id_col].astype(str).str.strip(), "name": df[name_col].astype(str)})
    out["nname"] = out["name"].map(norm_name)
    addr = df[addr_cols[0]].astype(str)
    for c in addr_cols[1:]:
        addr = addr.where(addr.map(road_key).notna(), df[c].astype(str))
    out["addr"] = addr
    out["road"] = addr.map(road_key)
    out["sgg"] = df[addr_cols[-1]].astype(str).map(sgg_token).where(lambda s: s.notna(), addr.map(sgg_token))
    if lat and lon:
        out["lat"] = pd.to_numeric(df[lat], errors="coerce")
        out["lon"] = pd.to_numeric(df[lon], errors="coerce")
    return out.drop_duplicates("value")


def match(L: pd.DataFrame, R: pd.DataFrame, use_coord: bool = False, fuzzy_on: str = "road", fuzzy_min: int = 88) -> pd.DataFrame:
    """L·R = prepare() 결과. 반환: left_value, right_value, confidence, method (L 기준 1행, 못 찾으면 right_value 없음)."""
    done_l, done_r, rows = set(), set(), []

    def take(pairs: pd.DataFrame, conf: float, method: str):
        pairs = pairs[~pairs["value_l"].isin(done_l) & ~pairs["value_r"].isin(done_r)]
        # 1:1만 (양쪽 모두 한 번씩 나오는 쌍)
        pairs = pairs[~pairs["value_l"].duplicated(keep=False) & ~pairs["value_r"].duplicated(keep=False)]
        for a, b in zip(pairs["value_l"], pairs["value_r"]):
            rows.append({"left_value": a, "right_value": b, "confidence": conf, "method": method})
            done_l.add(a)
            done_r.add(b)

    l, r = L.add_suffix("_l"), R.add_suffix("_r")
    take(l.merge(r, left_on=["nname_l", "road_l"], right_on=["nname_r", "road_r"]).dropna(subset=["road_l"]), 1.0, "name+road")
    take(l.merge(r, left_on=["nname_l", "sgg_l"], right_on=["nname_r", "sgg_r"]).dropna(subset=["sgg_l"]), 0.9, "name+sgg")
    fl, fr = f"{fuzzy_on}_l", f"{fuzzy_on}_r"
    cand = l[~l["value_l"].isin(done_l)].dropna(subset=[fl]).merge(
        r[~r["value_r"].isin(done_r)].dropna(subset=[fr]), left_on=fl, right_on=fr)
    if len(cand):
        cand = cand.assign(score=[max(fuzz.ratio(a, b), fuzz.partial_ratio(a, b) if min(len(a), len(b)) >= 4 else 0)
                                  if same_digits(a, b) else 0 for a, b in zip(cand["nname_l"], cand["nname_r"])])
        cand = cand[cand["score"] >= fuzzy_min].sort_values("score", ascending=False)
        take(cand.drop_duplicates("value_l").drop_duplicates("value_r"), 0.8, f"{fuzzy_on}+fuzzy")
    if use_coord and "lat_l" in l and "lat_r" in r:
        rl = r[~r["value_r"].isin(done_r)].dropna(subset=["lat_r", "lon_r"])
        grid = {}
        for rec in rl.itertuples(index=False):
            grid.setdefault((round(rec.lat_r, 3), round(rec.lon_r, 3)), []).append(rec)
        got = []
        for rec in l[~l["value_l"].isin(done_l)].dropna(subset=["lat_l", "lon_l"]).itertuples(index=False):
            best = None
            for dy in (-0.001, 0, 0.001):
                for dx in (-0.001, 0, 0.001):
                    for c in grid.get((round(rec.lat_l + dy, 3), round(rec.lon_l + dx, 3)), []):
                        d = _haversine((rec.lat_l, rec.lon_l), (c.lat_r, c.lon_r))
                        s = fuzz.ratio(rec.nname_l, c.nname_r) if same_digits(rec.nname_l, c.nname_r) else 0
                        if d <= 50 and s >= 80 and (best is None or s > best[1]):
                            best = (c.value_r, s)
            if best:
                got.append({"value_l": rec.value_l, "value_r": best[0]})
        if got:
            take(pd.DataFrame(got), 0.7, "coord")
    out = pd.DataFrame(rows, columns=["left_value", "right_value", "confidence", "method"])
    missing = L.loc[~L["value"].isin(done_l), "value"]
    return pd.concat([out, pd.DataFrame({"left_value": missing, "right_value": None, "confidence": 0.0, "method": "unmatched"})],
                     ignore_index=True)


def write(mid: str, left: dict, right: dict, method: str, table: pd.DataFrame, unmatched_policy: str, sources: list[str],
          notes: str) -> dict:
    MAPDIR.mkdir(parents=True, exist_ok=True)
    table.to_parquet(MAPDIR / f"{mid}.parquet", index=False)
    lefts = table.groupby("left_value")["right_value"].apply(lambda s: s.notna().any())  # 한 left에 여러 행(묶음 매칭)도 1로
    rec = {"id": mid, "left": left, "right": right, "method": method, "built_at": dt.date.today().isoformat(),
           "rows": int(len(table)), "match_rate": round(float(lefts.mean()), 4), "unmatched_policy": unmatched_policy,
           "file": f"mappings/{mid}.parquet", "sources": sources,
           "notes": notes + " · 단계별: " + ", ".join(f"{k} {v:,}" for k, v in table["method"].value_counts().items())}
    Mapping.model_validate(rec)
    store.dump(rec, MAPDIR / f"{mid}.yaml", header=f"매핑 {mid} — KNOWLEDGE-SPEC §3.3. pds/mapping/ 스크립트가 생성 (손으로 고치지 않음)")
    return rec
