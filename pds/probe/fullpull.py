"""전수 목록 수집 — 매핑·Edge에 필요한 코드 원장을 끝까지 받는다 (KNOWLEDGE-SPEC §7-4 준비).

Phase 2 검증(deep.py)은 최대 1,000행만 받는다. 매핑은 전수가 있어야 매칭률이 뜻을 가지므로 원장별로 끝까지 페이지를 돈다.
계획(PLANS): 데이터셋마다 오퍼레이션 + 고정 파라미터 + 반복 축(시도·시군구·도시코드).
출력: data/master/{id}/{name}.parquet (git 밖) · probe/fullpull/{id}.json (수집 기록: 행 수·전체 건수·호출 수·시각)
"""
from __future__ import annotations

import datetime as dt
import json
import time
from typing import Callable

import httpx
import pandas as pd

from pds import config
from pds.probe.deep import _items_json, _items_xml, _total

OUT = config.DATA / "master"
LOG = config.ROOT / "probe" / "fullpull"
SIDO2 = ["11", "26", "27", "28", "29", "30", "31", "36", "41", "42", "43", "44", "45", "46", "47", "48", "50", "51", "52"]


def _key() -> str:
    return json.loads((config.ROOT / "secrets" / "keys.json").read_text(encoding="utf-8"))["data.go.kr"]["decoding"]


def fetch_all(client: httpx.Client, url: str, params: dict, size: int = 1000, max_pages: int = 500,
              page_key: str = "pageNo", size_key: str = "numOfRows") -> tuple[list[dict], int | None, int]:
    """페이지를 끝까지. 서버가 size보다 적게 주면(상한) 받은 수를 페이지 크기로 보고 계속."""
    rows, total, calls, page = [], None, 0, 1
    while page <= max_pages:
        q = {"serviceKey": _key(), page_key: page, size_key: size, **params}
        for attempt in range(3):
            try:
                r = client.get(url, params=q, timeout=60)
                break
            except httpx.HTTPError:
                time.sleep(2 * (attempt + 1))
        else:
            break
        calls += 1
        text = r.text
        items = None
        if text.lstrip().startswith(("{", "[")):
            try:
                obj = r.json()
                items = _items_json(obj) or []
                total = total if total is not None else _total(obj)
            except json.JSONDecodeError:
                items = []
        else:
            items = _items_xml(text) or []
            if total is None:
                import re
                m = re.search(r"<totalCount>(\d+)</totalCount>", text)
                total = int(m.group(1)) if m else None
        if not items:
            break
        rows += items
        if total is not None and len(rows) >= total:
            break
        if total is None and len(items) < size:
            break
        page += 1
        time.sleep(0.05)
    return rows, total, calls


def _run(dsid: str, name: str, parts: list[tuple[str, dict]], **kw) -> dict:
    """parts: [(url, params)] — 반복 축마다 한 번씩 fetch_all, 결과를 합친다."""
    all_rows, tot_sum, calls, empty = [], 0, 0, 0
    with httpx.Client() as c:
        for url, params in parts:
            rows, total, n = fetch_all(c, url, params, **kw)
            for r in rows:
                r.update({f"_q_{k}": v for k, v in params.items()})
            all_rows += rows
            tot_sum += total or len(rows)
            calls += n
            empty += not rows
    df = pd.DataFrame(all_rows)
    (OUT / dsid).mkdir(parents=True, exist_ok=True)
    if len(df):
        df.astype(str).to_parquet(OUT / dsid / f"{name}.parquet", index=False)
    rec = {"id": dsid, "name": name, "rows": len(df), "total_reported": tot_sum, "calls": calls, "parts": len(parts),
           "empty_parts": empty, "columns": list(df.columns), "at": dt.datetime.now().isoformat(timespec="seconds"),
           "file": f"data/master/{dsid}/{name}.parquet"}
    LOG.mkdir(parents=True, exist_ok=True)
    prev = json.loads((LOG / f"{dsid}.json").read_text(encoding="utf-8")) if (LOG / f"{dsid}.json").exists() else {}
    prev[name] = rec
    (LOG / f"{dsid}.json").write_text(json.dumps(prev, ensure_ascii=False, indent=1), encoding="utf-8")
    return rec


def load(dsid: str, name: str) -> pd.DataFrame:
    return pd.read_parquet(OUT / dsid / f"{name}.parquet")


