"""구형(Swagger 없는) 오픈 API의 요청변수·출력결과 — 상세 페이지에 처음부터 들어 있는 첫 오퍼레이션 표를 읽는다 (로그인 불필요).

포털의 오퍼레이션별 상세 요청(/tcs/dss/selectApiDetailFunction.do)은 2026-09-30 기준 404라, 첫 오퍼레이션 표를 템플릿으로 삼고
나머지 오퍼레이션은 이름과 요청주소(페이지의 apis.data.go.kr URL)만 기록한다. 결과는 probe/specs/{id}.json operations (source='detail_table').
"""
from __future__ import annotations

import asyncio
import json
import re

from pds import config

SPECS = config.ROOT / "probe" / "specs"
TABLES_JS = ("ts => ts.map(t => ({cap: (t.querySelector('caption')||{}).innerText || '', "
             "rows: [...t.querySelectorAll('tr')].map(r => [...r.querySelectorAll('th,td')].map(c => c.innerText.trim()))}))")


def _parse(tables: list[dict]) -> tuple[list[dict], list[dict]]:
    params, fields = [], []
    for t in tables:
        rows = t["rows"]
        if len(rows) < 2 or not any("항목명" in h for h in rows[0]):
            continue
        head, body = rows[0], rows[1:]
        en = next((i for i, h in enumerate(head) if "영문" in h), 0)
        kr = next((i for i, h in enumerate(head) if "국문" in h), 1)
        sample = next((i for i, h in enumerate(head) if "샘플" in h), None)
        req = next((i for i, h in enumerate(head) if "구분" in h), None)
        is_req = "요청" in t["cap"] or (not params and "출력" not in t["cap"])
        for r in body:
            if len(r) <= en or not r[en]:
                continue
            item = {"name": " ".join(r[en].split()), "desc": r[kr] if kr < len(r) else "",
                    "example": r[sample] if sample is not None and sample < len(r) else None}
            if req is not None and req < len(r):
                item["required"] = r[req].startswith("1") or "필수" in r[req]
            (params if is_req else fields).append(item)
    return params, fields


async def read_ops(page, url: str) -> list[dict]:
    await page.goto(url, wait_until="networkidle")
    opts = await page.eval_on_selector_all("#open_api_detail_select option", "os => os.map(o => o.innerText.trim())")
    tables = await page.eval_on_selector_all("#apiDetailFunctionDiv table", TABLES_JS)
    text = await page.eval_on_selector("#apiDetailFunctionDiv", "e => e.innerText")
    html = await page.content()
    urls = sorted(set(re.findall(r"https?://apis\.data\.go\.kr/[\w/.\-]+", html)), key=len, reverse=True)
    first_url = (re.search(r"https?://apis\.data\.go\.kr/[\w/.\-]+", text) or [None])[0] if text else None
    params, fields = _parse(tables)
    ops = []
    for i, name in enumerate(opts or ["op"]):
        ops.append({"path": first_url if i == 0 else "", "method": "GET", "name": name,
                    "params": params, "response_fields": [{"name": f["name"], "desc": f["desc"]} for f in fields] if i == 0 else [],
                    "params_from": "first_operation_table" if i else "table"})
    return [o for o in ops if o["path"]] + [{"path": u, "method": "GET", "name": "(요청주소)", "params": params, "response_fields": []}
                                         for u in urls if u.count("/") >= 5 and all(u != o["path"] for o in ops)]


async def run(ids: list[str]) -> None:
    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        b = await p.chromium.launch(channel="chrome", headless=True)
        page = await b.new_page()
        for dsid in ids:
            path = SPECS / f"{dsid}.json"
            spec = json.loads(path.read_text(encoding="utf-8"))
            if spec.get("swagger") or "openapi.do" not in spec["url"]:
                continue
            try:
                spec["operations"], spec["source"] = await read_ops(page, spec["url"]), "detail_table"
            except Exception as e:  # noqa: BLE001
                spec["detail_error"] = repr(e)[:300]
            path.write_text(json.dumps(spec, ensure_ascii=False, indent=1), encoding="utf-8")
        await b.close()


if __name__ == "__main__":
    import sys
    asyncio.run(run(sys.argv[1:]))
