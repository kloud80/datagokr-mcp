"""공공데이터포털(data.go.kr) 세션 — 최초 1회 사람이 보안문자를 풀어 로그인하고 storage_state를 저장, 이후 에이전트는 그 세션만 쓴다.

비밀번호는 .env(DATA_GO_KR_ID/PW)에서 읽어 입력칸에 채우기만 한다. 보안문자는 자동화하지 않는다 (BUILD-PLAN §2.2).
세션 파일: secrets/data_go_kr_state.json (gitignore)
"""
from __future__ import annotations

import asyncio
import os
import time

from pds import config

STATE = config.ROOT / "secrets" / "data_go_kr_state.json"
LOGIN_URL = "https://www.data.go.kr/uim/login/loginView.do"


async def login_interactive(timeout_s: int = 600) -> str:
    """보이는 Chrome 창을 띄워 아이디·비밀번호를 채우고, 사람이 보안문자를 넣고 로그인하길 기다린다."""
    from playwright.async_api import async_playwright
    STATE.parent.mkdir(exist_ok=True)
    async with async_playwright() as p:
        browser = await p.chromium.launch(channel="chrome", headless=False)
        ctx = await browser.new_context()
        page = await ctx.new_page()
        await page.goto(LOGIN_URL, wait_until="networkidle")
        await page.fill("#inputUsername", os.getenv("DATA_GO_KR_ID", ""))
        await page.fill("#inputPassword", os.getenv("DATA_GO_KR_PW", ""))
        await page.focus("#captcha")
        print("Chrome 창에서 보안문자를 입력하고 로그인 버튼을 눌러 주세요.", flush=True)
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            await asyncio.sleep(2)
            if "www.data.go.kr" in page.url and "login" not in page.url.lower():
                await page.goto("https://www.data.go.kr/iim/main/mypageMain.do", wait_until="networkidle")
                if "login" not in page.url.lower():
                    await ctx.storage_state(path=str(STATE))
                    print(f"로그인 세션 저장: {STATE}", flush=True)
                    await browser.close()
                    return str(STATE)
        await browser.close()
        raise TimeoutError("로그인 대기 시간 초과")


def has_session() -> bool:
    return STATE.exists()


if __name__ == "__main__":
    asyncio.run(login_interactive())
