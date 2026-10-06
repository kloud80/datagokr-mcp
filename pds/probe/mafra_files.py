"""농림축산식품 공공데이터 포털(data.mafra.go.kr) 파일 검증 — 상세 페이지 첨부 파일(가장 최근 CSV·XLSX)을 로그인 없이 받는다.

오픈API형은 인증키(회원가입 후 발급)가 필요해 여기서는 파일만. 실행: python -m pds.probe.mafra_files [id ...]
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
from pds.probe.vworld_files import _read_any

P = config.ROOT / "probe"


async def run(items: list[tuple[str, str]]) -> list[dict]:
    from playwright.async_api import async_playwright
    out = []
    async with async_playwright() as p:
        b = await p.chromium.launch(channel="chrome", headless=True)
        page = await (await b.new_context(accept_downloads=True)).new_page()
        page.on("dialog", lambda d: asyncio.ensure_future(d.dismiss()))
        for dsid, link in items:
            run = {"id": dsid, "kind": "external", "site": "data.mafra.go.kr", "link": link,
                   "started_at": dt.datetime.now().isoformat(timespec="seconds"), "ops": []}
            try:
                await page.goto(link, wait_until="networkidle", timeout=60000)
                html = await page.content()
                grid = next(iter(re.findall(r"openapi/sample/\w+/(Grid_\w+)/", html)), None)
                if grid:  # 오픈API — 신청 없이 sample 키로 견본 5행 (전수는 인증키 + 데이터별 신청)
                    r = httpx.get(f"http://211.237.50.150:7080/openapi/sample/json/{grid}/1/5", timeout=40)
                    obj = r.json().get(grid) or {}
                    rows = obj.get("row") or []
                    if not rows:
                        raise ValueError(f"API 견본 0행: {str(obj.get('result'))[:100]}")
                    df = pd.DataFrame(rows)
                    (P / "data" / dsid).mkdir(parents=True, exist_ok=True)
                    df.astype(str).to_parquet(P / "data" / dsid / f"mafra_{dt.date.today():%Y%m%d}.parquet")
                    (P / "stats" / f"{dsid}.json").write_text(json.dumps({grid: col_stats(df)}, ensure_ascii=False, indent=1, default=str),
                                                             encoding="utf-8")
                    run["ops"] = [{"op": grid, "url": f"http://211.237.50.150:7080/openapi/{{KEY}}/json/{grid}/1/1000", "ok": True,
                                   "rows": len(df), "total_count": obj.get("totalCnt"), "columns": list(map(str, df.columns)),
                                   "note": "sample 키 견본 5행 — 전수는 인증키(회원가입 시 자동 발급) + 데이터별 오픈API 신청(자동승인)"}]
                    run["ok_ops"] = 1
                    raise StopIteration
                files = page.locator("a[href^='javascript:filedownload']")
                n = await files.count()
                if not n:
                    raise ValueError("첨부 파일 없음 (오픈API 전용일 수 있음 — 인증키 필요)")
                names = [await files.nth(k).inner_text() for k in range(n)]
                k = max((k for k, x in enumerate(names) if x.lower().endswith((".csv", ".xlsx", ".xls", ".zip"))), default=n - 1)
                async with page.expect_download(timeout=120000) as dl:
                    await files.nth(k).click()
                d = await dl.value
                df = _read_any(open(await d.path(), "rb").read(), d.suggested_filename)
                (P / "data" / dsid).mkdir(parents=True, exist_ok=True)
                df.astype(str).head(100000).to_parquet(P / "data" / dsid / f"mafra_{dt.date.today():%Y%m%d}.parquet")
                (P / "stats" / f"{dsid}.json").write_text(json.dumps({"file": col_stats(df.head(100000))}, ensure_ascii=False, indent=1,
                                                                    default=str), encoding="utf-8")
                run["ops"] = [{"op": "file", "ok": True, "rows": len(df), "total_count": len(df), "columns": list(map(str, df.columns)),
                               "file": d.suggested_filename, "note": f"첨부 {n}개 중 최근 파일"}]
                run["ok_ops"] = 1
            except StopIteration:
                pass
            except Exception as e:  # noqa: BLE001
                run.update({"ok_ops": 0, "error": f"{type(e).__name__}: {str(e)[:200]}"})
            run["finished_at"] = dt.datetime.now().isoformat(timespec="seconds")
            (P / "runs" / f"{dsid}.json").write_text(json.dumps(run, ensure_ascii=False, indent=1), encoding="utf-8")
            out.append(run)
            print(f"  {dsid} {'성공' if run['ok_ops'] else '실패'} {run.get('error') or run['ops'][0]['rows']}"[:140], flush=True)
        await b.close()
    return out


def main(ids: list[str]) -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    lk = pd.read_parquet(config.KNOWLEDGE / "expansion" / "site_links.parquet", columns=["id", "host", "link"]).drop_duplicates("id")
    g = lk[lk["host"] == "data.mafra.go.kr"]
    items = [(i, l) for i, l in zip(g["id"], g["link"]) if (not ids or i in ids) and not (
        (P / "runs" / f"{i}.json").exists() and json.loads((P / "runs" / f"{i}.json").read_text(encoding="utf-8")).get("ok_ops"))]
    print(f"농식품 포털 {len(items)}건", flush=True)
    r = asyncio.run(run(items))
    print({"대상": len(r), "성공": sum(1 for x in r if x.get("ok_ops"))})


if __name__ == "__main__":
    main(sys.argv[1:])
