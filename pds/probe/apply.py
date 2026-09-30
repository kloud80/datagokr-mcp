"""Phase 2-b 활용신청 — 저장된 포털 세션으로 오픈 API 개발계정 신청 폼을 채워 제출한다 (BUILD-PLAN §2.1 b).

활용목적은 고정 문구(PURPOSE). 상세기능은 전체 선택, 이용허락 동의. 확인/알림 창은 수락하고 메시지를 기록한다.
결과: probe/apply/{id}.json (제출 시각, 심의여부, 알림 메시지, 최종 URL)
"""
from __future__ import annotations

import asyncio
import datetime as dt
import json

from pds import config
from pds.probe.portal import STATE

OUT = config.ROOT / "probe" / "apply"
PURPOSE = ("공공데이터 활용 전략 시스템(PDS) 개발을 위한 데이터 구조·품질 검증입니다. 명세의 오퍼레이션을 최소 파라미터로 호출해 "
           "실제 컬럼·값 분포·갱신 주기를 확인하고, 다른 공공데이터와의 연계 키를 검증합니다. (개발계정, 비상업)")
FORM = "https://www.data.go.kr/tcs/dss/redirectDevAcountRequestForm.do?publicDataPk={pk}&isBusinessApply=undefined"


async def apply_one(page, pk: str) -> dict:
    rec = {"id": pk, "at": dt.datetime.now().isoformat(timespec="seconds"), "dialogs": []}

    async def on_dialog(d):
        rec["dialogs"].append(d.message[:300])
        await d.accept()

    page.on("dialog", on_dialog)
    await page.goto(FORM.format(pk=pk), wait_until="networkidle")
    body = await page.inner_text("body")
    rec["form_url"] = page.url
    if "개발계정 신청" not in body:
        rec["result"] = "no_form"
        rec["body_head"] = body[:400]
        page.remove_listener("dialog", on_dialog)
        return rec
    for key in ("심의여부", "활용기간"):
        i = body.find(key)
        rec[key] = body[i + len(key):i + len(key) + 30].strip().split("\n")[0] if i >= 0 else None
    await page.fill("#prcusePurps", PURPOSE)
    # 라디오·체크박스는 숨김 스타일이라 클릭이 안 먹는 페이지가 있어 스크립트로 체크하고 change 이벤트를 보낸다
    await page.evaluate("""() => {
        const set = e => { if (e && !e.checked) { e.checked = true; e.dispatchEvent(new Event('change', {bubbles: true})); } };
        set(document.querySelector('#radio3'));                                   // 활용목적: 기타
        document.querySelectorAll('input[type=checkbox]:not(#useScopeAgreAt)').forEach(set);  // 상세기능 전체
        set(document.querySelector('#useScopeAgreAt'));                           // 이용허락범위 동의
    }""")
    rec["ops_selected"] = await page.evaluate(
        "[...document.querySelectorAll('input[type=checkbox]:checked')].length")
    await page.get_by_text("활용 신청하기", exact=True).first.click()
    await page.wait_for_timeout(5000)   # 완료 알림이 늦게 뜨는 경우가 있다
    await page.wait_for_load_state("networkidle")
    rec["final_url"] = page.url
    done = any("완료" in m for m in rec["dialogs"])
    rec["result"] = "submitted" if done else ("already" if any("이미" in m for m in rec["dialogs"]) else "unknown")
    page.remove_listener("dialog", on_dialog)
    return rec


async def apply_many(pks: list[str], headless: bool = True) -> list[dict]:
    from playwright.async_api import async_playwright
    OUT.mkdir(parents=True, exist_ok=True)
    out = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(channel="chrome", headless=headless)
        ctx = await browser.new_context(storage_state=str(STATE))
        page = await ctx.new_page()
        for pk in pks:
            try:
                rec = await apply_one(page, pk)
            except Exception as e:  # noqa: BLE001
                rec = {"id": pk, "result": "error", "error": repr(e)[:300]}
            (OUT / f"{pk}.json").write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
            out.append(rec)
            await page.wait_for_timeout(1500)
        await ctx.storage_state(path=str(STATE))
        await browser.close()
    return out


if __name__ == "__main__":
    import sys
    print(json.dumps(asyncio.run(apply_many(sys.argv[1:])), ensure_ascii=False, indent=1))
