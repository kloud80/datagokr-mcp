"""문화공공데이터광장 오픈API 활용신청 — API마다 신청해야 하고, 서비스키가 API마다 다르게 메일로 온다.

사용자가 로그인한 가입 도우미 Chrome(원격 조작 포트 9333)으로 신청서를 넣는다 (사용자 위임, 2026-10-06).
  2단계: 이름·이메일(.env PERSON_NAME·PERSON_MAIL) · 개인 · 연령대 40대(사용자 답) · 소재지(PERSON_ADDRESS의 시도)
  3단계: 개발계정 · 활용목적 기본값 · 업종 기본값 · 서비스 URL · 설명
메일로 온 키는 사용자가 목록으로 준다 → knowledge 밖 secrets/culture_keys.json (API id → 키)로 넣는다.
결과: probe/apply_culture/{api id}.json   실행: python -m pds.probe.culture_apply [링크 수 제한]
"""
from __future__ import annotations

import asyncio
import datetime as dt
import json
import os
import re
import sys

import pandas as pd

from pds import config

OUT = config.ROOT / "probe" / "apply_culture"
URL = "http://bv.bigvalue.co.kr:9001"
SKIP = {"405"}  # 사용자가 직접 신청한 API (키 형식 확인용)
DESC = "공공데이터 전략 도우미(datagokr-mcp) — 공공데이터를 목표에 맞게 고르고 잇는 연구·서비스 개발. 데이터 구조·갱신 확인용 호출."


async def apply_one(page, link: str) -> dict:
    rec = {"link": link, "at": dt.datetime.now().isoformat(timespec="seconds"), "dialogs": []}
    page.on("dialog", lambda d: (rec["dialogs"].append(d.message[:200]), asyncio.ensure_future(d.accept())))
    await page.goto(link, wait_until="networkidle", timeout=60000)
    m = re.search(r"openapiView\.do\?id=(\d+)", page.url)
    if not m:
        rec["result"] = "api 페이지 아님"
        return rec
    rec["api_id"] = m.group(1)
    prev = OUT / f"{rec['api_id']}.json"
    if prev.exists() and json.loads(prev.read_text(encoding="utf-8")).get("result") == "submitted":
        rec["result"] = "이미 신청"
        return rec
    if rec["api_id"] in SKIP:
        rec["result"] = "사용자가 직접 신청"
        return rec
    rec["title"] = (await page.locator("h3, .title, h2").first.inner_text()).strip()[:80] if await page.locator("h3, .title, h2").count() else ""
    html = await page.content()
    rec["endpoint"] = next(iter(re.findall(r"(https?://api\.kcisa\.kr/[\w/.-]+)", html)), None)
    btn = page.get_by_text("활용신청", exact=True).first
    if not await btn.count():
        rec["result"] = "신청 버튼 없음"
        return rec
    await btn.click()
    await page.wait_for_timeout(800)
    sido = (os.getenv("PERSON_ADDRESS", "").split() or [""])[0][:2]
    await page.fill("#inputName", os.getenv("PERSON_NAME", ""))
    await page.fill("#inputEmail", os.getenv("PERSON_MAIL", ""))
    await page.evaluate("""() => { const set = e => { if (e) { e.checked = true; e.dispatchEvent(new Event('change', {bubbles: true})); e.dispatchEvent(new Event('click', {bubbles: true})); } };
        set(document.querySelector('#P0')); set(document.querySelector("[name=ageGroupCode][value='40']")); }""")
    opts = await page.eval_on_selector_all("#location option", "os => os.map(o => [o.value, o.text])")
    val = next((v for v, t in opts if t.startswith(sido)), None)
    if val:
        await page.select_option("#location", val)
    await page.locator("#dialog1_step2 button:has-text('다음')").click()
    await page.wait_for_timeout(800)
    await page.evaluate("""() => { const e = document.querySelector('#D'); if (e) { e.checked = true; e.dispatchEvent(new Event('change', {bubbles: true})); } }""")
    await page.fill("#useCodeDetl", DESC)
    await page.fill("#inputUrl", URL)
    await page.fill("#inputEx", DESC)
    await page.locator("#dialog1_step3 button:has-text('다음')").click()
    await page.wait_for_timeout(2500)
    step4 = page.locator("#dialog1_step4")
    rec["step4"] = re.sub(r"\s+", " ", await step4.inner_text())[:200] if await step4.count() else ""
    rec["result"] = "submitted" if (await step4.is_visible() if await step4.count() else False) else "unknown"
    return rec


async def run(links: list[tuple[str, str]]) -> list[dict]:
    from playwright.async_api import async_playwright
    OUT.mkdir(parents=True, exist_ok=True)
    out = []
    async with async_playwright() as p:
        b = await p.chromium.connect_over_cdp("http://127.0.0.1:9333")
        page = await b.contexts[0].new_page()
        for dsid, link in links:
            try:
                rec = await apply_one(page, link)
            except Exception as e:  # noqa: BLE001
                rec = {"link": link, "result": "error", "error": f"{type(e).__name__}: {str(e)[:150]}"}
            rec["dataset"] = dsid
            name = rec.get("api_id") or dsid
            if rec["result"] == "이미 신청":
                name = f"{name}__{dsid}"
            (OUT / f"{name}.json").write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
            out.append(rec)
            print(f"  {dsid} {rec.get('api_id')} {rec['result']} {rec.get('title', '')[:30]} {' / '.join(rec.get('dialogs') or [])[:80]}", flush=True)
            await page.wait_for_timeout(1000)
        await page.close()
    return out


def main(limit: int | None) -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    lk = pd.read_parquet(config.KNOWLEDGE / "expansion" / "site_links.parquet", columns=["id", "host", "link", "api_kind_label"]).drop_duplicates("id")
    g = lk[(lk["host"] == "culture.go.kr") & (lk["api_kind_label"] == "API_LINK")]
    done = {json.loads(f.read_text(encoding="utf-8")).get("dataset") for f in OUT.glob("*.json")} if OUT.exists() else set()
    links = [(i, l) for i, l in zip(g["id"], g["link"]) if i not in done][:limit]
    print(f"문화 API 신청 {len(links)}건", flush=True)
    r = asyncio.run(run(links))
    from collections import Counter
    print(dict(Counter(x["result"] for x in r)))


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else None)
