"""KIPRIS Plus(plus.kipris.or.kr, 한국특허정보원) 검증 — 포털 링크형 서비스 페이지의 REST 오퍼레이션을 샘플 인자로 부른다.

1. 서비스 페이지 /portal/data/service/<DBII>/view.do → 오퍼레이션 목록 detailPage('<ADI>',…)·setServiceNm('<서비스>','<오퍼레이션>')
2. 오퍼레이션 상세 POST /portal/data/service/<DBII>/<ADI>/ajaxOperation.do (bCode) → 입력값(샘플) 요청 주소
3. 샘플 주소의 accessKey를 키로 바꿔 호출 → XML items 아래 반복 레코드를 표로
키 하나로 모든 서비스가 되지 않는다 — 서비스마다 장바구니 → 신청(무료·유료)이 필요하고, 신청 전에는 resultCode 101
(AccessKey&ServiceID Is Not Registered). BULK만 있는 서비스는 REST 오퍼레이션이 없다.
키 변수: KIPRIS_API_KEY (오타 KIPRIS_APY_KEY도 읽는다). 응답·기록에 키를 싣지 않는다.
실행: python -m pds.probe.kipris_sites [id…]
"""
from __future__ import annotations

import datetime as dt
import html
import json
import os
import re
import sys
import time
import xml.etree.ElementTree as ET
from collections import Counter
from urllib.parse import parse_qsl, urlsplit

import httpx
import pandas as pd

from pds import config
from pds.probe.deep import col_stats, save_run

P = config.ROOT / "probe"
B = "https://plus.kipris.or.kr"
MAX_OPS = 4


def key() -> str:
    return (os.environ.get("KIPRIS_API_KEY") or os.environ.get("KIPRIS_APY_KEY") or "").strip()


def operations(c: httpx.Client, link: str) -> tuple[str | None, list[dict]]:
    m = re.search(r"(DBII_\d+)", link)
    if not m:
        return None, []
    h = c.get(f"{B}/portal/data/service/{m.group(1)}/view.do?menuNo=200101&subTab=SC003&entYn=N").text  # 링크의 탭 인자가 달라도 REST 탭으로
    ops = [{"adi": a, "service": s, "op": o} for a, s, o in
           re.findall(r"detailPage\('(ADI_\d+)','SC002'\);setServiceNm\('(\w+)','(\w+)'\)", h)]
    return m.group(1), ops


def sample_url(c: httpx.Client, dbii: str, adi: str) -> str | None:
    h = c.post(f"{B}/portal/data/service/{dbii}/{adi}/ajaxOperation.do?menuNo=200101&entYn=N&scode=SC002", data={"bCode": dbii}).text
    m = re.search(r'id="xmlTextarea"[^>]*>([^<]+)<', h)
    return html.unescape(m.group(1)).strip() if m else None


def _rows(root: ET.Element) -> list[dict]:
    """items 아래에서 잎(텍스트)만 가진 요소들 중 가장 많이 반복되는 태그를 레코드로."""
    items = root.find(".//items")
    if items is None:
        return []
    cand = [e for e in items.iter() if len(e) and all(len(ch) == 0 for ch in e)]
    if not cand:
        return []
    tag = Counter(e.tag for e in cand).most_common(1)[0][0]
    return [{ch.tag: (ch.text or "").strip() for ch in e} for e in cand if e.tag == tag]


def call(c: httpx.Client, url: str) -> tuple[pd.DataFrame | None, str | None, dict]:
    sp = urlsplit(url)
    params = {k: v for k, v in parse_qsl(sp.query, keep_blank_values=True) if k != "accessKey"}
    time.sleep(0.3)
    r = c.get(f"http://{sp.netloc}{sp.path}", params={**params, "accessKey": key()})
    try:
        root = ET.fromstring(r.content)
    except ET.ParseError:
        return None, f"XML 아님 {r.status_code}", params
    code, msg = (root.findtext(".//resultCode") or "").strip(), (root.findtext(".//resultMsg") or "").strip()
    if code not in ("", "00", "0"):  # 오류 응답에도 빈 껍데기(transferCount 0 · totCnt '')가 붙어 온다 — 표로 읽지 않는다
        return None, f"resultCode {code} {msg}", params
    rows = [r for r in _rows(root) if any(v not in ("", "0") for v in r.values())]
    if len(rows) and len(rows[0]) >= 2:
        return pd.DataFrame(rows), None, params
    return None, "0행(값이 빈 응답)", params


