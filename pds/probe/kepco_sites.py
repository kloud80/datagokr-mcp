"""한전 전력데이터 개방포털(bigdata.kepco.co.kr) 검증 — 포털 링크형을 오픈API로 불러 확인한다 (BIGDATA_KEPCO_API_KEY).

1. API 안내 화면 cmsmain.do?scode=S01&pcode=000493&pstate=<서비스> 에서 요청 주소·예시 인자를 읽는다 (서비스 13종)
2. 데이터 제목으로 서비스를 고른다 — API_LINK는 모두 안내 화면(pcode=000493)을 가리키고, FILE_LINK는 같은 내용의 조회 화면이다.
   설비 추이·발전실적·열공급처럼 대응 API가 없는 화면은 실패로 남긴다
3. 필수 인자만으로 먼저 부르고(전 지역·전 분류), 자료가 없으면(404·빈 목록) 예시의 선택 인자를 하나씩 더하고, 그래도 없으면 최근 연도로
공통 인자 apiKey·returnType=json. 응답·기록에 키를 싣지 않는다.
실행: python -m pds.probe.kepco_sites [id…]
"""
from __future__ import annotations

import datetime as dt
import html
import json
import os
import re
import sys
import time
from urllib.parse import parse_qsl, urlsplit

import httpx
import pandas as pd

from pds import config
from pds.probe.deep import col_stats, save_run

P = config.ROOT / "probe"
B = "https://bigdata.kepco.co.kr"
SVC = {  # 서비스 → 제목 단서 (앞의 것부터 맞춘다)
    "evmng": ["충전소 운영", "충전소운영"], "ev": ["충전소 설치", "전기차 충전소"], "indcust": ["고객 증감", "고객증감"],
    "billty": ["요금청구"], "house": ["가구 평균", "가구평균"], "renew": ["신재생"], "welfare": ["복지할인"], "code": ["공통코드"],
    "dgen": ["분산전원"], "contract": ["전자입찰"], "biz": ["업종별", "용도업종별"], "indus": ["산업분류"],
    "cntr": ["계약종별", "용도별"],
}
REQUIRED = {"year", "month", "codeTy", "noticeBeginDate", "noticeEndDate"}


def key() -> str:
    return os.environ.get("BIGDATA_KEPCO_API_KEY", "").strip()


def service_of(title: str) -> str | None:
    for svc, words in SVC.items():
        if any(w in title for w in words):
            return svc
    return None


def spec(c: httpx.Client, svc: str) -> tuple[str, dict] | None:
    h = c.post(f"{B}/cmsmain.do", data={"scode": "S01", "pcode": "000493", "pstate": svc}).text
    us = [html.unescape(u).replace("&nbsp;", "").replace("\xa0", "") for u in
          re.findall(r'https?://bigdata\.kepco\.co\.kr/openapi/[^\s"<]*\?[^\s"<]*apiKey=xxx[^\s"<]*', h)]
    if not us:
        return None
    sp = urlsplit(us[-1] if svc == "evmng" else us[0])
    return sp.path, {a: b.strip() for a, b in parse_qsl(sp.query) if a not in ("apiKey", "returnType") and b.strip()}


def _call(c: httpx.Client, path: str, p: dict) -> tuple[list[dict], str | None]:
    time.sleep(0.3)
    r = c.get(B + path, params={**p, "apiKey": key(), "returnType": "json"})
    try:
        j = r.json()
    except Exception:  # noqa: BLE001
        return [], f"json 아님 {r.status_code}"
    rows = next((v for v in j.values() if isinstance(v, list) and v), []) if isinstance(j, dict) else []
    return rows, None if rows else f"{r.status_code} {str(j)[:80]}"


def attempts(p: dict):
    """필수 인자만(전 지역·전 분류) → 선택 인자를 하나씩 더한 예시 인자 → 연도를 최근으로."""
    opt = [k for k in p if k not in REQUIRED]
    for n in range(len(opt) + 1):
        yield {k: v for k, v in p.items() if k in REQUIRED or k in opt[:n]}
    if "year" in p:
        base = {k: v for k, v in p.items() if k in REQUIRED}
        for y in range(dt.date.today().year - 1, dt.date.today().year - 4, -1):
            yield {**base, "year": str(y)}


def run_one(c: httpx.Client, dsid: str, link: str, title: str, specs: dict) -> dict:
    run = {"id": dsid, "kind": "external", "site": "bigdata.kepco.co.kr", "link": link, "started_at": dt.datetime.now().isoformat(timespec="seconds"),
           "ops": []}
    svc = service_of(title)
    sp = specs.get(svc) if svc else None
    if not sp:
        run.update({"ok_ops": 0, "error": "대응하는 오픈API 없음 (조회 화면 전용 — 설비·발전·열공급 등)" if not svc else f"{svc} API 안내를 읽지 못함"})
    else:
        path, p0 = sp
        rows, err, used = [], None, p0
        for p in attempts(p0):
            rows, err = _call(c, path, p)
            used = p
            if rows:
                break
        if not rows:
            run.update({"ok_ops": 0, "error": f"{path} {err}"})
        else:
            df = pd.DataFrame(rows)
            (P / "data" / dsid).mkdir(parents=True, exist_ok=True)
            df.astype(str).to_parquet(P / "data" / dsid / f"kepco_{dt.date.today():%Y%m%d}.parquet")
            (P / "stats" / f"{dsid}.json").write_text(json.dumps({path.rsplit("/", 1)[-1]: col_stats(df)}, ensure_ascii=False, indent=1, default=str),
                                                     encoding="utf-8")
            run["ops"] = [{"op": path.rsplit("/", 1)[-1].removesuffix(".do"), "url": B + path, "ok": True, "rows": len(df),
                           "columns": list(map(str, df.columns)), "params": {**used, "returnType": "json"},
                           "note": f"한전 전력데이터 개방포털 오픈API '{svc}'" + (" — 포털 링크는 같은 내용의 조회 화면" if "000493" not in link else "")
                                   + " · apiKey(query)"}]
            run["ok_ops"] = 1
    run["finished_at"] = dt.datetime.now().isoformat(timespec="seconds")
    save_run(run)  # 실패면 기존 성공 기록을 덮지 않는다
    return run


def main(only: set[str] | None = None) -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    lk = pd.read_parquet(config.KNOWLEDGE / "expansion" / "site_links.parquet", columns=["id", "host", "link", "title"]).drop_duplicates("id")
    lk = lk[lk["host"].fillna("") == "bigdata.kepco.co.kr"]
    if only:
        lk = lk[lk["id"].isin(only)]
    ok = 0
    with httpx.Client(timeout=90, headers={"User-Agent": "Mozilla/5.0"}) as c:
        specs = {s: spec(c, s) for s in SVC}
        print({s: (v[0] if v else None) for s, v in specs.items()}, flush=True)
        for n, r in enumerate(lk.itertuples(), 1):
            run = run_one(c, r.id, r.link, str(r.title), specs)
            ok += bool(run.get("ok_ops"))
            print(f"  {n}/{len(lk)} {r.id} {'성공' if run.get('ok_ops') else '실패'} {str(r.title)[:28]} "
                  f"{run.get('error') or str(run['ops'][0]['rows']) + '행'}"[:160], flush=True)
    print({"한전 링크": len(lk), "성공": ok})


if __name__ == "__main__":
    main(set(sys.argv[1:]) or None)
