"""한국부동산원 부동산통계정보 R-ONE 검증 — 포털 링크형(reb.or.kr)의 통계표를 R-ONE OpenAPI로 불러 확인한다 (REB_API_KEY).

1. 링크에서 통계표 ID: /r-one/portal/stat/easyStatPage/<STATBL_ID>.do (A_2024_00545 · T245883135037859 꼴)
   게시판·보고서 화면(searchBulletinPage·selectNttList)은 통계표가 정해지지 않아 실패로 남긴다
2. 통계표: https://www.reb.or.kr/r-one/openapi/SttsApiTbl.do?STATBL_ID → 수록주기(DTACYCLE_CD, 여럿이면 촘촘한 쪽부터 자료가 나올 때까지)
3. 자료: SttsApiTblData.do?STATBL_ID&DTACYCLE_CD&pIndex=1&pSize=1000 — 첫 1천 행과 전체 행 수(list_total_count)
공통 인자 KEY·Type=json·pIndex·pSize. 응답·기록에 키를 싣지 않는다.
실행: python -m pds.probe.reb_sites [id…]
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
B = "https://www.reb.or.kr/r-one/openapi/"
CYCLE = ["DD", "WK", "MM", "QY", "HY", "YY"]


def _get(c: httpx.Client, ep: str, **p) -> tuple[list[dict], int | None, str | None]:
    time.sleep(0.2)
    r = c.get(B + ep, params={"KEY": os.environ.get("REB_API_KEY", "").strip(), "Type": "json", "pIndex": 1, "pSize": 1000, **p})
    try:
        body = r.json().get(ep.removesuffix(".do"))
    except Exception:  # noqa: BLE001
        return [], None, f"json 아님 {r.status_code}"
    if not body:
        return [], None, r.text[:160]
    total, rows, msg = None, [], None
    for part in body:
        for h in part.get("head") or []:
            total = total or h.get("list_total_count")
            if "RESULT" in h:
                msg = h["RESULT"].get("MESSAGE")
        rows += part.get("row") or []
    return rows, total, None if rows else (msg or "0행")


def run_one(c: httpx.Client, dsid: str, link: str) -> dict:
    run = {"id": dsid, "kind": "external", "site": "www.reb.or.kr", "link": link, "started_at": dt.datetime.now().isoformat(timespec="seconds"),
           "ops": []}
    m = re.search(r"easyStatPage/([\w]+)\.do", link) or re.search(r"(?:statbl_id|STATBL_ID)=([\w]+)", link)
    if not m:
        run.update({"ok_ops": 0, "error": "링크가 통계표가 아닌 화면(게시판·보고서) — 통계표 ID 없음"})
    else:
        sid = m.group(1)
        meta, _, err = _get(c, "SttsApiTbl.do", STATBL_ID=sid)
        if not meta:
            run.update({"ok_ops": 0, "error": f"{sid} 통계표: {err}"})
        else:
            t = meta[0]
            rows, total, err = [], None, "주기 없음"
            for cyc in sorted((t.get("DTACYCLE_CD") or "YY").split(","), key=lambda x: CYCLE.index(x) if x in CYCLE else 99):
                rows, total, err = _get(c, "SttsApiTblData.do", STATBL_ID=sid, DTACYCLE_CD=cyc)  # 주기가 여럿이면 자료가 있는 쪽
                if rows:
                    break
            if not rows:
                run.update({"ok_ops": 0, "error": f"{sid} 자료({cyc}): {err}"})
            else:
                df = pd.DataFrame(rows)
                (P / "data" / dsid).mkdir(parents=True, exist_ok=True)
                df.astype(str).to_parquet(P / "data" / dsid / f"reb_{dt.date.today():%Y%m%d}.parquet")
                (P / "stats" / f"{dsid}.json").write_text(json.dumps({"SttsApiTblData": col_stats(df)}, ensure_ascii=False, indent=1, default=str),
                                                         encoding="utf-8")
                run["ops"] = [{"op": "SttsApiTblData", "url": B + "SttsApiTblData.do", "ok": True, "rows": len(df), "total_count": total,
                               "columns": list(map(str, df.columns)),
                               "params": {"Type": "json", "pIndex": 1, "pSize": 1000, "STATBL_ID": sid, "DTACYCLE_CD": cyc},
                               "note": f"R-ONE 통계표 {sid} '{t.get('STATBL_NM')}' · {t.get('DTACYCLE_NM')} · "
                                       f"{t.get('DATA_START_YY')}~{t.get('DATA_END_YY')} — KEY(query)"}]
                run["ok_ops"] = 1
    run["finished_at"] = dt.datetime.now().isoformat(timespec="seconds")
    save_run(run)  # 실패면 기존 성공 기록을 덮지 않는다
    return run


def main(only: set[str] | None = None) -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    lk = pd.read_parquet(config.KNOWLEDGE / "expansion" / "site_links.parquet", columns=["id", "host", "link", "title"]).drop_duplicates("id")
    lk = lk[lk["host"].fillna("").str.contains("reb.or.kr")]
    if only:
        lk = lk[lk["id"].isin(only)]
    ok = 0
    with httpx.Client(timeout=90, headers={"User-Agent": "Mozilla/5.0"}) as c:
        for n, r in enumerate(lk.itertuples(), 1):
            run = run_one(c, r.id, r.link)
            ok += bool(run.get("ok_ops"))
            print(f"  {n}/{len(lk)} {r.id} {'성공' if run.get('ok_ops') else '실패'} {str(r.title)[:28]} "
                  f"{run.get('error') or str(run['ops'][0]['total_count']) + '행'}"[:160], flush=True)
    print({"R-ONE 링크": len(lk), "성공": ok})


if __name__ == "__main__":
    main(set(sys.argv[1:]) or None)
