"""Phase 2-f/g 파일형 데이터(표준데이터·파일데이터) 다운로드·셀 통계.

표준데이터(standard.do): 로그인 세션으로 CSV 다운로드 버튼(#stdCsvDownloadBtn)을 눌러 받는다.
파일데이터(fileData.do): 파일 목록의 첫 다운로드 버튼. 인코딩은 utf-8-sig → cp949 순으로 시도.
출력: probe/data/{id}/file_{date}.parquet · probe/runs/{id}.json · probe/stats/{id}.json (API run과 같은 형식)
"""
from __future__ import annotations

import asyncio
import datetime as dt
import io
import json

import pandas as pd

from pds import config
from pds.probe.deep import col_stats
from pds.probe.portal import STATE

P = config.ROOT / "probe"


def _read(raw: bytes, name: str) -> pd.DataFrame:
    if raw[:2] == b"PK" and not name.lower().endswith((".xlsx",)):  # zip: 안의 가장 큰 표 파일
        import zipfile
        z = zipfile.ZipFile(io.BytesIO(raw))
        members = [i for i in z.infolist() if i.filename.lower().endswith((".csv", ".xlsx", ".xls", ".txt"))
                   or any(i.filename.encode("cp437", "ignore").decode("cp949", "ignore").lower().endswith(x) for x in (".csv", ".xlsx"))]
        if not members:
            raise ValueError(f"zip 안에 표 파일 없음: {[i.filename for i in z.infolist()][:5]}")
        m = max(members, key=lambda i: i.file_size)
        inner = m.filename
        try:
            inner = m.filename.encode("cp437").decode("cp949")
        except UnicodeError:
            pass
        return _read(z.read(m), inner)
    if name.lower().endswith((".xls", ".xlsx")):
        return pd.read_excel(io.BytesIO(raw), dtype=str)
    for enc in ("utf-8-sig", "cp949", "euc-kr"):
        try:
            return pd.read_csv(io.BytesIO(raw), dtype=str, encoding=enc, low_memory=False)
        except (UnicodeDecodeError, pd.errors.ParserError):
            continue
    raise ValueError("encoding/parse failed")


class CaptchaRequired(RuntimeError):
    """포털 다운로드 한도 초과 — 보안문자는 사람이 푼다 (자동화하지 않음)."""


async def download_filedata(page, dsid: str, url: str) -> tuple[bytes, str]:
    """fileData.do: 파일 정보 조회(selectFileDataDownload) → 한도 확인(check-limit) → fileDownload. 세션 쿠키로 요청."""
    import re as _re
    from urllib.parse import quote
    await page.goto(url, wait_until="domcontentloaded", timeout=60000)  # 다운로드 함수 인자는 HTML에 있다 — 화면 요청이 다 끝날 때까지 기다리지 않는다
    html = await page.content()
    m = _re.search(r"fn_fileDataDown\('(\d+)',\s*'([^']+)',\s*'([^']*)',\s*'(\d+)',\s*'(\d+)'\)", html)
    if not m:
        raise ValueError("다운로드 버튼(fn_fileDataDown) 없음")
    pk, detail_pk, atch, sn, _ = m.groups()
    req = page.context.request
    r = await req.post("https://www.data.go.kr/tcs/dss/selectFileDataDownload.do", form={
        "publicDataDetailPk": detail_pk, "publicDataPk": pk, "atchFileId": atch, "fileDetailSn": sn, "publicDataTyCode": "PR0051"})
    info = json.loads(await r.text())
    if not info.get("status"):
        raise ValueError(f"파일 정보 조회 실패: {info.get('error')}")
    atch, sn = info["atchFileId"], info["fileDetailSn"]
    name = (info.get("dataSetFileDetailInfo") or {}).get("dataNm") or dsid
    lim = await req.post("https://www.data.go.kr/cmm/cmm/check-limit.json", form={"atchFileId": atch, "fileDetailSn": str(sn)})
    if lim.status == 403 or (lim.ok and (await lim.json()).get("needCaptcha")):
        raise CaptchaRequired("다운로드 한도 — 보안문자 필요")
    f = await req.get(f"https://www.data.go.kr/cmm/cmm/fileDownload.do?atchFileId={atch}&fileDetailSn={sn}&dataNm={quote(name)}")
    raw = await f.body()
    cd = f.headers.get("content-disposition", "")
    fm = _re.search(r"filename\*?=(?:UTF-8'')?\"?([^\";]+)", cd)
    fname = (fm.group(1) if fm else name)
    from urllib.parse import unquote
    fname = unquote(fname)
    try:  # 헤더의 UTF-8 바이트가 latin1로 읽힌 경우
        fname = fname.encode("latin1").decode("utf-8")
    except UnicodeError:
        pass
    tmp = P / "data" / dsid / f"_raw_{_re.sub(r'[\/:*?\"<>|]', '_', fname)}"
    tmp.parent.mkdir(parents=True, exist_ok=True)
    tmp.write_bytes(raw)
    return raw, fname


