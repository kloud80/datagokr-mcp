"""나이스 교육정보 개방 포털(open.neis.go.kr) — SNS 로그인은 사람이 보이는 Chrome 창에서 하고, 세션만 저장한다.
세션: secrets/neis_state.json
"""
from __future__ import annotations

import asyncio
import time

from pds import config

STATE = config.ROOT / "secrets" / "neis_state.json"


async def main(timeout_s: int = 900) -> None:
    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        b = await p.chromium.launch(channel="chrome", headless=False)
        ctx = await b.new_context()
        pg = await ctx.new_page()
        await pg.goto("https://open.neis.go.kr/portal/mainPage.do", wait_until="domcontentloaded")
        print("Chrome 창에서 나이스 포털에 SNS로 로그인해 주세요 (로그인 버튼 → 네이버/카카오 등).", flush=True)
        end = time.time() + timeout_s
        while time.time() < end:
            await asyncio.sleep(3)
            for page in ctx.pages:
                try:
                    if "open.neis.go.kr" in page.url and "로그아웃" in await page.inner_text("body"):
                        await ctx.storage_state(path=str(STATE))
                        print(f"로그인 세션 저장: {STATE}", flush=True)
                        await b.close()
                        return
                except Exception:  # noqa: BLE001 — 로그인 중 페이지 전환
                    pass
        await b.close()
        raise TimeoutError("로그인 대기 시간 초과")


if __name__ == "__main__":
    asyncio.run(main())
