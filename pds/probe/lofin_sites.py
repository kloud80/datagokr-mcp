"""지방재정365(lofin365.go.kr) 검증 — 재정 데이터셋 146개의 오픈API 서비스명을 찾아 인증키로 호출하고, 포털 링크형과 제목으로 짝짓는다.

1. 목록: POST /lf/pfinDtaOpen/dtst/dtstSvi/retvLstDtstExcelDown.do → pdtaId·pdtaNm
2. 서비스명: POST /lf/pfinDtaOpen/dtst/dtstSvi/retvDtstDtsApi.do (pdtaId) → 본문의 /lf/hub/<서비스>
3. 호출: GET https://www.lofin365.go.kr/lf/hub/<서비스>?Key=&Type=json&pIndex=1&pSize=100 (LOFIN365_API_KEY)
4. 포털 링크(LF6000000.do?ntcaClsDvCd=…)는 공시 화면이라 데이터 id가 없다 — 포털 제목과 pdtaNm의 유사도로 짝짓는다(0.5 이상).
실행: python -m pds.probe.lofin_sites
"""
from __future__ import annotations

import datetime as dt
import difflib
import json
import os
import re
import sys

import httpx
import pandas as pd

from pds import config
from pds.probe.deep import col_stats

P = config.ROOT / "probe"
B = "https://www.lofin365.go.kr"
FORM = {"menuUrl": "/lf/pfinDtaOpen/dtst/dtstSvi/retvDtstDtsApi.do", "menuId": "LF5120000"}


def _norm(t: str) -> str:
    return re.sub(r"[\s()\[\]·_\-]|지방재정365|행정안전부|현황|정보", "", str(t))


def catalog(c: httpx.Client) -> list[dict]:
    c.get(f"{B}/portal/LF5100000.do")
    r = c.post(f"{B}/lf/pfinDtaOpen/dtst/dtstSvi/retvLstDtstExcelDown.do", data={"menuId": "LF5100000"})
    out = []
    for d in r.json()["resultList"]:
        if d.get("rlsSvApi") != "O":
            continue
        h = c.post(f"{B}/lf/pfinDtaOpen/dtst/dtstSvi/retvDtstDtsApi.do", data={**FORM, "pdtaId": d["pdtaId"]}).text
        svc = next(iter(re.findall(r"lf/hub/(\w+)", h)), None)
        sample = next(iter(re.findall(r"lf/hub/\w+\?([\w=&%.\-]+)", h)), "")  # 샘플URL의 필수 검색 인자 (예: fyr=2018)
        out.append({"pdtaId": d["pdtaId"], "name": d["pdtaNm"].strip(), "service": svc, "group": d.get("menuAtcClsNm"),
                    "sample": dict(x.split("=", 1) for x in sample.split("&") if "=" in x)})
    return out


def call(c: httpx.Client, svc: str, sample: dict | None = None) -> tuple[pd.DataFrame | None, int | None, str | None]:
    """샘플 인자로 부르고, 연도 인자는 최근 연도부터 거꾸로 (자료가 있는 해를 찾는다)."""
    base = {"Key": os.environ.get("LOFIN365_API_KEY", ""), "Type": "json", "pIndex": 1, "pSize": 100}
    sample = sample or {}
    yr_keys = [k for k, v in sample.items() if re.fullmatch(r"(19|20)\d{2}", v)]
    tries = [sample]
    if yr_keys:
        this = dt.date.today().year
        tries = [{**sample, **{k: str(y) for k in yr_keys}} for y in range(this - 1, this - 5, -1)] + [sample]
    last = (None, None, "호출 안 함")
    for extra in tries:
        last = _call(c, svc, {**base, **extra})
        if last[0] is not None:
            return last
    return last


def _call(c: httpx.Client, svc: str, params: dict) -> tuple[pd.DataFrame | None, int | None, str | None]:
    r = c.get(f"{B}/lf/hub/{svc}", params=params)
    try:
        obj = r.json()
    except Exception:  # noqa: BLE001
        return None, None, f"json 아님 {r.status_code}"
    body = obj.get(svc)
    if not body:
        return None, None, json.dumps(obj, ensure_ascii=False)[:160]
    total, rows = None, []
    for part in body:
        for h in part.get("head") or []:
            total = total or h.get("list_total_count")
        rows += part.get("row") or []
    return (pd.DataFrame(rows) if rows else None), total, None if rows else "0행"


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    lk = pd.read_parquet(config.KNOWLEDGE / "expansion" / "site_links.parquet", columns=["id", "host", "link"]).drop_duplicates("id")
    cat = pd.read_parquet(config.PROCESSED / "catalog.parquet", columns=["id", "title"])
    portal = lk[lk["host"].fillna("").str.contains("lofin365")].merge(cat, on="id")
    with httpx.Client(timeout=60, headers={"User-Agent": "Mozilla/5.0"}, follow_redirects=True) as c:
        svcs = catalog(c)
        print(f"지방재정365 API 데이터셋 {len(svcs)} · 서비스명 확인 {sum(1 for s in svcs if s['service'])}", flush=True)
        names = {_norm(s["name"]): s for s in svcs if s["service"]}
        ok = 0
        for r in portal.itertuples():
            t = _norm(str(r.title).split("_", 1)[-1])
            best = difflib.get_close_matches(t, list(names), n=1, cutoff=0.5)
            run = {"id": r.id, "kind": "external", "site": "www.lofin365.go.kr", "link": r.link,
                   "started_at": dt.datetime.now().isoformat(timespec="seconds"), "ops": []}
            if not best:
                run.update({"ok_ops": 0, "error": "지방재정365 데이터셋과 제목으로 짝을 찾지 못함"})
            else:
                s = names[best[0]]
                df, total, err = call(c, s["service"], s.get("sample"))
                if df is None:
                    run.update({"ok_ops": 0, "error": f"{s['service']}: {err}"})
                else:
                    (P / "data" / r.id).mkdir(parents=True, exist_ok=True)
                    df.astype(str).to_parquet(P / "data" / r.id / f"lofin_{dt.date.today():%Y%m%d}.parquet")
                    (P / "stats" / f"{r.id}.json").write_text(json.dumps({s["service"]: col_stats(df)}, ensure_ascii=False, indent=1,
                                                                        default=str), encoding="utf-8")
                    run["ops"] = [{"op": s["service"], "url": f"{B}/lf/hub/{s['service']}", "ok": True, "rows": len(df), "total_count": total,
                                   "columns": list(map(str, df.columns)), "params": {"Type": "json", "pIndex": 1, "pSize": 100},
                                   "note": f"지방재정365 '{s['name']}' (pdtaId {s['pdtaId']}) — 포털 제목과 유사도로 짝지음, Key(query)"}]
                    run["ok_ops"] = 1
                    ok += 1
            run["finished_at"] = dt.datetime.now().isoformat(timespec="seconds")
            (P / "runs" / f"{r.id}.json").write_text(json.dumps(run, ensure_ascii=False, indent=1), encoding="utf-8")
            print(f"  {r.id} {'성공' if run.get('ok_ops') else '실패'} {str(r.title)[:30]} {run.get('error') or run['ops'][0]['op']}"[:150], flush=True)
    print({"포털 링크": len(portal), "성공": ok})


if __name__ == "__main__":
    main()
