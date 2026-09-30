"""공동주택 단지: K-apt 단지코드(kaptCode, 15057332 전수) ↔ 실거래 단지 일련번호(aptSeq, 15126468 최근 6개월 전국).

K-apt 목록엔 도로명주소가 없어 법정동코드(10자리)를 블록으로 쓴다. 실거래는 sggCd(5)+umdCd(5) = 법정동코드.
실거래 쪽 전수 단지 목록은 없다 → 최근 6개월 거래된 단지만 오른쪽에 있다 (거래 없는 단지는 미매칭이 정상).
"""
from __future__ import annotations

import re

import pandas as pd

from pds.mapping.common import MAPDIR, match, same_digits, write
from pds.probe.fullpull import load


BRAND = [("lh", "엘에이치"), ("sk", "에스케이"), ("gs", "지에스"), ("kcc", "케이씨씨"), ("ipark", "아이파크"), ("s클래스", "에스클래스"),
         ("e편한세상", "이편한세상"), ("the", "더"), ("xi", "자이"), ("sh", "에스에이치"), ("hillstate", "힐스테이트")]


def _nm(s: str, strip: tuple[str, ...] = ()) -> str:
    s = re.sub(r"\(.*?\)", "", str(s))
    s = re.sub(r"[\s·.\-_,]", "", s).lower()
    s = re.sub(r"(아파트|apt)$", "", s)
    for a, b in BRAND:
        s = s.replace(a, b)
    for w in strip:  # 앞에 붙은 동·시군구 이름 ('반여동왕자' → '왕자', '아산득산부영' → '득산부영')
        w = re.sub(r"(동|읍|면|리|시|군|구)$", "", w or "")
        if len(w) >= 2 and s.startswith(w) and len(s) > len(w) + 1:
            s = s[len(w):].lstrip("동읍면리")
    return s


def _contain(L: pd.DataFrame, R: pd.DataFrame, m: pd.DataFrame) -> pd.DataFrame:
    """같은 법정동 안에서 한쪽 이름이 다른 쪽에 들어 있고 그 후보가 유일할 때 (confidence 0.7)."""
    done_l, done_r = set(m.loc[m.right_value.notna(), "left_value"]), set(m.right_value.dropna())
    l = L[~L.value.isin(done_l)]
    r = R[~R.value.isin(done_r)]
    c = l.merge(r, on="sgg", suffixes=("_l", "_r"))
    c = c[[len(a) >= 2 and len(b) >= 2 and (a in b or b in a) and same_digits(a, b) for a, b in zip(c.nname_l, c.nname_r)]]
    c = c[~c.value_l.duplicated(keep=False) & ~c.value_r.duplicated(keep=False)]
    add = dict(zip(c.value_l, c.value_r))
    hit = m.left_value.isin(add) & m.right_value.isna()
    m.loc[hit, "right_value"] = m.loc[hit, "left_value"].map(add)
    m.loc[hit, "confidence"] = 0.7
    m.loc[hit, "method"] = "bjd+contain"
    return m


def build() -> dict:
    k = load("15057332", "total")
    t = load("15126468", "trades_6m")
    t["bjd"] = t["sggCd"].astype(str).str.zfill(5) + t["umdCd"].astype(str).str.zfill(5)
    apt = (t.groupby("aptSeq").agg(aptNm=("aptNm", "first"), bjd=("bjd", "first"), jibun=("jibun", "first"),
                                   deals=("aptNm", "size")).reset_index())
    strip = [(a, b) for a, b in zip(k["as3"].fillna(""), k["as2"].fillna(""))]
    L = pd.DataFrame({"value": k["kaptCode"].astype(str), "name": k["kaptName"],
                      "nname": [_nm(n, (d, g.split()[0] if g else "")) for n, (d, g) in zip(k["kaptName"], strip)],
                      "road": None, "sgg": k["bjdCode"].astype(str)})
    R = pd.DataFrame({"value": apt["aptSeq"].astype(str), "name": apt["aptNm"], "nname": apt["aptNm"].map(_nm),
                      "road": None, "sgg": apt["bjd"]})
    m = match(L, R, fuzzy_on="sgg", fuzzy_min=85)
    m = _contain(L, R, m)
    m["method"] = m["method"].replace({"name+sgg": "name+bjd", "sgg+fuzzy": "bjd+fuzzy"})
    right_cov = m["right_value"].notna().sum() / len(R)
    return write("apt_complex_cd__rtms_apt_seq", {"key": "apt_complex_cd", "system": "K-apt 단지코드 kaptCode (공동주택 단지 목록 15057332 전수)"},
                 {"key": "rtms_apt_seq", "system": "실거래 단지 일련번호 aptSeq (아파트 매매 실거래 상세 15126468, 최근 6개월 전국)"},
                 "composite", m, "keep_left", ["15057332", "15126468"],
                 f"K-apt {len(L):,}단지 · 실거래 단지 {len(R):,}개(6개월 {len(t):,}건). 실거래 쪽 기준 매칭 {right_cov:.1%} — "
                 "K-apt는 의무관리 단지만, 실거래는 소규모 단지·연립 포함이라 양쪽 모두 미매칭이 정상적으로 남는다")




