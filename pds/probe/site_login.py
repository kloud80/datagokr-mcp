"""기관 사이트 로그인 세션 저장 — 사람이 직접 로그인한다 (아이디·비밀번호를 대신 넣지 않는다).

python -m pds.probe.site_login gg   → 경기데이터드림 창을 띄우고, 로그인되면 secrets/gg_state.json 저장
로그인 판정: 화면에 '로그아웃' 또는 '마이페이지'가 보이면.
"""
from __future__ import annotations

import asyncio
import sys

from pds import config

SITES = {"gg": ("https://data.gg.go.kr/portal/mainPage.do", "gg_state.json")}


async def login(site: str, timeout_s: int = 3600) -> None:
    from playwright.async_api import async_playwright
    url, name = SITES[site]
    out = config.ROOT / "secrets" / name
    async with async_playwright() as p:
        b = await p.chromium.launch(channel="chrome", headless=False)
        ctx = await b.new_context()
        page = await ctx.new_page()
        await page.goto(url, wait_until="domcontentloaded")
        print("Chrome 창에서 직접 로그인해 주세요.", flush=True)
        for _ in range(timeout_s // 3):
            await asyncio.sleep(3)
            try:
                texts = [await pg.inner_text("body") for pg in ctx.pages]
            except Exception:  # noqa: BLE001 — 이동 중
                continue
            if any("로그아웃" in t or "마이페이지" in t for t in texts):
                await asyncio.sleep(3)
                await ctx.storage_state(path=str(out))
                print(f"세션 저장: {out}", flush=True)
                break
        else:
            print("로그인 대기 시간 초과", flush=True)
        await b.close()


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    asyncio.run(login(sys.argv[1] if len(sys.argv) > 1 else "gg"))