# ─────────────────────────── 원장별 계획
def apt_list() -> dict:  # K-apt 단지 목록 전체 (kaptCode·bjdCode)
    return _run("15057332", "total", [("https://apis.data.go.kr/1613000/AptListService4/getTotalAptList4", {"_type": "json"})])


def hosp_ykiho() -> dict:  # 심평원 병원정보 전체 (ykiho·주소·좌표)
    return _run("15001698", "hosp_basis", [("https://apis.data.go.kr/B551182/hospInfoServicev2/getHospBasisList", {"_type": "json"})])


def hosp_hpid() -> dict:  # 국립중앙의료원 병·의원 전체 (hpid)
    return _run("15000736", "hsptl_mdcnc",
                [("https://apis.data.go.kr/B552657/HsptlAsembySearchService/getHsptlMdcncListInfoInqire", {"_type": "json"})])


def ltc_institutions() -> dict:  # 장기요양기관 — 시도 필수
    url = "https://apis.data.go.kr/B550928/searchLtcInsttService02/getLtcInsttSeachList02"
    return _run("15059029", "ltc_instt", [(url, {"siDoCd": s, "_type": "json"}) for s in SIDO2])


def welfare_facilities() -> dict:  # 사회복지시설 목록 전체
    url = "https://apis.data.go.kr/B554287/sclWlfrFcltInfoInqirService2/getFcltListInfoInqire2"
    return _run("15001848", "fclt_list", [(url, {})])


def tago_stops() -> dict:  # TAGO 정류소 — 도시코드 목록 → 도시별 (서울 제외)
    base = "https://apis.data.go.kr/1613000/BusSttnInfoInqireService/"
    with httpx.Client() as c:
        cities, _, _ = fetch_all(c, base + "getCtyCodeList", {"_type": "json"}, size=500)
    return _run("15098534", "sttn_no_list", [(base + "getSttnNoList", {"cityCode": str(x["citycode"]), "_type": "json"}) for x in cities])


def bus_stops(sgg_codes: list[str], opr_ymd: str = "20250801") -> dict:  # 국토부 표준 버스정류장 — 시군구별
    url = "https://apis.data.go.kr/1613000/BusStop/getBusStop"
    return _run("15142032", "bus_stop", [(url, {"opr_ymd": opr_ymd, "ctpv_cd": s[:2], "sgg_cd": s, "dataType": "JSON"})
                                         for s in sgg_codes])


def sgg_codes() -> list[str]:
    """시군구 5자리 — K-apt 단지 목록의 법정동코드 앞 5자리 (전국 공동주택이 있는 시군구)."""
    return sorted(load("15057332", "total")["bjdCode"].astype(str).str[:5].unique())


def rtms_trades(months: list[str] | None = None) -> dict:  # 아파트 매매 실거래 상세 — 시군구 × 월 (aptSeq 단지 목록용)
    if months is None:
        t = dt.date.today().replace(day=1)
        months = []
        for _ in range(6):
            t = (t - dt.timedelta(days=1)).replace(day=1)
            months.append(t.strftime("%Y%m"))
    url = "https://apis.data.go.kr/1613000/RTMSDataSvcAptTradeDev/getRTMSDataSvcAptTradeDev"
    return _run("15126468", "trades_6m", [(url, {"LAWD_CD": s, "DEAL_YMD": m}) for s in sgg_codes() for m in months])


def bus_stops_all() -> dict:
    return bus_stops(sgg_codes())


PLANS: dict[str, Callable[[], dict]] = {"apt": apt_list, "ykiho": hosp_ykiho, "hpid": hosp_hpid, "ltc": ltc_institutions,
                                        "welfare": welfare_facilities, "tago": tago_stops,
                                        "rtms": rtms_trades, "busstop": bus_stops_all}



# ─────────────────────────── 토지특성 코드 관측 (지목·용도지역·지형·도로접면·이용상황) — 전국 15곳 필지 표본
LAND_SITES = {  # 이름: (경도, 위도) — 도심·농촌·산지·공단·해안이 섞이게
    "서울종로": (126.973, 37.583), "평택농촌": (127.00, 36.95), "평창산지": (128.40, 37.50), "당진논": (126.60, 36.90),
    "나주들": (126.70, 35.00), "의성": (128.70, 36.35), "창원공단": (128.68, 35.23), "제주": (126.50, 33.45),
    "송도": (126.64, 37.39), "해운대": (129.16, 35.16), "달성": (128.45, 35.75), "울산공단": (129.33, 35.50),
    "괴산": (127.80, 36.80), "김제": (126.88, 35.80), "속초": (128.59, 38.20),
}