# ─────────────────────────── 부동산원 단지고유번호 허브 (15106861 파일, 필지고유번호·단지명 3종)
def _reb() -> pd.DataFrame:
    import glob
    from pds import config
    f = sorted(glob.glob(str(config.ROOT / "probe" / "data" / "15106861" / "*.parquet")))[-1]
    d = pd.read_parquet(f)
    d["단지고유번호"] = d["단지고유번호"].astype(str).str.strip()
    d["필지고유번호"] = d["필지고유번호"].astype(str).str.strip()
    return d


def build_rtms_reb() -> dict:
    """실거래 aptSeq → PNU(R-07 조립) → 부동산원 단지. 같은 필지에 단지가 여럿이면 이름이 가장 가까운 것."""
    from rapidfuzz import fuzz
    from pds.rules import pnu_from_rtms
    t = load("15126468", "trades_6m")
    t["pnu"] = pnu_from_rtms(t)
    apt = t.dropna(subset=["pnu"]).groupby("aptSeq").agg(aptNm=("aptNm", "first"), pnu=("pnu", lambda s: s.mode().iloc[0])).reset_index()
    reb = _reb()
    names = reb.melt(id_vars=["단지고유번호", "필지고유번호"], value_vars=["단지명_공시가격", "단지명_건축물대장", "단지명_도로명주소"],
                     value_name="nm").dropna(subset=["nm"])
    c = apt.merge(names, left_on="pnu", right_on="필지고유번호")
    c["score"] = [fuzz.ratio(_nm(a), _nm(b)) for a, b in zip(c.aptNm, c.nm)]
    best = c.sort_values("score", ascending=False).drop_duplicates("aptSeq")
    n_on_pnu = c.groupby("aptSeq")["단지고유번호"].nunique()
    best["confidence"] = [1.0 if n_on_pnu[a] == 1 else (0.9 if s >= 80 else 0.6) for a, s in zip(best.aptSeq, best.score)]
    best["method"] = ["pnu" if n_on_pnu[a] == 1 else "pnu+name" for a in best.aptSeq]
    m = apt[["aptSeq"]].merge(best[["aptSeq", "단지고유번호", "confidence", "method"]], on="aptSeq", how="left")
    m = m.rename(columns={"aptSeq": "left_value", "단지고유번호": "right_value"})
    m["method"] = m["method"].fillna("unmatched")
    m["confidence"] = m["confidence"].fillna(0.0)
    return write("rtms_apt_seq__reb_complex_id", {"key": "rtms_apt_seq", "system": "실거래 aptSeq (15126468 최근 6개월 전국)"},
                 {"key": "reb_complex_id", "system": "부동산원 단지고유번호 (공동주택 단지 식별정보 15106861)"},
                 "exact", m, "keep_left", ["15126468", "15106861"],
                 f"실거래 단지 {len(apt):,} → PNU 조립(R-07) 후 부동산원 필지고유번호와 일치. 한 필지 여러 단지면 단지명 3종 중 가장 가까운 것")


def build_kapt_reb() -> dict:
    """K-apt kaptCode → 부동산원 단지 (법정동 + 단지명 3종)."""
    k = load("15057332", "total")
    reb = _reb()
    reb["bjd"] = reb["필지고유번호"].str[:10]
    rows = []
    for col in ("단지명_공시가격", "단지명_건축물대장", "단지명_도로명주소"):
        x = reb.dropna(subset=[col])
        rows.append(pd.DataFrame({"value": x["단지고유번호"], "name": x[col], "nname": x[col].map(_nm), "road": None, "sgg": x["bjd"]}))
    R = pd.concat(rows).drop_duplicates(["value", "nname"])
    strip = [(a, b) for a, b in zip(k["as3"].fillna(""), k["as2"].fillna(""))]
    L = pd.DataFrame({"value": k["kaptCode"].astype(str), "name": k["kaptName"],
                      "nname": [_nm(n, (d, g.split()[0] if g else "")) for n, (d, g) in zip(k["kaptName"], strip)],
                      "road": None, "sgg": k["bjdCode"].astype(str)})
    # 한 단지가 이름 3종으로 여러 행 → match의 1:1 규칙이 단지 단위로 동작하게 (value, nname) 쌍을 먼저 고른다
    m = _match_multi(L, R)
    return write("apt_complex_cd__reb_complex_id", {"key": "apt_complex_cd", "system": "K-apt kaptCode (15057332 전수)"},
                 {"key": "reb_complex_id", "system": "부동산원 단지고유번호 (15106861, 단지명 3종)"},
                 "name_address_match", m, "keep_left", ["15057332", "15106861"],
                 f"K-apt {len(L):,} · 부동산원 {reb['단지고유번호'].nunique():,}단지. 법정동 + 단지명(공시가격·건축물대장·도로명주소 표기)")


