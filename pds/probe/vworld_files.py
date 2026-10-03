"""브이월드 공간정보 다운로드(dtmk_ntads) 검증 — 개별공시지가·토지특성·건물연령 같은 핵심 공간정보의 전국 일괄 파일판.

API 주소가 없는 링크형이라 external_sites로는 검증이 안 된다. 브이월드 로그인 세션(secrets/vworld_state.json)으로
목록 첫 쪽에서 가장 작은 CSV(없으면 SHP의 속성표 .dbf)를 하나 받아 행·열·셀 통계를 남긴다 (probe/runs·stats·data).
로그인은 사람이 한다: python -m pds.probe.vworld_files login  → 창에서 직접 로그인하면 세션 저장.
실행: python -m pds.probe.vworld_files [id ...]  (기본: logs/wave4_targets.json의 브이월드 다운로드 링크)
"""
from __future__ import annotations

import asyncio
import datetime as dt
import io
import json
import re
import sys
import zipfile

import pandas as pd

from pds import config
from pds.probe.deep import col_stats
from pds.probe.files import _read

STATE = config.ROOT / "secrets" / "vworld_state.json"
P = config.ROOT / "probe"


async def login(timeout_s: int = 1800) -> None:
    """보이는 창을 띄우고 사람이 로그인하길 기다린다 (아이디·비밀번호를 대신 넣지 않는다)."""
    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        b = await p.chromium.launch(channel="chrome", headless=False)
        ctx = await b.new_context()
        page = await ctx.new_page()
        await page.goto("https://www.vworld.kr/v4po_usrlogin_a001.do", wait_until="domcontentloaded")
        print("Chrome 창에서 브이월드에 로그인해 주세요.", flush=True)
        for _ in range(timeout_s // 3):
            await asyncio.sleep(3)
            try:
                if "로그아웃" in await page.inner_text("body"):
                    await ctx.storage_state(path=str(STATE))
                    print(f"세션 저장: {STATE}", flush=True)
                    break
            except Exception:  # noqa: BLE001 — 이동 중
                pass
        await b.close()


def _size_kb(txt: str) -> float:
    m = re.search(r"용량\s*([\d,\.]+)\s*(KB|MB|GB)", txt)
    if not m:
        return 1e12
    v = float(m.group(1).replace(",", ""))
    return v * {"KB": 1, "MB": 1024, "GB": 1024 ** 2}[m.group(2)]


def _read_any(raw: bytes, name: str) -> pd.DataFrame:
    if raw[:2] == b"PK":
        z = zipfile.ZipFile(io.BytesIO(raw))
        names = [i.filename for i in z.infolist()]
        if "[Content_Types].xml" in names:  # xlsx도 zip이다
            return pd.read_excel(io.BytesIO(raw), dtype=str)
        if any(n.lower().endswith((".csv", ".txt", ".xlsx")) for n in names):
            return _read(raw, name)
        dbf = [n for n in names if n.lower().endswith(".dbf")]
        if dbf:
            import shapefile
            r = shapefile.Reader(dbf=io.BytesIO(z.read(dbf[0])), encoding="cp949")
            return pd.DataFrame(r.records(), columns=[f[0] for f in r.fields[1:]]).astype(str)
        raise ValueError(f"zip 안에 표·dbf 없음: {names[:5]}")
    try:
        return _read(raw, name)
    except ValueError:  # 구분자가 | 이거나 깨진 줄이 섞인 CSV
        for enc in ("cp949", "utf-8-sig"):
            for sep in ("|", ",", "	"):
                try:
                    df = pd.read_csv(io.BytesIO(raw), dtype=str, encoding=enc, sep=sep, on_bad_lines="skip", low_memory=False)
                    if df.shape[1] > 1:
                        return df
                except (UnicodeDecodeError, pd.errors.ParserError):
                    continue
        raise


async def run(items: list[tuple[str, str]]) -> list[dict]:
    from playwright.async_api import async_playwright
    out = []
    async with async_playwright() as p:
        b = await p.chromium.launch(channel="chrome", headless=True)
        ctx = await b.new_context(storage_state=str(STATE), accept_downloads=True)
        page = await ctx.new_page()
        page.on("dialog", lambda d: asyncio.ensure_future(d.dismiss()))
        for dsid, link in items:
            run = {"id": dsid, "kind": "external", "site": "vworld.kr", "link": link,
                   "started_at": dt.datetime.now().isoformat(timespec="seconds"), "ops": []}
            try:
                await page.goto(link, wait_until="networkidle", timeout=60000)
                if "로그인/회원가입" in await page.inner_text("body"):  # 로그인 상태면 머리글이 "마이포털"
                    raise RuntimeError("브이월드 로그인 세션 없음")
                rows = page.locator("li:has(button.down)")
                cand = []
                for k in range(await rows.count()):
                    txt = await rows.nth(k).inner_text()
                    fmt = (await rows.nth(k).locator(".format").inner_text()).strip().upper()
                    cand.append((0 if fmt == "CSV" else 1, _size_kb(txt), k, fmt, " ".join(txt.split())[:80]))
                if not cand:
                    raise ValueError("다운로드 목록 없음")
                _, kb, k, fmt, desc = sorted(cand)[0]
                if kb > 300 * 1024:
                    raise ValueError(f"가장 작은 파일도 큼 ({kb / 1024:.0f}MB)")
                async with page.expect_download(timeout=600000) as dl:
                    await rows.nth(k).locator("button.down").click()
                d = await dl.value
                raw = open(await d.path(), "rb").read()
                df = _read_any(raw, d.suggested_filename)
                cols = list(map(str, df.columns))
                (P / "data" / dsid).mkdir(parents=True, exist_ok=True)
                df.astype(str).head(200000).to_parquet(P / "data" / dsid / f"vworld_{dt.date.today():%Y%m%d}.parquet")
                (P / "stats" / f"{dsid}.json").write_text(json.dumps({"file": col_stats(df.head(200000))}, ensure_ascii=False, indent=1,
                                                                    default=str), encoding="utf-8")
                run["ops"] = [{"op": f"vworld 다운로드 {fmt}", "ok": True, "rows": len(df), "total_count": len(df), "columns": cols,
                               "file": d.suggested_filename, "sample": desc, "attempts": [{"bytes": len(raw)}]}]
                run["ok_ops"] = 1
            except Exception as e:  # noqa: BLE001
                run.update({"ok_ops": 0, "error": f"{type(e).__name__}: {str(e)[:200]}"})
            run["finished_at"] = dt.datetime.now().isoformat(timespec="seconds")
            (P / "runs" / f"{dsid}.json").write_text(json.dumps(run, ensure_ascii=False, indent=1), encoding="utf-8")
            out.append(run)
            print(f"  {dsid} {'성공' if run['ok_ops'] else '실패'} {run.get('error') or run['ops'][0]['rows']}", flush=True)
            if "로그인 세션 없음" in str(run.get("error")):
                break
        await b.close()
    return out


def main(ids: list[str]) -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    if ids == ["login"]:
        asyncio.run(login())
        return
    links = pd.read_parquet(config.KNOWLEDGE / "expansion" / "site_links.parquet", columns=["id", "link"]).drop_duplicates("id")
    link = dict(zip(links["id"], links["link"]))
    if not ids:
        t = json.loads((config.ROOT / "logs" / "wave4_targets.json").read_text(encoding="utf-8"))
        ids = [x["id"] for x in t if "dtmk_ntads" in str(link.get(x["id"]))]
    items = [(i, link[i]) for i in ids if i in link]
    print(f"브이월드 다운로드 {len(items)}건", flush=True)
    r = asyncio.run(run(items))
    print({"대상": len(r), "성공": sum(1 for x in r if x.get("ok_ops"))})


if __name__ == "__main__":
    main(sys.argv[1:])
