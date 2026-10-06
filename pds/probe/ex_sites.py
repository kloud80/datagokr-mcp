"""한국도로공사 고속도로 공공데이터 포털(data.ex.co.kr) 검증 — 가입 없이 key=test 로 오픈API 호출.

API 안내(openApiInfoM?apiId=…) 페이지에서 요청 주소(data.ex.co.kr/openapi/…)를 찾아 key=test&type=json 으로 부른다.
전수·운영은 회원가입 후 인증키. 파일형 링크는 이 도구 밖. 실행: python -m pds.probe.ex_sites
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
EP = re.compile(r"(https?://data\.ex\.co\.kr/openapi/(?!basicinfo)[\w/]+)")


def _rows(obj) -> tuple[list[dict], int | None]:
    if isinstance(obj, dict):
        for k in ("list", "data", "items", "realUnitTrtm", "row"):
            v = obj.get(k)
            if isinstance(v, list) and v and isinstance(v[0], dict):
                return v, obj.get("count") or obj.get("totalCount")
        for v in obj.values():
            if isinstance(v, list) and v and isinstance(v[0], dict):
                return v, obj.get("count")
    return [], None


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    lk = pd.read_parquet(config.KNOWLEDGE / "expansion" / "site_links.parquet", columns=["id", "host", "link", "api_kind_label"]).drop_duplicates("id")
    g = lk[(lk["host"] == "data.ex.co.kr") & (lk["api_kind_label"] == "API_LINK")]
    ok = 0
    with httpx.Client(timeout=40, follow_redirects=True, headers={"User-Agent": "Mozilla/5.0"}) as c:
        for dsid, link in zip(g["id"], g["link"]):
            run = {"id": dsid, "kind": "external", "site": "data.ex.co.kr", "link": link,
                   "started_at": dt.datetime.now().isoformat(timespec="seconds"), "ops": []}
            try:
                eps = list(dict.fromkeys(EP.findall(c.get(link).text)))
                if not eps:
                    raise ValueError("요청 주소를 찾지 못함")
                rows, total, used, err = [], None, None, ""
                for ep in eps[:3]:
                    r = c.get(ep, params={"key": "test", "type": "json", "numOfRows": 100, "pageNo": 1})
                    try:
                        rows, total = _rows(r.json())
                    except Exception:  # noqa: BLE001
                        err = r.text[:120]
                    if rows:
                        used = ep
                        break
                if not rows:
                    raise ValueError(f"0행 {err}")
                df = pd.DataFrame(rows)
                (P / "data" / dsid).mkdir(parents=True, exist_ok=True)
                df.astype(str).to_parquet(P / "data" / dsid / f"ex_{dt.date.today():%Y%m%d}.parquet")
                op = used.rsplit("/", 1)[-1]
                (P / "stats" / f"{dsid}.json").write_text(json.dumps({op: col_stats(df)}, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
                run["ops"] = [{"op": op, "url": used, "ok": True, "rows": len(df), "total_count": total, "columns": list(map(str, df.columns)),
                               "params": {"type": "json", "numOfRows": 100, "pageNo": 1}, "note": "key=test로 확인 — 운영은 도로공사 인증키(key)"}]
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
