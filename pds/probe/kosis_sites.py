"""KOSIS 국가통계포털 검증 — 포털 링크형(kosis.kr · stat.kosis.kr)의 통계표를 OpenAPI로 불러 확인한다 (KOSIS_API_KEY).

1. 링크에서 orgId·tblId (statHtml.do?orgId=…&tblId=…). 통계목록 화면(vwcd=MT_…, parentId·listid)은 통계목록 API
   statisticsList.do?method=getList&vwCd&parentListId 로 확인한다. 둘 다 없는 화면(간행물·시각화)은 실패로 남긴다
2. 메타: statisticsData.do?method=getMeta&type=PRD(수록주기) · type=ITM(분류 수)
3. 자료: Param/statisticsParameterData.do?method=getList&orgId&tblId&itmId=ALL&objL1..n=ALL&prdSe&newEstPrdCnt=1 — 최근 1시점
   (statisticsData.do는 사용자 등록 통계표 userStatsId용이다). 4만 셀이 넘으면(오류 31) 항목 하나 → 첫 분류 하나로 좁힌다
제한: 분당 200건 — 호출 사이 0.35초. 키는 base64라 끝의 '='가 빠져 있으면 채운다. 응답·기록에 키를 싣지 않는다.
실행: python -m pds.probe.kosis_sites [id…]
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
META = "https://kosis.kr/openapi/statisticsData.do"
LIST = "https://kosis.kr/openapi/statisticsList.do"
DATA = "https://kosis.kr/openapi/Param/statisticsParameterData.do"
SE = {"년": "Y", "반기": "H", "분기": "Q", "월": "M", "일": "D", "부정기": "IR", "2년": "F", "3년": "F", "4년": "F", "5년": "F", "10년": "F"}
ORDER = ["M", "Q", "H", "Y", "F", "D", "IR"]  # 같은 표에 주기가 여럿이면 촘촘한 쪽


def key() -> str:
    k = os.environ.get("KOSIS_API_KEY", "").strip()
    return k + "=" * (-len(k) % 4)


def ids_of(link: str) -> tuple[str, str] | None:
    m = re.search(r"orgId=(\w+)", link, re.I), re.search(r"tblId=([\w\-]+)", link, re.I)
    return (m[0].group(1), m[1].group(1)) if all(m) else None


def _get(c: httpx.Client, url: str, **p):
    time.sleep(0.35)
    r = c.get(url, params={"apiKey": key(), "format": "json", "jsonVD": "Y", **p})
    try:
        return r.json()
    except Exception:  # noqa: BLE001
        return {"err": "json", "errMsg": f"json 아님 {r.status_code} {r.text[:80]}"}


def fetch(c: httpx.Client, org: str, tbl: str) -> tuple[pd.DataFrame | None, dict, str | None]:
    prd = _get(c, META, method="getMeta", type="PRD", orgId=org, tblId=tbl)
    if not isinstance(prd, list) or not prd:
        return None, {}, f"수록주기: {prd.get('errMsg') if isinstance(prd, dict) else prd}"
    ses = sorted({SE.get(x["PRD_SE"], x["PRD_SE"]) for x in prd}, key=lambda s: ORDER.index(s) if s in ORDER else 99)
    itm = _get(c, META, method="getMeta", type="ITM", orgId=org, tblId=tbl)
    if not isinstance(itm, list):
        return None, {}, f"분류: {itm.get('errMsg')}"
    objs: list[str] = []
    for x in itm:
        if x["OBJ_ID"] != "ITEM" and x["OBJ_ID"] not in objs:
            objs.append(x["OBJ_ID"])
    first = {o: next(x["ITM_ID"] for x in itm if x["OBJ_ID"] == o) for o in ["ITEM", *objs] if any(x["OBJ_ID"] == o for x in itm)}
    base = {"method": "getList", "orgId": org, "tblId": tbl, "itmId": "ALL", "prdSe": ses[0], "newEstPrdCnt": "1",
            **{f"objL{n}": "ALL" for n in range(1, len(objs) + 1)}}
    narrow = [{}, {"itmId": first.get("ITEM", "ALL")}]
    if objs:
        narrow.append({"itmId": first.get("ITEM", "ALL"), "objL1": first[objs[0]]})
    err = None
    for extra in narrow:
        d = _get(c, DATA, **base, **extra)
        if isinstance(d, list) and d:
            prm = {k: v for k, v in {**base, **extra}.items() if k != "method"}
            return pd.DataFrame(d), {"params": prm, "periods": [f"{x['PRD_SE']} {x.get('STRT_PRD_DE')}~{x.get('END_PRD_DE')}" for x in prd],
                                     "classes": len(objs), "narrowed": bool(extra)}, None
        err = d.get("errMsg") if isinstance(d, dict) else str(d)[:120]
        if not (isinstance(d, dict) and d.get("err") == "31"):  # 셀 초과가 아니면 좁혀도 소용없다
            break
    return None, {}, f"자료: {err}"


def _store(dsid: str, df: pd.DataFrame, op: str) -> None:
    (P / "data" / dsid).mkdir(parents=True, exist_ok=True)
    df.astype(str).to_parquet(P / "data" / dsid / f"kosis_{dt.date.today():%Y%m%d}.parquet")
    (P / "stats" / f"{dsid}.json").write_text(json.dumps({op: col_stats(df)}, ensure_ascii=False, indent=1, default=str), encoding="utf-8")


def run_one(c: httpx.Client, dsid: str, link: str, title: str = "") -> dict:
    run = {"id": dsid, "kind": "external", "site": "kosis.kr", "link": link, "started_at": dt.datetime.now().isoformat(timespec="seconds"),
           "ops": []}
    ot = ids_of(link)
    vw = re.search(r"vwcd=(MT_\w+)", link, re.I)
    if not ot and vw:
        parent = re.search(r"(?:parentId|listid)=([\w\-]+)", link, re.I)
        prm = {"method": "getList", "vwCd": vw.group(1), "parentListId": parent.group(1) if parent else ""}
        d = _get(c, LIST, **prm)
        if isinstance(d, list) and d:
            df = pd.DataFrame(d)
            _store(dsid, df, "statisticsList")
            run["ops"] = [{"op": "statisticsList", "url": LIST, "ok": True, "rows": len(df), "columns": list(map(str, df.columns)),
                           "params": {"format": "json", "jsonVD": "Y", **prm},
                           "note": f"KOSIS 통계목록 {vw.group(1)}{' · ' + prm['parentListId'] if prm['parentListId'] else ''} 한 단계 — apiKey(query)"}]
            run["ok_ops"] = 1
        else:
            run.update({"ok_ops": 0, "error": f"통계목록 {vw.group(1)}: {d.get('errMsg') if isinstance(d, dict) else d}"})
    elif not ot:
        run.update({"ok_ops": 0, "error": "링크가 통계표·통계목록이 아닌 화면(간행물·시각화 등) — orgId·tblId·vwcd 없음"})
    else:
        df, info, err = fetch(c, *ot)
        if df is None:
            run.update({"ok_ops": 0, "error": f"{ot[0]}/{ot[1]} {err}"})
        else:
            _store(dsid, df, "statisticsParameterData")
            run["ops"] = [{"op": "statisticsParameterData", "url": DATA, "ok": True, "rows": len(df), "columns": list(map(str, df.columns)),
                           "params": {"method": "getList", "format": "json", "jsonVD": "Y", **info["params"]},
                           "note": f"KOSIS 통계표 {ot[0]}/{ot[1]} 최근 1시점{' (4만 셀 제한으로 좁힘)' if info['narrowed'] else ''} — "
                                   f"수록 {', '.join(info['periods'])} · 분류 {info['classes']}개, apiKey(query)"}]
            run["ok_ops"] = 1
    run["finished_at"] = dt.datetime.now().isoformat(timespec="seconds")
    save_run(run)  # 실패면 기존 성공 기록을 덮지 않는다
    return run


def links(only: set[str] | None = None) -> pd.DataFrame:
    lk = pd.read_parquet(config.KNOWLEDGE / "expansion" / "site_links.parquet", columns=["id", "host", "link", "title"]).drop_duplicates("id")
    lk = lk[lk["host"].fillna("").str.contains("kosis.kr")]
    return lk[lk["id"].isin(only)] if only else lk


def main(only: set[str] | None = None) -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    lk = links(only)
    ok = 0
    with httpx.Client(timeout=90, headers={"User-Agent": "Mozilla/5.0"}) as c:
        for n, r in enumerate(lk.itertuples(), 1):
            run = run_one(c, r.id, r.link, r.title)
            ok += bool(run.get("ok_ops"))
            print(f"  {n}/{len(lk)} {r.id} {'성공' if run.get('ok_ops') else '실패'} {str(r.title)[:28]} "
                  f"{run.get('error') or str(run['ops'][0]['rows']) + '행'}"[:160], flush=True)
    print({"KOSIS 링크": len(lk), "성공": ok})


if __name__ == "__main__":
    main(set(sys.argv[1:]) or None)