async def download(page, dsid: str, url: str) -> tuple[bytes, str]:
    if "fileData.do" in url:
        return await download_filedata(page, dsid, url)
    await page.goto(url, wait_until="networkidle")
    sel = "#stdCsvDownloadBtn"
    if not await page.locator(sel).count():  # 전국 표준데이터 중 일부는 CSV 대신 기관 API로 연결(stdLinkBtn)만 둔다
        raise ValueError("CSV 다운로드 없음 — 표준데이터가 연계 API로 제공됨 (stdLinkBtn)")
    async with page.expect_download(timeout=180000) as di:
        await page.locator(sel).first.click(force=True, timeout=120000)  # 전국 표준데이터는 버튼이 늦게 뜬다
    d = await di.value
    tmp = P / "data" / dsid / f"_raw_{d.suggested_filename}"
    tmp.parent.mkdir(parents=True, exist_ok=True)
    await d.save_as(str(tmp))
    return tmp.read_bytes(), d.suggested_filename


async def run_files(items: list[tuple[str, str]]) -> list[dict]:
    from playwright.async_api import async_playwright
    out = []
    async with async_playwright() as p:
        b = await p.chromium.launch(channel="chrome", headless=True)
        ctx = await b.new_context(storage_state=str(STATE), accept_downloads=True)
        page = await ctx.new_page()
        page.on("dialog", lambda d: asyncio.ensure_future(d.accept()))
        for dsid, url in items:
            run = {"id": dsid, "kind": "file", "url": url, "started_at": dt.datetime.now().isoformat(timespec="seconds")}
            try:
                raw, name = await download(page, dsid, url)
                df = _read(raw, name)
                run.update({"file": name, "bytes": len(raw), "rows": len(df), "columns": list(map(str, df.columns)), "ok_ops": 1})
                sample = df.head(100000)  # 큰 파일은 앞 10만 행으로 저장·통계 (전체 행 수는 rows에)
                sample.astype(str).to_parquet(P / "data" / dsid / f"file_{dt.date.today():%Y%m%d}.parquet")  # 날짜·혼합형 열도 저장되게
                (P / "stats").mkdir(parents=True, exist_ok=True)
                (P / "stats" / f"{dsid}.json").write_text(json.dumps({"file": col_stats(sample)}, ensure_ascii=False, indent=1, default=str),
                                                          encoding="utf-8")
                run["ops"] = [{"op": "file", "ok": True, "rows": len(df), "total_count": len(df), "columns": run["columns"],
                               "attempts": [{"bytes": len(raw)}]}]
            except CaptchaRequired as e:
                run.update({"error": str(e), "ok_ops": 0, "ops": [], "captcha": True})
                (P / "runs" / f"{dsid}.json").write_text(json.dumps(run, ensure_ascii=False, indent=1), encoding="utf-8")
                out.append(run)
                break  # 한도에 걸리면 이후 다운로드도 막힌다 — 사람에게 넘긴다
            except Exception as e:  # noqa: BLE001
                run.update({"error": repr(e)[:300], "ok_ops": 0, "ops": []})
            (P / "runs").mkdir(parents=True, exist_ok=True)
            (P / "runs" / f"{dsid}.json").write_text(json.dumps(run, ensure_ascii=False, indent=1), encoding="utf-8")
            out.append(run)
        await b.close()
    return out


# ── 브라우저 없이 받기 (7차 확대) ─────────────────────────────────────────────
# fileData.do 화면 HTML은 로그인 없이 보이고, 다운로드 세 단계(정보 조회 → 한도 확인 → 받기)는 세션 쿠키만 있으면 된다.
# 브라우저로 화면을 여는 데 건당 6~15초, 띄우는 데 수십 초가 들던 것이 0.5초 안팎으로 준다. 표준데이터(standard.do)는 단추를 눌러야 해서 브라우저로.
BIG = 150 * 2**20  # 이보다 큰 CSV는 앞 10만 행만 읽는다 — 통째로 읽으면 메모리를 수 GB 쓴다


def read_capped(raw: bytes, name: str) -> pd.DataFrame:
    if len(raw) <= BIG:
        return _read(raw, name)
    if name.lower().endswith((".csv", ".txt")):
        for enc in ("utf-8-sig", "cp949"):
            try:
                return pd.read_csv(io.BytesIO(raw), dtype=str, encoding=enc, nrows=100000, low_memory=False)
            except (UnicodeDecodeError, pd.errors.ParserError):
                continue
    raise ValueError(f"파일이 너무 큼({len(raw) >> 20}MB) — CSV가 아니라 앞부분만 읽을 수 없다")


