"""Edge 실측 프로브 (KNOWLEDGE-SPEC §3.4, §9-3) — 선언된 조인이 실제 값으로 이어지는지 매칭률을 잰다.

측정 (edge마다 probe/joins/{edge id}.json):
  코드표 목적지(법정동 파일 등)  왼쪽 값이 코드표 전수에 있는 비율 (R-02는 시군구 5자리, R-14는 이름→코드 성공률)
  같은 키                        오른쪽 전수 원장(data/master)이 있으면 포함률, 없으면 양쪽 표본 겹침
  매핑 경유                      왼쪽 값이 매핑표에서 짝을 찾는 비율
  공간 R-12·R-13                 표본 좌표·주소 몇 건을 브이월드로 실제 변환한 성공률 (호출 수 제한)
  lookup                         제공 데이터의 해당 필드에 값이 채워진 비율 + 호출 쪽 필수 파라미터와 이름 대응
결과는 edges.yaml의 verified {by: measured, run, match_rate, at}로 들어간다 (pds/edges/auto.py 재생성 때 보존).
"""
from __future__ import annotations

import datetime as dt
import glob
import json
import re
import time

import httpx
import pandas as pd

from pds import config
from pds.schema import store

OUT = config.ROOT / "probe" / "joins"
P = config.ROOT / "probe" / "data"
M = config.DATA / "master"
TODAY = dt.date.today().isoformat()
SAMPLE = 200
SPATIAL_SAMPLE = 6
# 전수 원장 (key → parquet, 컬럼)
MASTERS = {"ykiho": ("15001698/hosp_basis", "ykiho"), "hpid": ("15000736/hsptl_mdcnc", "hpid"),
           "apt_complex_cd": ("15057332/total", "kaptCode"), "rtms_apt_seq": ("15126468/trades_6m", "aptSeq"),
           "ltc_instt_cd": ("15059029/ltc_instt", "longTermAdminSym"), "tago_node_id": ("15098534/sttn_no_list", "nodeid"),
           "busstop_sttn_id": ("15142032/bus_stop", "sttn_id"), "instt_cd": ("15077870/stan_org_cd", "org_cd")}


def _values(dsid: str, cols: list[str]) -> pd.DataFrame:
    frames = []
    for f in glob.glob(str(P / dsid / "*.parquet")):
        try:
            d = pd.read_parquet(f)
        except Exception:  # noqa: BLE001
            continue
        have = [c for c in cols if c in d.columns]
        if have:
            frames.append(d[have].astype(str))
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=cols)


def _norm(v: str) -> str:
    v = str(v).strip()
    return re.sub(r"[-\s]", "", v) if re.fullmatch(r"[\d\-\s]+", v) else v


def _clean(s: pd.Series) -> pd.Series:
    s = s.astype(str).str.strip()
    return s[~s.isin(["", "nan", "None", "-", "null"])]


def _bjd_codes() -> set[str]:
    t = pd.read_parquet(config.KNOWLEDGE / "codes" / "bjd_cd.parquet")
    return set(t["code"].astype(str))


