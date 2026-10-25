"""링크형 파일(FILE_LINK) 범용 검증 — 키가 필요 없는 기관 사이트 (python -m pds.probe.link_files [targets 로그]).

포털 '바로가기'가 가리키는 기관 페이지(site_links.parquet)를 headless Chrome으로 열고
  ① 파일 링크(.csv·.xlsx·.xls·.zip·.txt·.json) → 직접 받기
  ② '다운로드·내려받기·첨부·CSV·엑셀' 단추 → 눌러서 받기 (최대 MAX_TRY개)
  ③ 둘 다 없으면 페이지 안의 HTML 통계표 — 머리글이 있고 게시판 목록(제목·작성자·첨부…)이 아니며 숫자 열이 있는 표만.
     method "html_table"로 구분해 남긴다 (화면 배치용 표·게시판 목록은 데이터가 아니다)
받은 파일은 pds.probe.files와 같은 방식으로 읽어 probe/data·runs·stats에 쓴다. 한 행 이상, 두 열 이상이어야 성공.
기록은 다른 사이트 검증기와 같은 모양(kind "external" · site · link · ops) — 키가 없으니 ops에 호출 url을 두지 않는다.
사이트별 전용 검증기(external_sites·*_sites)가 있는 호스트는 그쪽이 맡는다. 실행 중 PDS_SHARD="i/k"로 나눠 돌린다.
PDS_LINK_IDS=파일(한 줄에 id 하나)을 주면 그 id만 — 전용 검증기가 못 한 것(서울 통계표·파일 등)을 이 도구로 다시 받을 때.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import io
import json
import os
import re
import sys
from urllib.parse import urljoin

import pandas as pd

from pds import config
from pds.probe.deep import col_stats
from pds.probe.files import _read

P = config.ROOT / "probe"
EXT = re.compile(r"\.(csv|xlsx|xls|zip|txt|json)(\?|$|&)", re.I)
BAD_EXT = re.compile(r"\.(pdf|hwp|hwpx|docx?|pptx?|jpg|png|gif)(\?|$)", re.I)
BTN = re.compile(r"다운로드|내려받기|첨부|csv|엑셀|xlsx?|파일받기", re.I)
MAX_TRY = 4
BOARD = re.compile(r"제목|작성자|조회|첨부|등록일|글쓴이|게시")
TIMEOUT = 45000


def _ok(df: pd.DataFrame | None) -> bool:
    return df is not None and len(df) >= 1 and df.shape[1] >= 2


async def _candidates(page) -> list[dict]:
    """파일 링크와 다운로드 단추 — 본문 프레임까지 (iframe 안 게시판이 흔하다)."""
    out, seen = [], set()
    for fr in page.frames:
        try:
            items = await fr.eval_on_selector_all(
                "a, button, input[type=button], span[onclick], img[onclick]",
                """els => els.map((e, i) => ({i, tag: e.tagName, href: e.getAttribute('href') || '',
                    text: (e.innerText || e.value || e.getAttribute('title') || e.getAttribute('alt') || '').trim().slice(0, 80),
                    onclick: (e.getAttribute('onclick') || '').slice(0, 200)}))""")
        except Exception:  # noqa: BLE001
            continue
        for it in items:
            href, text, oc = it["href"], it["text"], it["onclick"]
            if BAD_EXT.search(href) or BAD_EXT.search(text):
                continue
            score = 0
            if EXT.search(href) or EXT.search(text):
                score = 3
            elif BTN.search(text) or re.search(r"down|file", oc + href, re.I) and BTN.search(text + oc):
                score = 2
            elif re.search(r"fileDown|download|filedown|atchFile", oc + href, re.I):
                score = 1
            if not score:
                continue
            key = (fr.url, href, text, oc)
            if key in seen:
                continue
            seen.add(key)
            out.append({**it, "frame": fr, "score": score})
    return sorted(out, key=lambda x: -x["score"])[:MAX_TRY]


async def _try(page, c: dict) -> tuple[bytes, str] | None:
    href = c["href"]
    if href and not href.startswith(("javascript", "#")) and EXT.search(href) and not c["onclick"]:
        r = await page.context.request.get(urljoin(c["frame"].url, href), timeout=TIMEOUT)
        if r.ok:
            name = href.split("?")[0].rsplit("/", 1)[-1]
            cd = r.headers.get("content-disposition", "")
            m = re.search(r"filename\*?=(?:UTF-8'')?\"?([^\";]+)", cd)
            return await r.body(), (m.group(1) if m else name)
        return None
    el = (await c["frame"].query_selector_all("a, button, input[type=button], span[onclick], img[onclick]"))[c["i"]]
    async with page.expect_download(timeout=TIMEOUT) as di:
        try:
            await el.click(force=True, timeout=15000)
        except Exception:  # noqa: BLE001 — 숨은 단추는 스크립트로 누른다
            await el.evaluate("e => e.click()")
    d = await di.value
    path = await d.path()
    return open(path, "rb").read(), d.suggested_filename


async def _html_table(page) -> pd.DataFrame | None:
    best = None
    for fr in page.frames:
        try:
            html = await fr.content()
            for t in pd.read_html(io.StringIO(html)):
                if best is None or t.size > best.size:
                    best = t
        except Exception:  # noqa: BLE001
            continue
    if best is None or len(best) < 3 or best.shape[1] < 2:
        return None
    best.columns = [" ".join(map(str, c)) if isinstance(c, tuple) else str(c) for c in best.columns]
    heads = " ".join(best.columns)
    if all(re.fullmatch(r"\d+", c) for c in best.columns) or BOARD.search(heads):
        return None
    num = max((pd.to_numeric(best[c].astype(str).str.replace(",", ""), errors="coerce").notna().mean() for c in best.columns), default=0)
    return best if num >= 0.6 else None


async def run_one(page, dsid: str, link: str) -> dict:
    run = _new(dsid, link)
    errs = []
    try:
        if EXT.search(link):  # 링크 자체가 파일
            r = await page.context.request.get(link, timeout=TIMEOUT)
            raw, name = await r.body(), link.split("?")[0].rsplit("/", 1)[-1]
            return _save(run, _read(raw, name), name, raw, "download", link)
        await page.goto(link, wait_until="domcontentloaded", timeout=TIMEOUT)
        try:
            await page.wait_for_load_state("networkidle", timeout=15000)
        except Exception:  # noqa: BLE001
            pass
        df, name, raw, method = None, None, b"", None
        for c in await _candidates(page):
            try:
                got = await _try(page, c)
                if not got:
                    continue
                raw, name = got
                df = _read(raw, name)
                if _ok(df):
                    method = "download"
                    break
                df = None
            except Exception as e:  # noqa: BLE001
                errs.append(f"{c['text'][:20]}: {repr(e)[:120]}")
        if df is None:
            df = await _html_table(page)
            if df is not None:
                method, name = "html_table", "page"
        if df is None:
            raise ValueError("파일 링크·다운로드 단추·표 모두 없음" + (f" ({'; '.join(errs[:3])})" if errs else ""))
        return _save(run, df, name, raw, method, page.url)
    except Exception as e:  # noqa: BLE001
        run.update({"error": repr(e)[:400], "ok_ops": 0, "ops": []})
    (P / "runs" / f"{run['id']}.json").write_text(json.dumps(run, ensure_ascii=False, indent=1), encoding="utf-8")
    return run


def _new(dsid: str, link: str) -> dict:
    from urllib.parse import urlparse
    return {"id": dsid, "kind": "external", "site": urlparse(link).netloc, "link": link, "tool": "link_files",
            "started_at": dt.datetime.now().isoformat(timespec="seconds")}


def normalize() -> int:
    """초기판 기록(kind "link_file")을 지금 모양으로 바꾼다."""
    n = 0
    for f in (P / "runs").glob("*.json"):
        if f.stat().st_size > 20000:
            continue
        r = json.loads(f.read_text(encoding="utf-8"))
        if r.get("kind") != "link_file":
            continue
        new = _new(r["id"], r["url"]) | {"started_at": r["started_at"], "ok_ops": r.get("ok_ops", 0)}
        for k in ("file", "bytes", "rows", "columns", "method", "final_url", "error"):
            if k in r:
                new[k] = r[k]
        new["ops"] = [{"op": o["op"], "ok": True, "rows": o["rows"], "columns": o["columns"], "file": r.get("file"),
                       "note": f"기관 사이트에서 받음 ({r.get('final_url')})"} for o in r.get("ops") or []]
        f.write_text(json.dumps(new, ensure_ascii=False, indent=1), encoding="utf-8")
        n += 1
    return n


def _save(run: dict, df: pd.DataFrame, name: str, raw: bytes, method: str, final_url: str) -> dict:
    if not _ok(df):
        raise ValueError(f"표가 비었거나 열이 하나뿐: {name}")
    dsid = run["id"]
    df = df.astype(str)
    d = P / "data" / dsid
    d.mkdir(parents=True, exist_ok=True)
    sample = df.head(100000)
    sample.to_parquet(d / f"file_{dt.date.today():%Y%m%d}.parquet")
    (P / "stats" / f"{dsid}.json").write_text(json.dumps({"file": col_stats(sample)}, ensure_ascii=False, indent=1, default=str),
                                             encoding="utf-8")
    run.update({"file": name, "bytes": len(raw), "rows": len(df), "columns": list(map(str, df.columns)), "ok_ops": 1, "method": method,
                "final_url": final_url,
                "ops": [{"op": method, "ok": True, "rows": len(df), "columns": list(map(str, df.columns)), "file": name,
                         "note": f"기관 사이트에서 받음 ({final_url})"}]})
    (P / "runs" / f"{dsid}.json").write_text(json.dumps(run, ensure_ascii=False, indent=1), encoding="utf-8")
    return run


def _special_hosts() -> set[str]:
    from pds.probe import external_sites as ex
    return {h.removeprefix("www.") for h in ex.SITES}


async def main(log: str) -> None:
    from playwright.async_api import async_playwright
    t = json.loads((config.ROOT / "logs" / log).read_text(encoding="utf-8"))
    links = pd.read_parquet(config.KNOWLEDGE / "expansion" / "site_links.parquet", columns=["id", "link", "host"]).drop_duplicates("id")
    cov = json.loads((config.KNOWLEDGE / "expansion" / "site_coverage.json").read_text(encoding="utf-8"))
    free = {x["host"] for x in cov["sites"] if x["key"] == "키 불필요"}
    lk = {r.id: (r.link, r.host) for r in links.itertuples()}
    only = set(open(os.environ["PDS_LINK_IDS"], encoding="utf-8").read().split()) if os.environ.get("PDS_LINK_IDS") else None
    today = os.environ.get("PDS_SINCE") or dt.date.today().isoformat()  # 이 날짜 이후 기록은 건너뛴다
    todo = []
    for x in t:
        if x["kind"] not in ("FILE_LINK", "API_LINK") or x["id"] not in lk or (only is None and x["kind"] != "FILE_LINK"):
            continue
        link, host = lk[x["id"]]
        if not isinstance(link, str):
            continue
        if only is not None:
            if x["id"] not in only:
                continue
        elif host not in free or host in _special_hosts():
            continue
        p = P / "runs" / f"{x['id']}.json"
        if p.exists() and json.loads(p.read_text(encoding="utf-8")).get("started_at", "") >= today:
            continue
        todo.append((x["id"], link))
    shard = os.environ.get("PDS_SHARD")
    if shard:
        i, k = map(int, shard.split("/"))
        todo = todo[i::k]
    print(f"링크형 파일 {len(todo)}건", flush=True)
    ok = 0
    async with async_playwright() as p:
        b = await p.chromium.launch(channel="chrome", headless=True)
        ctx = await b.new_context(accept_downloads=True, ignore_https_errors=True, locale="ko-KR")
        page = await ctx.new_page()
        page.on("dialog", lambda d: asyncio.ensure_future(d.accept()))
        for n, (dsid, link) in enumerate(todo, 1):
            try:
                r = await asyncio.wait_for(run_one(page, dsid, link), timeout=180)
            except Exception as e:  # noqa: BLE001 — 한 건이 브라우저를 붙잡으면 새 페이지로
                r = {"ok_ops": 0, "error": repr(e)[:200]}
                (P / "runs" / f"{dsid}.json").write_text(json.dumps(_new(dsid, link) | r | {"ops": []}, ensure_ascii=False, indent=1), encoding="utf-8")
                try:
                    await page.close()
                except Exception:  # noqa: BLE001
                    pass
                page = await ctx.new_page()
                page.on("dialog", lambda d: asyncio.ensure_future(d.accept()))
            ok += bool(r.get("ok_ops"))
            if n % 25 == 0:
                print(f"  {n}/{len(todo)} 성공 {ok}", flush=True)
        await b.close()
    print({"대상": len(todo), "성공": ok}, flush=True)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    if sys.argv[1:] == ["normalize"]:
        print("변환", normalize())
    else:
        asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "wave7_targets.json"))
