"""기상청 API허브(apihub.kma.go.kr) 활용신청 + 검증 — 키는 하나(KMA_APIHUB_API_KEY), API마다 활용신청(즉시 승인)이 필요하다.

포털 링크(urlRedirect.do?seqApi=&seqApiSub=) → API 목록 화면(apiList.do)의 API별 신청 번호(openAPIUse(N))와 샘플 주소(authKey={인증키입력})를 모은다.
신청: 사용자가 로그인한 가입 도우미 Chrome(포트 9333)에서 /requestUseApi POST (분야 학술/연구 CD00009 · 목적 학술/연구 CD00023 · 설명) — 사용자 위임 2026-10-06.
검증: 샘플 주소를 키로 불러 본문이 403(활용신청 필요)·오류가 아니면 성공. 실행: python -m pds.probe.kma_sites
"""
from __future__ import annotations

import asyncio
import datetime as dt
import json
import os
import re
import sys
from urllib.parse import parse_qs, urlparse

import httpx
import pandas as pd

from pds import config
from pds.probe.deep import _items_json, _items_xml, col_stats

P = config.ROOT / "probe"
PURPOSE = "공공데이터 전략 도우미(datagokr-mcp) 연구 — 데이터 구조·갱신 확인용 호출"


def _rows(text: str) -> list[dict] | None:
    t = text.lstrip()
    if t.startswith(("{", "[")):
        try:
            return _items_json(json.loads(t))
        except Exception:  # noqa: BLE001
            return None
    if t.startswith("<"):
        return _items_xml(text)
    lines = [l for l in text.splitlines() if l.strip() and not l.startswith("#")]  # typ01 고정폭·CSV 텍스트
    if len(lines) >= 2:
        return [{"line": l[:300]} for l in lines[:100]]
    return None


async def main_async() -> None:
    from playwright.async_api import async_playwright
    key = os.environ.get("KMA_APIHUB_API_KEY", "")
    lk = pd.read_parquet(config.KNOWLEDGE / "expansion" / "site_links.parquet", columns=["id", "host", "link"]).drop_duplicates("id")
    g = lk[lk["host"] == "apihub.kma.go.kr"]
    applied: set[int] = set()
    ok_n = 0
    async with async_playwright() as p:
        b = await p.chromium.connect_over_cdp("http://127.0.0.1:9333")
        page = await b.contexts[0].new_page()
        page.on("dialog", lambda d: asyncio.ensure_future(d.accept()))
        with httpx.Client(timeout=60) as c:
            for dsid, link in zip(g["id"], g["link"]):
                q = parse_qs(urlparse(link).query)
                sa, ss = q.get("seqApi", [""])[0], q.get("seqApiSub", [""])[0]
                run = {"id": dsid, "kind": "external", "site": "apihub.kma.go.kr", "link": link,
                       "started_at": dt.datetime.now().isoformat(timespec="seconds"), "ops": []}
                try:
                    await page.goto(f"https://apihub.kma.go.kr/apiList.do?seqApi={sa}&seqApiSub={ss}", wait_until="networkidle")
                    html, text = await page.content(), await page.inner_text("body")
                    nums = [int(x) for x in dict.fromkeys(re.findall(r"openAPIUse\((\d+)\)", html))]
                    import html as _h
                    samples = [u + "{인증키입력}" for u in dict.fromkeys(re.findall(r"(https://apihub\.kma\.go\.kr/api/[^\s\"<]+?authKey=)", _h.unescape(html)))]
                    # 신청 버튼이 없으면(로그인 풀림) 신청은 건너뛰고 샘플로만 검증 — 앞선 실행에서 이미 신청됐을 수 있다
                    for n in nums[:12]:
                        if n in applied:
                            continue
                        await page.goto(f"https://apihub.kma.go.kr/APIUse.do?seqApi={n}", wait_until="networkidle")
                        res = await page.evaluate("""([n, purpose]) => new Promise(res => {
                            const token = $("meta[name='_csrf']").attr("content"), header = $("meta[name='_csrf_header']").attr("content");
                            $.ajax({url: '/requestUseApi', type: 'POST', contentType: 'application/json; charset=utf-8',
                                    data: JSON.stringify({seqApi: n, useSpcltCd: 'CD00009', usePurpsCd: 'CD00023', purpsUseEtc: purpose, wbzpsUsePurpsCd: null}),
                                    beforeSend: x => x.setRequestHeader(header, token)})
                              .done(d => res('ok ' + JSON.stringify(d).slice(0, 80))).fail(e => res('fail ' + e.status + ' ' + (e.responseText || '').slice(0, 80)));
                        })""", [n, PURPOSE])
                        applied.add(n)
                        run.setdefault("applied", []).append({"seqApi": n, "result": res})
                        await page.wait_for_timeout(300)
                    df, used = None, None
                    for s in samples[:6]:
                        r = c.get(s.replace("{인증키입력}", key))
                        if r.status_code == 200 and "활용신청이 필요" not in r.text and "error" not in r.text[:200].lower():
                            rows = _rows(r.text)
                            if rows:
                                df, used = pd.DataFrame(rows), s
                                break
                    if df is None:
                        raise ValueError("샘플 호출에서 행을 받지 못함")
                    op = urlparse(used).path.rsplit("/", 1)[-1]
                    (P / "data" / dsid).mkdir(parents=True, exist_ok=True)
                    df.astype(str).to_parquet(P / "data" / dsid / f"kma_{dt.date.today():%Y%m%d}.parquet")
                    (P / "stats" / f"{dsid}.json").write_text(json.dumps({op: col_stats(df)}, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
                    run["ops"] = [{"op": op, "url": used.split("?")[0], "ok": True, "rows": len(df), "columns": list(map(str, df.columns)),
                                   "params": dict(x.split("=", 1) for x in urlparse(used).query.split("&") if "=" in x and not x.startswith("authKey")),
                                   "note": "기상청 API허브 — 키 하나 + API별 활용신청(즉시 승인), authKey(query)"}]
                    run["ok_ops"] = 1
                    ok_n += 1
                except Exception as e:  # noqa: BLE001
                    run.update({"ok_ops": 0, "error": f"{type(e).__name__}: {str(e)[:150]}"})
                run["finished_at"] = dt.datetime.now().isoformat(timespec="seconds")
                text_ = json.dumps(run, ensure_ascii=False, indent=1)
                (P / "runs" / f"{dsid}.json").write_text(text_.replace(key, "***") if key else text_, encoding="utf-8")
                print(f"  {dsid} {'성공' if run.get('ok_ops') else '실패'} 신청 {len(run.get('applied') or [])} {run.get('error', '')[:60]}", flush=True)
        await page.close()
    print({"대상": len(g), "성공": ok_n, "신청한 API": len(applied)})


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    asyncio.run(main_async())