def measure(e: dict, keys: dict) -> dict | None:
    on = e.get("on") or {}
    left, right = on.get("left") or [], on.get("right") or []
    rec = {"edge": e["id"], "src": e["src"], "dst": e["dst"], "rel": e["rel"], "at": TODAY}
    if e["rel"] == "related_to":
        return None
    lv = _values(e["src"], left)
    if e["rel"] == "lookup":
        rv = _values(e["dst"], right)
        col = next((c for c in right if c in rv.columns), None)
        if col is None:
            return {**rec, "method": "lookup", "match_rate": None, "detail": f"제공 데이터 표본에 {right} 컬럼 없음"}
        filled = _clean(rv[col])
        return {**rec, "method": "lookup(제공 필드 채움률)", "match_rate": round(len(filled) / max(1, len(rv)), 4),
                "n": int(len(rv)), "examples": filled.head(3).tolist()}
    if not len(lv.columns):
        return {**rec, "method": "none", "match_rate": None, "detail": f"왼쪽 표본에 {left} 컬럼 없음"}
    col = lv.columns[0]
    vals = _clean(lv[col]).drop_duplicates().head(SAMPLE)
    if on.get("transform") == "R-12":
        return _spatial(rec, _all_columns(e["src"]), "coord")
    if on.get("transform") == "R-13":
        return _spatial(rec, lv, "address")
    if on.get("via_mapping"):
        m = pd.read_parquet(config.KNOWLEDGE / "mappings" / f"{on['via_mapping']}.parquet")
        known = set(m["left_value"].astype(str))
        hit = set(m.loc[m["right_value"].notna(), "left_value"].astype(str))
        norm = vals.map(_norm)
        inmap = norm[norm.isin(known)]
        if not len(inmap):  # 표본 값이 매핑표 범위 밖 (예: 2015년 거래 표본 vs 최근 6개월 매핑) — 판정 보류
            return {**rec, "method": f"mapping {on['via_mapping']}", "match_rate": None, "n": int(len(norm)),
                    "detail": "표본 값이 매핑표 범위 밖 — 판정 보류"}
        return {**rec, "method": f"mapping {on['via_mapping']}", "match_rate": round(inmap.isin(hit).mean(), 4), "n": int(len(inmap)),
                "coverage_of_sample": round(len(inmap) / len(norm), 4)}
    if e["dst"] == "15123287":  # 법정동 코드표
        codes = _bjd_codes()
        if on.get("transform") == "R-14":
            from pds.rules import admin_name_to_code
            ok = [admin_name_to_code(v) is not None for v in vals]
            return {**rec, "method": "R-14 이름→코드", "match_rate": round(sum(ok) / max(1, len(ok)), 4), "n": len(ok)}
        v = vals.map(_norm)
        v = v.where(v.str.len() != 5, v + "00000").where(v.str.len() != 2, v + "0" * 8)
        return {**rec, "method": "법정동 코드표 포함률", "match_rate": round(v.isin(codes).mean(), 4) if len(v) else None, "n": int(len(v))}
    # 같은 키
    key = next((k for k in keys if k in (e.get("note") or "")), None)
    rv = _values(e["dst"], right)
    rcol = next((c for c in right if c in rv.columns), None)
    rset = set(_clean(rv[rcol]).map(_norm)) if rcol else set()
    master = MASTERS.get(key or "")
    if master and (M / f"{master[0]}.parquet").exists():
        mset = set(pd.read_parquet(M / f"{master[0]}.parquet", columns=[master[1]])[master[1]].astype(str).map(_norm))
        v = vals.map(_norm)
        return {**rec, "method": f"전수 원장 포함률 ({master[0]})", "match_rate": round(v.isin(mset).mean(), 4) if len(v) else None,
                "n": int(len(v))}
    v = vals.map(_norm)
    rate = round(v.isin(rset).mean(), 4) if len(v) and rset else None
    if not rate:  # 거래 번호처럼 표본 기간이 달라 겹치지 않는 키 — 오른쪽 API를 그 값으로 직접 조회
        lk = _lookup_probe(e["dst"], right, vals)
        if lk:
            return {**rec, **lk, "sample_overlap": rate}
    return {**rec, "method": "표본 겹침 (전수 원장 없음 — 0이면 판정 보류)",
            "match_rate": rate if rate else None, "sample_overlap": rate, "n": int(len(v)), "right_n": len(rset),
            "pattern_ok": round(v.str.fullmatch(keys.get(key, {}).get("pattern") or r".+").mean(), 4) if key and len(v) else None}


LOOKUP_N = 5


def _lookup_probe(dst: str, right: list[str], vals: pd.Series) -> dict | None:
    """오른쪽 데이터의 API에 같은 이름의 조회 파라미터가 있으면 왼쪽 값 LOOKUP_N개로 직접 불러 찾아지는 비율을 잰다."""
    sp = config.ROOT / "probe" / "specs" / f"{dst}.json"
    if not sp.exists():
        return None
    spec = json.loads(sp.read_text(encoding="utf-8"))
    if not spec.get("swagger"):
        return None
    want = {c.lower() for c in right}
    op = next((o for o in spec.get("operations") or [] if o.get("method", "GET") == "GET"
               and any((p.get("name") or "").lower() in want for p in o.get("params") or [])), None)
    if not op:
        return None
    pname = next(p["name"] for p in op["params"] if (p.get("name") or "").lower() in want)
    from pds.probe import deep
    scheme = "https" if "https" in (spec.get("schemes") or ["https"]) else "http"
    base = f"{scheme}://{spec['host']}{spec.get('base_path') or ''}"
    picks = [x for x in vals.dropna().astype(str).unique() if x.strip()][:LOOKUP_N]
    if not picks:
        return None
    key = deep.service_key()
    found = 0
    base_extra = deep.overrides(dst, op["path"])
    names = [p.get("name") or "" for p in op.get("params") or []]
    no_dates = {n: None for n in names if re.search(r"(Dt|Ymd|Bgn|End|Date|date|YM|Ym)$", n) or re.search(r"(Bgn|End)", n)}
    variants = [base_extra, {**no_dates}]  # ① 저장된 호출 조건 + 값 ② 날짜 조건을 빼고 값만
    if "inqryDiv" in names:  # 나라장터: 조회구분 1=기간, 2·3=번호
        variants += [{**no_dates, "inqryDiv": d} for d in ("2", "3")]
    used = None
    with httpx.Client(headers={"User-Agent": "pds-probe/0.1"}) as c:
        for x in picks:
            hit = False
            for v in ([used] if used is not None else variants):
                r = deep.call_op(c, base, op, key, 10, rows=10, extra={**v, pname: x})
                df = r.pop("_df", None)
                # 조건을 무시하고 아무 행이나 주는 API가 있다 — 그 값이 실제로 들어 있어야 찾은 것
                if df is not None and len(df) and df.astype(str).apply(lambda col: col.map(_norm).eq(_norm(x))).any().any():
                    hit, used = True, v
                    break
                time.sleep(0.15)
            found += hit
    return {"method": f"조회 실측 ({dst} {op['path']}?{pname}=왼쪽 값 {len(picks)}건, 값 포함 확인)", "match_rate": round(found / len(picks), 4),
            "n": len(picks), "found": found, "params_used": {k: v for k, v in (used or {}).items()}}