def http_client():
    import httpx
    jar = httpx.Cookies()
    for c in json.loads(STATE.read_text(encoding="utf-8"))["cookies"]:
        jar.set(c["name"], c["value"], domain=c["domain"], path=c["path"])
    return httpx.Client(cookies=jar, timeout=180, follow_redirects=True, headers={"User-Agent": "Mozilla/5.0 (pds-probe)"})


def download_http(c, dsid: str, url: str) -> tuple[bytes, str]:
    import re as _re
    html = c.get(url).text
    m = _re.search(r"fn_fileDataDown\('(\d+)',\s*'([^']+)',\s*'([^']*)',\s*'(\d+)',\s*'(\d+)'\)", html)
    if not m:
        raise ValueError("다운로드 버튼(fn_fileDataDown) 없음")
    pk, detail_pk, atch, sn, _ = m.groups()
    info = c.post("https://www.data.go.kr/tcs/dss/selectFileDataDownload.do", data={
        "publicDataDetailPk": detail_pk, "publicDataPk": pk, "atchFileId": atch, "fileDetailSn": sn, "publicDataTyCode": "PR0051"}).json()
    if not info.get("status"):
        raise ValueError(f"파일 정보 조회 실패: {info.get('error')}")
    atch, sn = info["atchFileId"], info["fileDetailSn"]
    name = (info.get("dataSetFileDetailInfo") or {}).get("dataNm") or dsid
    lim = c.post("https://www.data.go.kr/cmm/cmm/check-limit.json", data={"atchFileId": atch, "fileDetailSn": str(sn)})
    if lim.status_code == 403 or (lim.is_success and lim.json().get("needCaptcha")):
        raise CaptchaRequired("다운로드 한도 — 보안문자 필요")
    f = c.get("https://www.data.go.kr/cmm/cmm/fileDownload.do", params={"atchFileId": atch, "fileDetailSn": sn, "dataNm": name})
    f.raise_for_status()
    from urllib.parse import unquote
    fm = _re.search(r"filename\*?=(?:UTF-8'')?\"?([^\";]+)", f.headers.get("content-disposition", ""))
    fname = unquote(fm.group(1)) if fm else name
    try:
        fname = fname.encode("latin1").decode("utf-8")
    except UnicodeError:
        pass
    raw = f.content
    tmp = P / "data" / dsid / f"_raw_{_re.sub(r'[\/:*?\"<>|]', '_', fname)}"
    tmp.parent.mkdir(parents=True, exist_ok=True)
    tmp.write_bytes(raw)
    return raw, fname


def run_files_http(items: list[tuple[str, str]]) -> list[dict]:
    """fileData.do만 — 기록 모양은 run_files와 같다. 한도(보안문자)에 걸리면 멈춘다."""
    out = []
    with http_client() as c:
        for dsid, url in items:
            run = {"id": dsid, "kind": "file", "url": url, "started_at": dt.datetime.now().isoformat(timespec="seconds")}
            try:
                raw, name = download_http(c, dsid, url)
                df = read_capped(raw, name)
                run.update({"file": name, "bytes": len(raw), "rows": len(df), "columns": list(map(str, df.columns)), "ok_ops": 1})
                sample = df.head(100000)
                sample.astype(str).to_parquet(P / "data" / dsid / f"file_{dt.date.today():%Y%m%d}.parquet")
                (P / "stats").mkdir(parents=True, exist_ok=True)
                (P / "stats" / f"{dsid}.json").write_text(json.dumps({"file": col_stats(sample)}, ensure_ascii=False, indent=1, default=str),
                                                          encoding="utf-8")
                run["ops"] = [{"op": "file", "ok": True, "rows": len(df), "total_count": len(df), "columns": run["columns"],
                               "attempts": [{"bytes": len(raw)}]}]
            except CaptchaRequired as e:
                run.update({"error": str(e), "ok_ops": 0, "ops": [], "captcha": True})
                (P / "runs" / f"{dsid}.json").write_text(json.dumps(run, ensure_ascii=False, indent=1), encoding="utf-8")
                out.append(run)
                break
            except Exception as e:  # noqa: BLE001
                run.update({"error": repr(e)[:300], "ok_ops": 0, "ops": []})
            (P / "runs").mkdir(parents=True, exist_ok=True)
            (P / "runs" / f"{dsid}.json").write_text(json.dumps(run, ensure_ascii=False, indent=1), encoding="utf-8")
            out.append(run)
    return out
