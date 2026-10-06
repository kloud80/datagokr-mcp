"""제주데이터허브(jejudatahub.net) 링크형 검증 — 링크 396건 (API 68 · 파일 328).

메타: GET https://jejudatahub.net/api/data/view?id={id} → dataKey · dataApi(요청 인자 명세) · csvData(미리보기 표).
API형: https://open.jejudatahub.net/api/proxy/{dataKey}/{projectKey}?{인자} (projectKey = .env JEJU_DATA_HUB_API_KEY)
       필수 인자는 명세의 example(YYYYMM·YYYYMMDD 등)을 수집기간 끝 기준으로 채운다. 실패하면 미리보기 표로.
파일형: 원본은 로그인·대용량(zip)이라, 상세 페이지 미리보기(csvData, 로그인 불필요)로 열·값을 확인한다.
실행: python -m pds.probe.jeju_sites [id ...]   (키 값은 실행 기록에 남기지 않는다)
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import sys
import time

import httpx
import pandas as pd

from pds import config
from pds.probe.deep import col_stats

P = config.ROOT / "probe"
META = "https://jejudatahub.net/api/data/view"
PROXY = "https://open.jejudatahub.net/api/proxy/{dk}/{pk}"


def _fill(ex: str, end: str) -> str | None:
    e = (ex or "").strip().upper()
    d = re.sub(r"\D", "", end or "") or dt.date.today().strftime("%Y%m%d")
    if e in ("YYYYMM", "YYYY-MM"):
        return d[:6] if e == "YYYYMM" else f"{d[:4]}-{d[4:6]}"
    if e in ("YYYYMMDD", "YYYY-MM-DD"):
        return d[:8] if e == "YYYYMMDD" else f"{d[:4]}-{d[4:6]}-{d[6:8]}"
    if e == "YYYY":
        return d[:4]
    return ex if ex and not re.search(r"[가-힣]", ex) else None


def _rows(obj) -> list[dict]:
    if isinstance(obj, list) and obj and isinstance(obj[0], dict):
        return obj
    if isinstance(obj, dict):
        for v in obj.values():
            r = _rows(v)
            if r:
                return r
    return []


def run_one(c: httpx.Client, dsid: str, link: str, pk: str) -> dict:
    run = {"id": dsid, "kind": "external", "site": "jejudatahub.net", "link": link,
           "started_at": dt.datetime.now().isoformat(timespec="seconds"), "ops": []}
    try:
        jid = re.search(r"/(\d+)(?:\D*$)", link)
        if not jid:
            raise ValueError("링크에서 데이터 id를 찾지 못함")
        meta = None
        for k in range(4):  # 연속 요청이면 HTML 오류 페이지가 온다 — 잠깐 쉬고 다시
            r0 = c.get(META, params={"id": jid.group(1)})
            if r0.text.lstrip()[:1] == "{":
                meta = r0.json()
                break
            time.sleep(2 + 3 * k)
        if meta is None:
            raise ValueError(f"메타 응답이 JSON 아님 (status {r0.status_code})")
        dk, api = meta.get("dataKey"), meta.get("dataApi")
        df, op = None, None
        if api and dk and pk:
            params = {}
            for el in api.get("dataApiElements") or []:
                if el.get("type") != "request" or el.get("requireYn") != "Y":
                    continue
                v = _fill(el.get("example"), meta.get("endDate"))
                if v:
                    params[el["name"].strip()] = v
            r = c.get(PROXY.format(dk=dk, pk=pk), params=params)
            if r.status_code == 200 and r.text.lstrip()[:1] in "{[":
                rows = _rows(r.json())
                if rows:
                    df = pd.DataFrame(rows)
                    op = {"op": "api", "url": PROXY.format(dk=dk, pk="{projectKey}"), "params": params,
                          "note": "제주데이터허브 오픈API — projectKey(경로), 일일 쿼터 " + str(api.get("quota"))}
            if df is None:
                run["api_error"] = f"status {r.status_code} {r.text[:80]}".replace(pk, "***")
        if df is None:
            csv = meta.get("csvData") or []
            if len(csv) >= 2:
                w = max(len(x) for x in csv)
                head = [str(x) for x in csv[0]] + [f"col{i}" for i in range(len(csv[0]), w)]
                df = pd.DataFrame([list(x) + [None] * (w - len(x)) for x in csv[1:]], columns=head)
                op = {"op": "preview", "url": f"{META}?id={jid.group(1)}",
                      "note": "상세 페이지 미리보기(csvData, 로그인 불필요) — 원본 파일·API는 로그인/projectKey"}
        if df is None or not len(df):
            raise ValueError("API·미리보기 모두 행 없음" + (f" ({run.get('api_error')})" if run.get("api_error") else ""))
        (P / "data" / dsid).mkdir(parents=True, exist_ok=True)
        s = df.astype(str).head(100000)
        s.to_parquet(P / "data" / dsid / f"jeju_{dt.date.today():%Y%m%d}.parquet")
        (P / "stats" / f"{dsid}.json").write_text(json.dumps({op["op"]: col_stats(s)}, ensure_ascii=False, indent=1, default=str),
                                                 encoding="utf-8")
        run["ops"] = [{**op, "ok": True, "rows": len(df), "columns": list(map(str, df.columns))}]
        run["ok_ops"] = 1
    except Exception as e:  # noqa: BLE001
        run.update({"ok_ops": 0, "error": f"{type(e).__name__}: {str(e)[:150]}".replace(pk, "***") if pk else f"{type(e).__name__}: {str(e)[:150]}"})
    run["finished_at"] = dt.datetime.now().isoformat(timespec="seconds")
    text = json.dumps(run, ensure_ascii=False, indent=1, default=str)
    (P / "runs" / f"{dsid}.json").write_text(text.replace(pk, "***") if pk else text, encoding="utf-8")
    return run


def main(ids: list[str]) -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    pk = os.environ.get("JEJU_DATA_HUB_API_KEY", "")
    lk = pd.read_parquet(config.KNOWLEDGE / "expansion" / "site_links.parquet", columns=["id", "host", "link"]).drop_duplicates("id")
    g = lk[lk["host"].fillna("").str.contains("jejudatahub")]
    items = [(i, l) for i, l in zip(g["id"], g["link"]) if not ids or i in ids]
    ok = 0
    from collections import Counter
    why = Counter()
    with httpx.Client(timeout=40, follow_redirects=True, headers={"User-Agent": "Mozilla/5.0"}) as c:
        for dsid, link in items:
            prev = P / "runs" / f"{dsid}.json"
            if prev.exists() and json.loads(prev.read_text(encoding="utf-8")).get("ok_ops"):
                continue
            r = run_one(c, dsid, link, pk)
            time.sleep(0.4)
            ok += bool(r.get("ok_ops"))
            if r.get("ok_ops"):
                why[r["ops"][0]["op"]] += 1
            else:
                why[r["error"][:50]] += 1
            print(f"  {dsid} {'성공' if r.get('ok_ops') else '실패'} {r.get('error') or r['ops'][0]['op']}"[:120], flush=True)
    print({"대상": len(items), "성공": ok})
    print(why.most_common(6))


if __name__ == "__main__":
    main(sys.argv[1:])