def _all_columns(dsid: str) -> pd.DataFrame:
    frames = []
    for f in glob.glob(str(P / dsid / "*.parquet")):
        try:
            frames.append(pd.read_parquet(f).astype(str))
        except Exception:  # noqa: BLE001
            continue
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


LAT = re.compile(r"(^lat|lat$|_lat|latitude|위도|^la_|_la$|la_crd|ycrd|y_crd|^y$|_y$|ypos)", re.I)
LON = re.compile(r"(^lon|lon$|_lon|lng|longitude|logitude|경도|^lo_|_lo$|lo_crd|lot$|xcrd|x_crd|^x$|_x$|xpos)", re.I)


def _spatial(rec: dict, lv: pd.DataFrame, kind: str) -> dict:
    from pds.rules import address_to_coord, coord_to_pnu
    ok, tried, ex = 0, 0, []
    with httpx.Client(timeout=30) as c:
        if kind == "coord":
            cols = [str(x) for x in lv.columns]
            lat_c = next((x for x in cols if LAT.search(x) and not LON.search(x)), None)
            lon_c = next((x for x in cols if LON.search(x) and not LAT.search(x)), None)
            if not (lat_c and lon_c):
                return {**rec, "method": "R-12", "match_rate": None, "detail": f"위경도 컬럼 판별 실패 {cols}"}
            pts = lv[[lat_c, lon_c]].apply(pd.to_numeric, errors="coerce").dropna()
            pts = pts[(pts[lat_c].between(33, 39)) & (pts[lon_c].between(124, 132))].drop_duplicates().head(SPATIAL_SAMPLE)
            for la, lo in pts.itertuples(index=False):
                tried += 1
                pnu = coord_to_pnu(la, lo, c)
                ok += bool(pnu)
                ex.append(pnu)
                time.sleep(0.3)
        else:
            addrs = _clean(lv[lv.columns[0]]).drop_duplicates().head(SPATIAL_SAMPLE)
            for a in addrs:
                tried += 1
                pt = address_to_coord(a, c)
                pnu = coord_to_pnu(*pt, c) if pt else None
                ok += bool(pnu)
                ex.append(pnu)
                time.sleep(0.3)
    return {**rec, "method": f"R-12{'·R-13' if kind == 'address' else ''} 브이월드 실변환", "match_rate": round(ok / tried, 4) if tried else None,
            "n": tried, "examples": ex[:3]}


def run(only_unverified: bool = True) -> dict:
    keys = {k["id"]: k for k in store.load("key")}
    edges = store.load("edge")
    OUT.mkdir(parents=True, exist_ok=True)
    done, skipped = 0, 0
    for e in edges:
        if only_unverified and e.get("verified"):
            continue
        try:
            r = measure(e, keys)
        except Exception as ex:  # noqa: BLE001
            r = {"edge": e["id"], "error": repr(ex)[:200], "match_rate": None}
        if r is None:
            skipped += 1
            continue
        (OUT / f"{e['id']}.json").write_text(json.dumps(r, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
        if r.get("match_rate") is not None:
            e["verified"] = {"by": "measured", "run": f"probe/joins/{e['id']}.json", "match_rate": float(r["match_rate"]), "at": TODAY}
            if e.get("source") == "auto":  # 실측으로 신뢰도 보정: 선언 신뢰도와 매칭률의 평균
                e["confidence"] = round((e["confidence"] + float(r["match_rate"])) / 2, 3)
        done += 1
    store.dump(edges, store.PATHS["edge"], header="데이터셋 사이 조인·lookup 선언 (KNOWLEDGE-SPEC §3.4). source: auto는 pds/edges/auto.py가 다시 쓴다 —\n"
                                                  "확정한 Edge는 source: admin으로 바꾸면 보존된다. verified는 pds/probe/join.py 실측.")
    vr = [e["verified"]["match_rate"] for e in edges if e.get("verified")]
    return {"measured": done, "related_to(측정 안 함)": skipped, "with_rate": len(vr),
            "median_rate": float(pd.Series(vr).median()) if vr else None}


if __name__ == "__main__":
    print(run())
