"""가입 도우미 — 사이트 가입 페이지를 Chrome으로 띄우고 빈칸(이름·아이디·이메일·전화·주소)만 .env 값으로 채운다.

사람이 하는 것: 약관 동의 · 비밀번호 · 휴대폰/이메일 인증 · 가입 버튼. 이 도구는 그 칸들을 건드리지 않는다.
  python -m pds.probe.signup open <url>   별도 프로필 Chrome(원격 조작 포트 9333)으로 연다
  python -m pds.probe.signup fill         지금 보이는 페이지의 빈칸을 채운다 (채운 칸 이름만 출력, 값은 출력하지 않음)
.env: PERSON_NAME · PERSON_TEL · PERSON_MAIL · PERSON_ADDRESS, 아이디는 DATA_GO_KR_ID.
"""
from __future__ import annotations

import asyncio
import os
import re
import subprocess
import sys
from pathlib import Path

from pds import config  # noqa: F401 — .env 로드

PORT = 9333
PROFILE = config.ROOT / "secrets" / "signup_profile"
CHROME = next((p for p in (r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                           r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe") if Path(p).exists()), "chrome")
SKIP = re.compile(r"(pass|pwd|비밀번호|암호|주민|jumin|resident|인증번호|certi|auth|captcha|보안문자|otp)", re.I)
RULES = [  # (판정 정규식, 값 종류) — 위에서부터
    (re.compile(r"(아이디|user_?id|login_?id|mber_?id|^id$|memid|usrid|userid)", re.I), "id"),
    (re.compile(r"(이메일|e-?mail|mail)", re.I), "mail"),
    (re.compile(r"(휴대|핸드폰|전화|연락처|mobile|phone|tel|hp|cell)", re.I), "tel"),
    (re.compile(r"(상세주소|주소|addr)", re.I), "addr"),
    (re.compile(r"(이름|성명|^name$|user_?nm|mber_?nm|usr_?nm|_nm$|username)", re.I), "name"),
]


def _vals() -> dict:
    return {"id": os.getenv("DATA_GO_KR_ID", ""), "name": os.getenv("PERSON_NAME", ""), "mail": os.getenv("PERSON_MAIL", ""),
            "tel": re.sub(r"\D", "", os.getenv("PERSON_TEL", "")), "addr": os.getenv("PERSON_ADDRESS", "")}


def open_url(url: str) -> None:
    PROFILE.mkdir(parents=True, exist_ok=True)
    subprocess.Popen([CHROME, f"--remote-debugging-port={PORT}", f"--user-data-dir={PROFILE}", "--no-first-run", url])
    print("Chrome을 열었습니다. 약관 동의를 마치고 정보 입력 화면이 나오면 알려 주세요.")


JS = r"""() => {
  const out = [];
  const vis = e => !!(e.offsetWidth || e.offsetHeight || e.getClientRects().length);
  document.querySelectorAll('input, select').forEach((e, i) => {
    if (!vis(e) || e.disabled || e.readOnly) return;
    const t = (e.type || '').toLowerCase();
    if (e.tagName === 'INPUT' && !['text', 'email', 'tel', 'number', ''].includes(t)) return;
    let label = '';
    if (e.id) { const l = document.querySelector(`label[for="${e.id}"]`); if (l) label = l.innerText; }
    if (!label) { const th = e.closest('tr')?.querySelector('th'); if (th) label = th.innerText; }
    if (!label) { const dt = e.closest('dd')?.previousElementSibling; if (dt) label = dt.innerText; }
    e.setAttribute('data-pds-i', i);
    out.push({i, tag: e.tagName, name: e.name || '', id: e.id || '', ph: e.placeholder || '', aria: e.getAttribute('aria-label') || '',
              title: e.title || '', label: (label || '').trim().slice(0, 30), val: e.value || '', max: e.maxLength,
              opts: e.tagName === 'SELECT' ? [...e.options].map(o => o.value + '|' + o.text) : []});
  });
  return out;
}"""


def _plan(fields: list[dict], v: dict) -> list[tuple[dict, str, str]]:
    plan = []
    groups: dict[str, list[dict]] = {}
    for f in fields:
        hint = " ".join([f["name"], f["id"], f["ph"], f["aria"], f["title"], f["label"]])
        if SKIP.search(hint) or (f["val"] and f["tag"] == "INPUT"):
            continue
        kind = next((k for rx, k in RULES if rx.search(hint)), None)
        if kind:
            groups.setdefault(kind, []).append(f)
    for kind, fs in groups.items():
        inputs = [f for f in fs if f["tag"] == "INPUT"]
        if kind == "tel" and len(inputs) == 3:  # 010 / 1234 / 5678
            t = v["tel"]
            parts = [t[:3], t[3:-4], t[-4:]]
            plan += [(f, kind, p) for f, p in zip(inputs, parts)]
        elif kind == "mail" and len(inputs) >= 2:  # 아이디 @ 도메인
            local, _, dom = v["mail"].partition("@")
            plan += [(inputs[0], kind, local), (inputs[1], kind, dom)]
        elif inputs:
            plan.append((inputs[0], kind, v[kind]))
    return [(f, k, x) for f, k, x in plan if x]


async def fill() -> None:
    from playwright.async_api import async_playwright
    v = _vals()
    async with async_playwright() as p:
        b = await p.chromium.connect_over_cdp(f"http://127.0.0.1:{PORT}")
        pages = [pg for c in b.contexts for pg in c.pages]
        page = pages[-1]
        done = []
        for fr in page.frames:
            try:
                fields = await fr.evaluate(JS)
            except Exception:  # noqa: BLE001
                continue
            for f, kind, val in _plan(fields, v):
                loc = fr.locator(f'[data-pds-i="{f["i"]}"]')
                try:
                    await loc.fill(val[: f["max"]] if f.get("max") and f["max"] > 0 else val)
                    done.append(f"{kind}: {f['label'] or f['name'] or f['id']}")
                except Exception as e:  # noqa: BLE001
                    done.append(f"{kind}: 실패 {type(e).__name__}")
        print(f"페이지: {page.url[:90]}")
        print("채운 칸:", ", ".join(done) if done else "없음 (정보 입력 화면이 아니거나 이미 채워짐)")
        print("남은 것: 비밀번호 · 약관 · 인증 · 주소 검색(우편번호) · 가입 버튼은 직접")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    cmd = sys.argv[1] if len(sys.argv) > 1 else "fill"
    if cmd == "open":
        open_url(sys.argv[2])
    else:
        asyncio.run(fill())
