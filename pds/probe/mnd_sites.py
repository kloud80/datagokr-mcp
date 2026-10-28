"""국방부 국방 공공데이터 개방(opendata.mnd.go.kr) 검증 — 포털 링크형의 데이터셋(infId)을 오픈API 또는 시트 조회로 불러 확인한다 (DATA_MND_API_KEY).

1. 링크의 infId로 시트 화면 /openinf/sheetview2.jsp?infId 를 연다 — dsId(테이블)와 제공 유형 버튼(시트·오픈API 등). 화면이 없으면
   ("서비스가 존재하지 않아") 내려간 데이터로 실패
2. 오픈API가 있으면 같은 세션으로 /openinf/openapiview2.jsp (POST infId·selSrvType=A) 의 견본 주소에서 서비스 이름(DS_…)을 읽어
   https://openapi.mnd.go.kr/{KEY}/json/{SERVICE}/1/1000/ — 전체 건수 list_total_count
3. 오픈API가 없으면 시트 조회 /openinf/sheetexec.jsp (POST infId·dsId·ibpage·onepagerow — 키 없음). 응답은 따옴표 없는 JS 객체라 고쳐 읽는다
응답·기록에 키를 싣지 않는다 (키는 경로에 들어가므로 기록의 url은 {KEY}로 적는다).
실행: python -m pds.probe.mnd_sites [id…]
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import sys
import time

import httpx
import pandas as pd

from pds import config
from pds.probe.deep import col_stats, save_run

P = config.ROOT / "probe"
B = "https://opendata.mnd.go.kr/openinf"
API = "https://openapi.mnd.go.kr"


def key() -> str:
    return os.environ.get("DATA_MND_API_KEY", "").strip()


def _js_obj(t: str) -> dict:
    """{TOTAL:16, DATA:[{RN:"1",forn:"131860"},]} → dict (키에 따옴표를 붙이고 끝 쉼표를 뗀다)."""
    t = re.sub(r'([{,]\s*)([A-Za-z_]\w*)\s*:', r'\1"\2":', t)
    return json.loads(re.sub(r",\s*([\]}])", r"\1", t))  # 끝 쉼표 [..,] 도 있다


def api_service(c: httpx.Client, inf: str) -> str | None:
    h = c.post(f"{B}/openapiview2.jsp", data={"infId": inf, "selSrvType": "A", "infSeq": "1", "tMenu": "Dataset", "sMenu": "Dataset"}).text
    m = re.search(r"openapi\.mnd\.go\.kr/sample/\w+/(\w+)/", h)
    return m.group(1) if m else None


def via_api(c: httpx.Client, svc: str) -> tuple[pd.DataFrame | None, int | None, str | None]:
    time.sleep(0.3)
    r = c.get(f"{API}/{key()}/json/{svc}/1/1000/")
    try:
        j = r.json()
    except Exception:  # noqa: BLE001
        return None, None, f"json 아님 {r.status_code}"
    body = j.get(svc) or {}
    rows = body.get("row") or []
    if not rows:
        return None, None, str((j.get("RESULT") or body.get("RESULT") or {}).get("MESSAGE", j))[:120].replace("\n", " ")
    return pd.DataFrame(rows), body.get("list_total_count"), None


def via_sheet(c: httpx.Client, inf: str, ds: str) -> tuple[pd.DataFrame | None, int | None, str | None]:
    time.sleep(0.3)
    r = c.post(f"{B}/sheetexec.jsp", data={"ibpage": "1", "onepagerow": "1000", "infId": inf, "dsId": ds, "strWhere": "", "filterCol": "", "txtFilter": ""})
    try:
        j = _js_obj(r.text.strip())
    except Exception:  # noqa: BLE001
        return None, None, f"시트 응답을 읽지 못함 {r.status_code} {r.text[:60]}"
    rows = [{k: v for k, v in x.items() if k != "RN"} for x in j.get("DATA") or []]
    if not rows:
        return None, None, "시트 0행"
    return pd.DataFrame(rows), j.get("TOTAL"), None


def run_one(c: httpx.Client, dsid: str, link: str) -> dict:
    run = {"id": dsid, "kind": "external", "site": "opendata.mnd.go.kr", "link": link, "started_at": dt.datetime.now().isoformat(timespec="seconds"),
           "ops": []}
    m = re.search(r"infId=([\w\-]+)", link)
    if not m:
        run.update({"ok_ops": 0, "error": "링크에 infId 없음"})
    else:
        inf = m.group(1)
        h = c.get(f"{B}/sheetview2.jsp", params={"infId": inf}).text
        ds = re.search(r'name="dsId"[^>]*value="([^"]*)"', h)
        if not ds or not ds.group(1):
            run.update({"ok_ops": 0, "error": f"{inf} 데이터셋 화면 없음 (사이트에서 내려감 — '서비스가 존재하지 않아')"})
        else:
            svc = api_service(c, inf)
            df, total, err, op = None, None, None, None
            if svc:
                df, total, err = via_api(c, svc)
                op = {"op": svc, "url": f"{API}/{{KEY}}/json/{svc}/1/1000/", "params": {},
                      "note": f"국방 공공데이터 오픈API {svc} ({inf}) — 키는 경로(KEY 자리)"}
            if df is None:
                e1 = err
                df, total, err = via_sheet(c, inf, ds.group(1))
                op = {"op": "sheetexec", "url": f"{B}/sheetexec.jsp", "params": {"infId": inf, "dsId": ds.group(1), "ibpage": 1, "onepagerow": 1000},
                      "note": f"국방 공공데이터 시트 조회 ({inf} · {ds.group(1)}) — 키 없이 POST" + (f" · 오픈API 실패: {e1}" if svc else "")}
            if df is None:
                run.update({"ok_ops": 0, "error": f"{inf} {err}"})
            else:
                (P / "data" / dsid).mkdir(parents=True, exist_ok=True)
                df.astype(str).to_parquet(P / "data" / dsid / f"mnd_{dt.date.today():%Y%m%d}.parquet")
                (P / "stats" / f"{dsid}.json").write_text(json.dumps({op["op"]: col_stats(df)}, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
                run["ops"] = [{**op, "ok": True, "rows": len(df), "total_count": total, "columns": list(map(str, df.columns))}]
                run["ok_ops"] = 1
    run["finished_at"] = dt.datetime.now().isoformat(timespec="seconds")
    save_run(run)  # 실패면 기존 성공 기록을 덮지 않는다
    return run


def main(only: set[str] | None = None) -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    lk = pd.read_parquet(config.KNOWLEDGE / "expansion" / "site_links.parquet", columns=["id", "host", "link", "title"]).drop_duplicates("id")
    lk = lk[lk["host"].fillna("").str.endswith("mnd.go.kr")]
    if only:
        lk = lk[lk["id"].isin(only)]
    ok = 0
    with httpx.Client(timeout=90, headers={"User-Agent": "Mozilla/5.0"}, follow_redirects=True) as c:
        for n, r in enumerate(lk.itertuples(), 1):
            try:
                run = run_one(c, r.id, r.link)
            except Exception as e:  # noqa: BLE001
                print(f"  {n}/{len(lk)} {r.id} 오류 {repr(e)[:120]}", flush=True)
                continue
            ok += bool(run.get("ok_ops"))
            print(f"  {n}/{len(lk)} {r.id} {'성공' if run.get('ok_ops') else '실패'} {str(r.title)[:28]} "
                  f"{run.get('error') or run['ops'][0]['op'] + ' ' + str(run['ops'][0]['total_count']) + '건'}"[:170], flush=True)
    print({"국방부 링크": len(lk), "성공": ok})


if __name__ == "__main__":
    main(set(sys.argv[1:]) or None)
