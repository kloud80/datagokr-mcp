"""경기데이터드림(data.gg.go.kr) 링크형 검증 — 포털의 경기도 링크형 1,747건 (python -m pds.probe.gg_sites [id ...]).

상세 페이지(selectServicePage.do?infId=…)에서 오픈API 서비스명(openapi.gg.go.kr/<서비스>)을 찾아 인증키 없이 부른다 —
키 없이도 견본 행이 나온다(전수는 인증키 필요, 무료 즉시 발급). API가 없는 데이터는 로그인 세션(secrets/gg_state.json)으로
시트 파일을 받는다. 결과는 probe/runs·stats·data, targets 상태는 sync4/별도 갱신.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import json
import re
import sys

import httpx
import pandas as pd

from pds import config
from pds.probe.deep import col_stats

P = config.ROOT / "probe"
STATE = config.ROOT / "secrets" / "gg_state.json"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/140 Safari/537.36"}
# 같은 개방 포털 솔루션(selectServicePage.do?infId=, searchSheetData.do)을 쓰는 사이트 — PDS_SITE로 고른다
SITES = {
    "gg": {"host": "data.gg.go.kr", "api": "https://openapi.gg.go.kr/{svc}", "rx": r"https?://openapi\.gg\.go\.kr/(\w+)",
           "key_env": None, "state": "gg_state.json", "sheet": "https://data.gg.go.kr/portal/data/sheet/searchSheetData.do"},
    "gm": {"host": "data.gm.go.kr", "api": "https://data.gm.go.kr/openapi/{svc}", "rx": r"data\.gm\.go\.kr/openapi/(\w+)",
           "key_env": None, "state": None, "sheet": "https://data.gm.go.kr/portal/data/sheet/searchSheetData.do"},
    "assembly": {"host": "open.assembly.go.kr", "api": "https://open.assembly.go.kr/portal/openapi/{svc}",
                 "rx": r"open\.assembly\.go\.kr/portal/openapi/(\w+)", "key_env": "OPEN_ASSEMBLY_API_KEY", "state": None,
                 "sheet": "https://open.assembly.go.kr/portal/data/sheet/searchSheetData.do"},
}
import os as _os
SITE = SITES[_os.environ.get("PDS_SITE", "gg")]


def _save(dsid: str, df: pd.DataFrame, run: dict) -> None:
    (P / "data" / dsid).mkdir(parents=True, exist_ok=True)
    df.astype(str).head(100000).to_parquet(P / "data" / dsid / f"gg_{dt.date.today():%Y%m%d}.parquet")
    (P / "stats" / f"{dsid}.json").write_text(json.dumps({run["ops"][0]["op"]: col_stats(df.head(100000))}, ensure_ascii=False, indent=1,
                                                         default=str), encoding="utf-8")


def call_api(c: httpx.Client, svc: str) -> tuple[pd.DataFrame | None, int | None, str | None]:
    params = {"Type": "json", "pIndex": 1, "pSize": 100}
    if SITE["key_env"] and _os.environ.get(SITE["key_env"]):
        params["KEY"] = _os.environ[SITE["key_env"]]
    r = c.get(SITE["api"].format(svc=svc), params=params, timeout=40)
    try:
        obj = r.json()
    except Exception:  # noqa: BLE001
        return None, None, f"json 아님 status {r.status_code}"
    if svc not in obj:
        return None, None, json.dumps(obj.get("RESULT") or obj, ensure_ascii=False)[:200]
    head, rows, total = obj[svc][0].get("head") or [], [], None
    for h in head:
        total = total or h.get("list_total_count")
    for part in obj[svc][1:]:
        rows += part.get("row") or []
    return (pd.DataFrame(rows) if rows else None), total, None if rows else "0행"


async def run(items: list[tuple[str, str]]) -> list[dict]:
    from playwright.async_api import async_playwright
    out = []
    async with async_playwright() as p:
        b = await p.chromium.launch(channel="chrome", headless=True)
        st = config.ROOT / "secrets" / SITE["state"] if SITE["state"] else None
        ctx = await b.new_context(storage_state=str(st) if st and st.exists() else None, accept_downloads=True)
        page = await ctx.new_page()
        page.on("dialog", lambda d: asyncio.ensure_future(d.dismiss()))
        with httpx.Client(headers=UA, follow_redirects=True) as c:
            for dsid, link in items:
                run = {"id": dsid, "kind": "external", "site": SITE["host"], "link": link,
                       "started_at": dt.datetime.now().isoformat(timespec="seconds"), "ops": []}
                try:
                    sheet = None
                    try:
                        async with page.expect_response(lambda r: "searchSheetData" in r.url, timeout=45000) as resp:
                            await page.goto(link, wait_until="domcontentloaded", timeout=60000)
                        sheet = await (await resp.value).json()
                    except Exception:  # noqa: BLE001 — 시트가 없는 데이터 (API 전용 등)
                        await page.wait_for_load_state("networkidle")
                    html = await page.content()
                    svcs = [x for x in dict.fromkeys(re.findall(SITE["rx"], html)) if x != "main"]
                    df, total, err = None, None, "오픈API 없음"
                    for svc in svcs[:3]:
                        df, total, err = call_api(c, svc)
                        if df is not None:
                            run["ops"] = [{"op": svc, "url": SITE["api"].format(svc=svc), "ok": True, "rows": len(df),
                                           "total_count": total, "columns": list(map(str, df.columns)),
                                           "params": {"Type": "json", "pIndex": 1, "pSize": 100},
                                           "note": "인증키 KEY(query)" if SITE["key_env"] else "인증키 없이 견본 — 전수는 KEY"}]
                            break
                    if df is None and sheet and sheet.get("Data"):  # 페이지의 시트 데이터 (searchSheetData.do, 앞 100행)
                        df = pd.DataFrame(sheet["Data"])
                        total = next((v for k, v in sheet.items() if k.lower() in ("total", "totalcnt", "total_count")), None)
                        run["ops"] = [{"op": "sheet", "url": SITE["sheet"], "ok": True,
                                       "rows": len(df), "total_count": total, "columns": list(map(str, df.columns)),
                                       "note": "상세 페이지 시트 (앞 100행) — 전체는 파일 다운로드·오픈API"}]
                    if df is None:  # 첨부 파일형 (srvCd F) — 파일 목록의 '다운로드'
                        link_dl = page.locator("a:has-text('다운로드'), button:has-text('다운로드')").first
                        if await link_dl.count():
                            try:
                                async with page.expect_download(timeout=90000) as dl:
                                    await link_dl.click()
                                d = await dl.value
                                from pds.probe.vworld_files import _read_any
                                df = _read_any(open(await d.path(), "rb").read(), d.suggested_filename)
                                run["ops"] = [{"op": "file", "ok": True, "rows": len(df), "total_count": len(df),
                                               "columns": list(map(str, df.columns)), "file": d.suggested_filename}]
                            except Exception as ex:  # noqa: BLE001
                                err = f"파일 다운로드 실패: {type(ex).__name__}: {str(ex)[:80]}"
                    if df is None:
                        raise ValueError(err)
                    _save(dsid, df, run)
                    run["ok_ops"] = 1
                except Exception as e:  # noqa: BLE001
                    run.update({"ok_ops": 0, "error": f"{type(e).__name__}: {str(e)[:200]}"})
                run["finished_at"] = dt.datetime.now().isoformat(timespec="seconds")
                (P / "runs" / f"{dsid}.json").write_text(json.dumps(run, ensure_ascii=False, indent=1), encoding="utf-8")
                out.append(run)
                print(f"  {dsid} {'성공' if run['ok_ops'] else '실패'} {run.get('error') or run['ops'][0]['op']}"[:140], flush=True)
        await b.close()
    return out


def main(ids: list[str]) -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    import os
    lk = pd.read_parquet(config.KNOWLEDGE / "expansion" / "site_links.parquet", columns=["id", "host", "link"]).drop_duplicates("id")
    g = lk[lk["host"] == SITE["host"]]
    items = [(i, l) for i, l in zip(g["id"], g["link"]) if not ids or i in ids]
    shard = os.environ.get("PDS_SHARD")
    if shard:
        a, k = map(int, shard.split("/"))
        items = items[a::k]
    today = dt.date.today().isoformat()
    items = [(i, l) for i, l in items if not ((P / "runs" / f"{i}.json").exists() and
                                              json.loads((P / "runs" / f"{i}.json").read_text(encoding="utf-8")).get("ok_ops"))]  # 이미 성공한 것만 건너뜀
    print(f"{SITE['host']} {len(items)}건", flush=True)
    r = asyncio.run(run(items))
    print({"대상": len(r), "성공": sum(1 for x in r if x.get("ok_ops"))})


if __name__ == "__main__":
    main(sys.argv[1:])