def _get_retry(c: httpx.Client, url: str, params: dict, tries: int = 3) -> httpx.Response | None:
    for i in range(tries):
        try:
            r = c.get(url, params=params)
            time.sleep(0.15)
            return r
        except httpx.HTTPError:
            time.sleep(2 * (i + 1))
    return None


def land_characteristics(per_site: int = 120) -> dict:
    vw = json.loads((config.ROOT / "secrets" / "keys.json").read_text(encoding="utf-8"))["vworld"]
    key, domain = vw["key"], vw.get("domain", "bv")
    rows, calls = [], 0
    with httpx.Client(timeout=40) as c:
        for site, (lon, lat) in LAND_SITES.items():
            box = f"BOX({lon - 0.006},{lat - 0.006},{lon + 0.006},{lat + 0.006})"
            r = _get_retry(c, "https://api.vworld.kr/req/data", {"service": "data", "request": "GetFeature", "data": "LP_PA_CBND_BUBUN",
                           "geomFilter": box, "format": "json", "size": per_site, "page": 1, "geometry": "false", "key": key, "domain": domain})
            calls += 1
            if r is None:
                continue
            feats = ((r.json()["response"].get("result") or {}).get("featureCollection") or {}).get("features") or []
            for f in feats:
                pnu = f["properties"].get("pnu")
                q = _get_retry(c, "https://api.vworld.kr/ned/data/getLandCharacteristics",
                               {"pnu": pnu, "stdrYear": "2025", "format": "json", "numOfRows": 1, "pageNo": 1, "key": key, "domain": domain})
                calls += 1
                try:
                    fld = (q.json().get("landCharacteristicss") or {}).get("field") or [] if q is not None else []
                except ValueError:
                    fld = []
                for x in fld[:1]:
                    rows.append({**x, "_site": site})
    df = pd.DataFrame(rows)
    (OUT / "vworld_landchar").mkdir(parents=True, exist_ok=True)
    df.astype(str).to_parquet(OUT / "vworld_landchar" / "sample.parquet", index=False)
    rec = {"id": "vworld_landchar", "rows": len(df), "calls": calls, "sites": list(LAND_SITES), "at": dt.datetime.now().isoformat(timespec="seconds"),
           "file": "data/master/vworld_landchar/sample.parquet"}
    LOG.mkdir(parents=True, exist_ok=True)
    (LOG / "vworld_landchar.json").write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
    return rec


PLANS["landchar"] = land_characteristics



def stan_org_codes() -> dict:
    """행정표준 기관코드 전수 (15077870) — 응답이 {StanOrgCd: [{head}, {row: [...]}]} 형태라 전용 페이지 루프."""
    url = "https://apis.data.go.kr/1741000/StanOrgCd2/getStanOrgCdList2"
    rows, total, calls, page = [], None, 0, 1
    with httpx.Client(timeout=60) as c:
        while True:
            r = _get_retry(c, url, {"serviceKey": _key(), "pageNo": page, "numOfRows": 1000, "type": "json"})
            calls += 1
            if r is None:
                break
            try:
                body = r.json()["StanOrgCd"]
            except (ValueError, KeyError):
                break
            if total is None:
                total = int(body[0]["head"][0]["totalCount"])
            part = body[1]["row"] if len(body) > 1 else []
            if not part:
                break
            rows += part
            if len(rows) >= total:
                break
            page += 1
    df = pd.DataFrame(rows)
    (OUT / "15077870").mkdir(parents=True, exist_ok=True)
    df.astype(str).to_parquet(OUT / "15077870" / "stan_org_cd.parquet", index=False)
    rec = {"id": "15077870", "name": "stan_org_cd", "rows": len(df), "total_reported": total, "calls": calls,
           "at": dt.datetime.now().isoformat(timespec="seconds"), "file": "data/master/15077870/stan_org_cd.parquet"}
    LOG.mkdir(parents=True, exist_ok=True)
    (LOG / "15077870.json").write_text(json.dumps({"stan_org_cd": rec}, ensure_ascii=False, indent=1), encoding="utf-8")
    return rec


PLANS["stanorg"] = stan_org_codes

if __name__ == "__main__":
    import sys
    for name in sys.argv[1:] or list(PLANS):
        t0 = time.time()
        rec = PLANS[name]()
        print(name, {k: rec.get(k) for k in ("rows", "total_reported", "calls", "empty_parts")}, f"{time.time() - t0:.0f}s", flush=True)
