"""외부 라운드 — 서울 열린데이터광장 실시간 도시데이터(포털 목록키 15146211의 원천). 키: .env DATA_SEOUL_API_KEY.
주요 장소별 실시간 인구(citydata_ppltn)를 받아 포털 API와 같은 형식으로 저장한다.
"""
from __future__ import annotations

import datetime as dt
import json
import os
from urllib.parse import quote

import httpx
import pandas as pd

from pds import config
from pds.probe.deep import col_stats

P = config.ROOT / "probe"
AREAS = ["강남역", "광화문·덕수궁", "홍대 관광특구", "명동 관광특구", "잠실 관광특구", "여의도", "서울역", "성수카페거리",
         "이태원 관광특구", "신촌·이대역", "건대입구역", "가로수길", "북촌한옥마을", "DMC(디지털미디어시티)", "고척돔"]


def run(dsid: str = "15146211") -> dict:
    key = os.getenv("DATA_SEOUL_API_KEY")
    rows, fails = [], []
    with httpx.Client(timeout=60) as c:
        for a in AREAS:
            r = c.get(f"http://openapi.seoul.go.kr:8088/{key}/json/citydata_ppltn/1/5/{quote(a)}")
            items = (r.json().get("SeoulRtd.citydata_ppltn") or []) if r.status_code == 200 else []
            if items:
                it = {k: v for k, v in items[0].items() if not isinstance(v, (list, dict))}
                rows.append(it)
            else:
                fails.append(a)
    df = pd.DataFrame(rows)
    (P / "data" / dsid).mkdir(parents=True, exist_ok=True)
    df.astype(str).to_parquet(P / "data" / dsid / f"citydata_ppltn_{dt.datetime.now():%Y%m%d%H%M}.parquet")
    (P / "stats" / f"{dsid}.json").write_text(json.dumps({"citydata_ppltn": col_stats(df)}, ensure_ascii=False, indent=1, default=str),
                                              encoding="utf-8")
    run = {"id": dsid, "channel": "external", "site": "data.seoul.go.kr", "ok_ops": int(len(df) > 0),
           "ops": [{"op": "citydata_ppltn", "ok": len(df) > 0, "rows": len(df), "columns": list(df.columns), "failed_areas": fails,
                    "attempts": []}]}
    (P / "runs" / f"{dsid}.json").write_text(json.dumps(run, ensure_ascii=False, indent=1), encoding="utf-8")
    return {"rows": len(df), "failed": fails, "cols": list(df.columns)[:12]}


if __name__ == "__main__":
    print(run())