def run_one(c: httpx.Client, dsid: str, link: str) -> dict:
    run = {"id": dsid, "kind": "external", "site": "plus.kipris.or.kr", "link": link, "started_at": dt.datetime.now().isoformat(timespec="seconds"),
           "ops": []}
    dbii, ops = operations(c, link)
    errs = []
    if not dbii:
        run.update({"ok_ops": 0, "error": "링크가 KIPRIS Plus 서비스 페이지가 아님"})
    elif not ops:
        run.update({"ok_ops": 0, "error": f"{dbii} REST 오퍼레이션 없음 (BULK 전용 — 장바구니 신청 후 파일)"})
    for o in ops[:MAX_OPS]:
        url = sample_url(c, dbii, o["adi"])
        if not url:
            errs.append(f"{o['op']}: 샘플 주소 없음")
            continue
        df, err, params = call(c, url)
        if df is None:
            errs.append(f"{o['op']}: {err}")
            continue
        (P / "data" / dsid).mkdir(parents=True, exist_ok=True)
        df.astype(str).to_parquet(P / "data" / dsid / f"kipris_{dt.date.today():%Y%m%d}.parquet")
        (P / "stats" / f"{dsid}.json").write_text(json.dumps({o["op"]: col_stats(df)}, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
        run["ops"] = [{"op": o["op"], "url": url.split("?")[0], "ok": True, "rows": len(df), "columns": list(map(str, df.columns)),
                       "params": params, "note": f"KIPRIS Plus {o['service']}/{o['op']} ({dbii}) 샘플 인자 — accessKey(query)"}]
        run["ok_ops"] = 1
        break
    if ops and not run.get("ok_ops"):
        reg = any(w in e for e in errs for w in ("101", "NOT_REGISTERED", "Not Registerd", "등록된 서비스키"))
        run.update({"ok_ops": 0, "error": ("서비스 신청 필요(키에 이 서비스가 등록되지 않음) — " if reg else "") + " · ".join(errs)[:300]})
    run["finished_at"] = dt.datetime.now().isoformat(timespec="seconds")
    save_run(run)  # 실패면 기존 성공 기록을 덮지 않는다
    return run


def main(only: set[str] | None = None) -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    lk = pd.read_parquet(config.KNOWLEDGE / "expansion" / "site_links.parquet", columns=["id", "host", "link", "title"]).drop_duplicates("id")
    lk = lk[lk["host"].fillna("").str.contains("kipris")]
    if only:
        lk = lk[lk["id"].isin(only)]
    ok = 0
    with httpx.Client(timeout=90, headers={"User-Agent": "Mozilla/5.0"}, follow_redirects=True) as c:
        for n, r in enumerate(lk.itertuples(), 1):
            try:
                run = run_one(c, r.id, r.link)
            except Exception as e:  # noqa: BLE001
                print(f"  {n}/{len(lk)} {r.id} 오류 {repr(e)[:120]}", flush=True)
                continue
            ok += bool(run.get("ok_ops"))
            print(f"  {n}/{len(lk)} {r.id} {'성공' if run.get('ok_ops') else '실패'} {str(r.title)[:28]} "
                  f"{run.get('error') or str(run['ops'][0]['rows']) + '행'}"[:170], flush=True)
    print({"KIPRIS 링크": len(lk), "성공": ok})


if __name__ == "__main__":
    main(set(sys.argv[1:]) or None)
