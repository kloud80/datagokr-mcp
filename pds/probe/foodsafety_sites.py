"""식품안전나라(foodsafetykorea.go.kr) 오픈API 검증 — 가입 없이 sample 키로 견본 5행.

링크(…svc_no=I2540 등)나 상세 페이지에서 서비스 코드를 찾아 http://openapi.foodsafetykorea.go.kr/api/sample/{코드}/json/1/5 를 부른다.
전수는 인증키(회원가입 → 인증키 신청) 필요. 실행: python -m pds.probe.foodsafety_sites
"""
from __future__ import annotations

import datetime as dt
import json
import re
import sys

import httpx
import pandas as pd

from pds import config
from pds.probe.deep import col_stats

P = config.ROOT / "probe"
API = "http://openapi.foodsafetykorea.go.kr/api/{key}/{svc}/json/1/5"
CODE = re.compile(r"(?:svc_no=|keyId=|/api/sample/)([A-Z]{1,2}\d{3,4}(?:_\d+)?)")


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    lk = pd.read_parquet(config.KNOWLEDGE / "expansion" / "site_links.parquet", columns=["id", "host", "link", "api_kind_label"]).drop_duplicates("id")
    g = lk[lk["host"].fillna("").str.contains("foodsafetykorea") & (lk["api_kind_label"] == "API_LINK")]
    ok = 0
    with httpx.Client(timeout=40, follow_redirects=True, headers={"User-Agent": "Mozilla/5.0"}) as c:
        for dsid, link in zip(g["id"], g["link"]):
            run = {"id": dsid, "kind": "external", "site": "openapi.foodsafetykorea.go.kr", "link": link,
                   "started_at": dt.datetime.now().isoformat(timespec="seconds"), "ops": []}
            try:
                codes = CODE.findall(link)
                if not codes:
                    codes = list(dict.fromkeys(CODE.findall(c.get(link).text)))
                if not codes:
                    raise ValueError("서비스 코드를 찾지 못함")
                svc, rows, total = codes[0], [], None
                for svc in codes[:3]:
                    obj = c.get(API.format(key="sample", svc=svc)).json().get(svc) or {}
                    rows, total = obj.get("row") or [], obj.get("total_count")
                    if rows:
                        break
                if not rows:
                    raise ValueError(f"{svc} 견본 0행")
                df = pd.DataFrame(rows)
                (P / "data" / dsid).mkdir(parents=True, exist_ok=True)
                df.astype(str).to_parquet(P / "data" / dsid / f"foodsafety_{dt.date.today():%Y%m%d}.parquet")
                (P / "stats" / f"{dsid}.json").write_text(json.dumps({svc: col_stats(df)}, ensure_ascii=False, indent=1, default=str),
                                                         encoding="utf-8")
                run["ops"] = [{"op": svc, "url": API.format(key="{KEY}", svc=svc).replace("/1/5", "/1/1000"), "ok": True, "rows": len(df),
                               "total_count": total, "columns": list(map(str, df.columns)),
                               "note": "sample 키 견본 5행 — 전수는 식품안전나라 인증키"}]
                run["ok_ops"] = 1
                ok += 1
            except Exception as e:  # noqa: BLE001
                run.update({"ok_ops": 0, "error": f"{type(e).__name__}: {str(e)[:150]}"})
            run["finished_at"] = dt.datetime.now().isoformat(timespec="seconds")
            (P / "runs" / f"{dsid}.json").write_text(json.dumps(run, ensure_ascii=False, indent=1), encoding="utf-8")
            print(f"  {dsid} {'성공' if run.get('ok_ops') else '실패'} {run.get('error') or run['ops'][0]['op']}"[:120], flush=True)
    print({"대상": len(g), "성공": ok})


if __name__ == "__main__":
    main()