def _match_multi(L: pd.DataFrame, R: pd.DataFrame) -> pd.DataFrame:
    """R의 한 value가 이름 여러 개를 가질 때: 이름별 후보를 모두 보고 value 단위로 1:1."""
    from rapidfuzz import fuzz
    c = L.merge(R, on="sgg", suffixes=("_l", "_r"))
    c["score"] = [100 if a == b else (max(fuzz.ratio(a, b), fuzz.partial_ratio(a, b) if min(len(a), len(b)) >= 4 else 0)
                                      if same_digits(a, b) else 0) for a, b in zip(c.nname_l, c.nname_r)]
    c = c[c.score >= 85].sort_values("score", ascending=False).drop_duplicates(["value_l", "value_r"])
    out, used = [], set()
    for vl, g in c.groupby("value_l", sort=False):
        top = g.iloc[0]
        tie = (g.score == top.score).sum() > 1 and g[g.score == top.score].value_r.nunique() > 1
        if tie or top.value_r in used:
            continue
        used.add(top.value_r)
        out.append({"left_value": vl, "right_value": top.value_r, "confidence": 1.0 if top.score == 100 else 0.8,
                    "method": "name+bjd" if top.score == 100 else "bjd+fuzzy"})
    m = pd.DataFrame(out)
    miss = L.loc[~L.value.isin(set(m.left_value) if len(m) else set()), "value"]
    return pd.concat([m, pd.DataFrame({"left_value": miss, "right_value": None, "confidence": 0.0, "method": "unmatched"})],
                     ignore_index=True)


def compose_kapt_rtms() -> dict:
    """K-apt ↔ 실거래를 부동산원 경유로 보강: kapt→reb→(PNU로 이은) rtms. 이름 직접 매칭과 합친다."""
    base = build()
    d = pd.read_parquet(MAPDIR / "apt_complex_cd__rtms_apt_seq.parquet")
    kr = pd.read_parquet(MAPDIR / "apt_complex_cd__reb_complex_id.parquet").dropna(subset=["right_value"])
    rr = pd.read_parquet(MAPDIR / "rtms_apt_seq__reb_complex_id.parquet").dropna(subset=["right_value"])
    rr = rr[~rr.right_value.duplicated(keep=False)]  # 부동산원 단지 하나에 실거래 단지 하나일 때만
    via = kr.merge(rr, left_on="right_value", right_on="right_value", suffixes=("", "_r"))[["left_value", "left_value_r", "confidence", "confidence_r"]]
    via = via.rename(columns={"left_value_r": "rtms"})
    add = dict(zip(via.left_value, via.rtms))
    conf = dict(zip(via.left_value, via[["confidence", "confidence_r"]].min(axis=1)))
    taken = set(d.right_value.dropna())
    hit = d.right_value.isna() & d.left_value.map(lambda x: x in add and add[x] not in taken)
    d.loc[hit, "right_value"] = d.loc[hit, "left_value"].map(add)
    d.loc[hit, "confidence"] = d.loc[hit, "left_value"].map(conf) * 0.95
    d.loc[hit, "method"] = "via_reb"
    both = d[~hit & d.right_value.notna() & d.left_value.isin(add)]
    agree = (both.left_value.map(add) == both.right_value).mean() if len(both) else float("nan")
    return write("apt_complex_cd__rtms_apt_seq", base["left"], base["right"], "composite", d, "keep_left", base["sources"] + ["15106861"],
                 f"이름 매칭 + 부동산원 단지고유번호 경유(kapt→reb→PNU→aptSeq). 두 경로가 모두 답한 {len(both):,}곳의 일치율 {agree:.1%}")


if __name__ == "__main__":
    for fn in (build_rtms_reb, build_kapt_reb, compose_kapt_rtms):
        r = fn()
        print(r["id"], {k: r[k] for k in ("rows", "match_rate", "notes")})
