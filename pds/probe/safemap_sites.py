"""생활안전지도(safemap.go.kr) 검증 — 데이터 안내(dataViewRenew.do?objtId=)의 오픈API(/openapi2/IF_xxxx)를 인증키로 부른다.

키: .env SAFEMAP_API_KEY (serviceKey). 회원가입 → 오픈API 인증키 신청 → 승인 후에야 등록된다 (그 전에는 resultCode 30 '등록되지 않은 서비스키').
WMS·범례(_WMS, lgdInfo)는 표가 아니라 건너뛴다. selectDataAPIDetail.do 3건은 WMS 전용이라 대상 아님.
실행: python -m pds.probe.safemap_sites
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import sys

import httpx
import pandas as pd

from pds import config
from pds.probe.deep import col_stats

P = config.ROOT / "probe"
B = "https://www.safemap.go.kr"


def _rows(obj) -> tuple[list[dict], int | None, str]:
    head = obj.get("header") or {}
    body = obj.get("body") or {}
    items = body.get("items")
    if isinstance(items, dict):
        items = items.get("item")
    if isinstance(items, dict):
        items = [items]
    return (items or []), body.get("totalCount"), f"{head.get('resultCode')} {head.get('errorMsg') or head.get('resultMsg')}"


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    key = os.environ.get("SAFEMAP_API_KEY", "")
    lk = pd.read_parquet(config.KNOWLEDGE / "expansion" / "site_links.parquet", columns=["id", "host", "link"]).drop_duplicates("id")
    g = lk[lk["host"].fillna("").str.contains("safemap")]
    ok = 0
    with httpx.Client(timeout=40, follow_redirects=True, headers={"User-Agent": "Mozilla/5.0"}) as c:
        for dsid, link in zip(g["id"], g["link"]):
            run = {"id": dsid, "kind": "external", "site": "www.safemap.go.kr", "link": link,
                   "started_at": dt.datetime.now().isoformat(timespec="seconds"), "ops": []}
            try:
                if "dataViewRenew" not in link:
                    raise ValueError("WMS 지도 서비스 안내 — 표 형태 API 아님")
                svcs = [s for s in dict.fromkeys(re.findall(r"/openapi2/(IF_\w+)", c.get(link).text)) if not s.endswith("_WMS")]
                if not svcs:
                    raise ValueError("오픈API 주소를 찾지 못함")
                svc, rows, total, msg = svcs[0], [], None, ""
                for svc in svcs[:2]:
                    r = c.get(f"{B}/openapi2/{svc}", params={"serviceKey": key, "numOfRows": 100, "pageNo": 1, "returnType": "json"})
                    try:
                        rows, total, msg = _rows(r.json())
                    except Exception:  # noqa: BLE001
                        msg = r.text[:100]
                    if rows:
                        break
                if not rows:
                    raise ValueError(f"{svc}: {msg}")
                df = pd.DataFrame(rows)
                (P / "data" / dsid).mkdir(parents=True, exist_ok=True)
                df.astype(str).to_parquet(P / "data" / dsid / f"safemap_{dt.date.today():%Y%m%d}.parquet")
                (P / "stats" / f"{dsid}.json").write_text(json.dumps({svc: col_stats(df)}, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
                run["ops"] = [{"op": svc, "url": f"{B}/openapi2/{svc}", "ok": True, "rows": len(df), "total_count": total,
                               "columns": list(map(str, df.columns)), "params": {"numOfRows": 100, "pageNo": 1, "returnType": "json"},
                               "note": "생활안전지도 인증키 serviceKey(query) — 가입·신청·승인 필요"}]
                run["ok_ops"] = 1
                ok += 1
            except Exception as e:  # noqa: BLE001
                run.update({"ok_ops": 0, "error": f"{type(e).__name__}: {str(e)[:150]}"})
            run["finished_at"] = dt.datetime.now().isoformat(timespec="seconds")
            text = json.dumps(run, ensure_ascii=False, indent=1)
            (P / "runs" / f"{dsid}.json").write_text(text.replace(key, "***") if key else text, encoding="utf-8")
            print(f"  {dsid} {'성공' if run.get('ok_ops') else '실패'} {run.get('error') or run['ops'][0]['op']}"[:120], flush=True)
    print({"대상": len(g), "성공": ok})


if __name__ == "__main__":
    main()
