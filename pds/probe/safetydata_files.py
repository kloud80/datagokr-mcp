"""재난안전데이터공유플랫폼(safetydata.go.kr) 검증 — 데이터 상세의 '샘플 다운로드'(첫 100건, 로그인 세션)로 행·열·셀 통계.

전수는 데이터별 이용신청 후 오픈API(/V2/api/DSSP-IF-…?serviceKey=)로 — 검증에는 샘플로 충분하다.
세션: secrets/safetydata_state.json (사람이 가입·로그인한 브라우저에서 저장). 실행: python -m pds.probe.safetydata_files [id ...]
"""
from __future__ import annotations

import asyncio
import datetime as dt
import json
import re
import sys

import pandas as pd

from pds import config
from pds.probe.deep import col_stats
from pds.probe.vworld_files import _read_any

STATE = config.ROOT / "secrets" / "safetydata_state.json"
P = config.ROOT / "probe"


async def run(items: list[tuple[str, str]]) -> list[dict]:
    from playwright.async_api import async_playwright
    out = []
    async with async_playwright() as p:
        b = await p.chromium.launch(channel="chrome", headless=True)
        ctx = await b.new_context(storage_state=str(STATE), accept_downloads=True)
        page = await ctx.new_page()
        page.on("dialog", lambda d: asyncio.ensure_future(d.dismiss()))
        for dsid, link in items:
            run = {"id": dsid, "kind": "external", "site": "www.safetydata.go.kr", "link": link,
                   "started_at": dt.datetime.now().isoformat(timespec="seconds"), "ops": []}
            try:
                await page.goto(link, wait_until="networkidle", timeout=60000)
                html = await page.content()
                api = next(iter(re.findall(r"https?://www\.safetydata\.go\.kr/V2/api/(DSSP-IF-\d+)", html)), None)
                btn = page.locator("button[id^=fileDataDownload]").first
                if not await btn.count():
                    raise ValueError("샘플 다운로드 없음")
                async with page.expect_download(timeout=120000) as dl:
                    await btn.click()
                d = await dl.value
                df = _read_any(open(await d.path(), "rb").read(), d.suggested_filename)
                (P / "data" / dsid).mkdir(parents=True, exist_ok=True)
                df.astype(str).to_parquet(P / "data" / dsid / f"safetydata_{dt.date.today():%Y%m%d}.parquet")
                (P / "stats" / f"{dsid}.json").write_text(json.dumps({"sample": col_stats(df)}, ensure_ascii=False, indent=1, default=str),
                                                         encoding="utf-8")
                run["ops"] = [{"op": api or "sample", "url": f"https://www.safetydata.go.kr/V2/api/{api}" if api else None, "ok": True,
                               "rows": len(df), "columns": list(map(str, df.columns)), "file": d.suggested_filename,
                               "note": "샘플 다운로드(첫 100건, 로그인) — 전수는 데이터별 이용신청 후 오픈API serviceKey"}]
                run["ok_ops"] = 1
            except Exception as e:  # noqa: BLE001
                run.update({"ok_ops": 0, "error": f"{type(e).__name__}: {str(e)[:200]}"})
            run["finished_at"] = dt.datetime.now().isoformat(timespec="seconds")
            (P / "runs" / f"{dsid}.json").write_text(json.dumps(run, ensure_ascii=False, indent=1), encoding="utf-8")
            out.append(run)
            print(f"  {dsid} {'성공' if run['ok_ops'] else '실패'} {run.get('error') or run['ops'][0]['rows']}", flush=True)
        await b.close()
    return out


def main(ids: list[str]) -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    lk = pd.read_parquet(config.KNOWLEDGE / "expansion" / "site_links.parquet", columns=["id", "host", "link"]).drop_duplicates("id")
    g = lk[lk["host"].fillna("").str.contains("safetydata")]
    items = [(i, l) for i, l in zip(g["id"], g["link"]) if not ids or i in ids]
    items = [(i, l) for i, l in items if not ((P / "runs" / f"{i}.json").exists()
                                              and json.loads((P / "runs" / f"{i}.json").read_text(encoding="utf-8")).get("ok_ops"))]
    print(f"재난안전데이터 {len(items)}건", flush=True)
    r = asyncio.run(run(items))
    print({"대상": len(r), "성공": sum(1 for x in r if x.get("ok_ops"))})


if __name__ == "__main__":
    main(sys.argv[1:])
