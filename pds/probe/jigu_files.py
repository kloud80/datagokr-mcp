"""택지정보시스템(openapi.jigu.go.kr) 파일 데이터 검증 — 지구정보·지구경계·단계별사업·토지이용계획 등 (키·로그인 불필요).

링크 detail.do?table=<테이블>에서 최신 고시월의 파일 목록(/api/list.json)을 받아 전국(없으면 가장 작은) CSV·SHP 하나를
/openApi/down.do로 내려받아 행·열·셀 통계를 남긴다 (probe/runs·stats·data). 실행: python -m pds.probe.jigu_files [id ...]
"""
from __future__ import annotations

import datetime as dt
import json
import re
import sys
from urllib.parse import parse_qs, urlparse

import httpx
import pandas as pd

from pds import config
from pds.probe.deep import col_stats
from pds.probe.vworld_files import _read_any

BASE = "https://openapi.jigu.go.kr"
P = config.ROOT / "probe"


def _kb(s: str) -> float:
    m = re.search(r"([\d,\.]+)\s*(KB|MB|GB)", str(s))
    return float(m.group(1).replace(",", "")) * {"KB": 1, "MB": 1024, "GB": 1024 ** 2}[m.group(2)] if m else 1e12


def run_one(c: httpx.Client, dsid: str, link: str) -> dict:
    run = {"id": dsid, "kind": "external", "site": "openapi.jigu.go.kr", "link": link,
           "started_at": dt.datetime.now().isoformat(timespec="seconds"), "ops": []}
    try:
        table = parse_qs(urlparse(link).query).get("table", [None])[0]
        if not table:
            raise ValueError("링크에 table 없음")
        page = c.get(f"{BASE}/down/detail.do", params={"table": table}).text
        months = re.findall(r'<option value="(\d{4}-\d{2}[^"]*)"', page)
        files = []
        for m in months[:3]:
            files = c.post(f"{BASE}/api/list.json", data={"tNm": table, "table": table, "ctprvn": "", "ntfcDe": m}).json().get("list") or []
            if files:
                break
        if not files:
            raise ValueError("파일 목록 없음")
        pick = sorted(files, key=lambda f: (f.get("fileTy") not in ("csv",), f.get("ctprvn") != "00", _kb(f.get("fileCpcty"))))[0]
        r = c.get(f"{BASE}/openApi/down.do", params={"fileTy": pick["fileTy"], "stdrDe": str(pick["dt"]).replace("-", ""),
                                                     "ctprvn": pick["ctprvn"], "table": table, "fileNo": pick["fileNo"]}, timeout=300)
        if r.status_code != 200 or not r.content:
            raise ValueError(f"다운로드 실패 status {r.status_code}")
        name = re.search(r'filename="?([^";]+)', r.headers.get("content-disposition", "")) or None
        df = _read_any(r.content, name.group(1) if name else f"{table}.zip")
        (P / "data" / dsid).mkdir(parents=True, exist_ok=True)
        df.astype(str).to_parquet(P / "data" / dsid / f"jigu_{dt.date.today():%Y%m%d}.parquet")
        (P / "stats" / f"{dsid}.json").write_text(json.dumps({"file": col_stats(df)}, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
        run["ops"] = [{"op": f"jigu 다운로드 {pick['fileTy']}", "ok": True, "rows": len(df), "total_count": pick.get("totcnt"),
                       "columns": list(map(str, df.columns)), "file": pick.get("fileNm"), "sample": f"{pick.get('ctprvnNm')} {pick.get('ntfcDe')}",
                       "attempts": [{"bytes": len(r.content)}]}]
        run["ok_ops"] = 1
    except Exception as e:  # noqa: BLE001
        run.update({"ok_ops": 0, "error": f"{type(e).__name__}: {str(e)[:200]}"})
    run["finished_at"] = dt.datetime.now().isoformat(timespec="seconds")
    (P / "runs" / f"{dsid}.json").write_text(json.dumps(run, ensure_ascii=False, indent=1), encoding="utf-8")
    return run


def main(ids: list[str]) -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    links = pd.read_parquet(config.KNOWLEDGE / "expansion" / "site_links.parquet", columns=["id", "link"]).drop_duplicates("id")
    link = dict(zip(links["id"], links["link"]))
    if not ids:
        t = json.loads((config.KNOWLEDGE / "targets.json").read_text(encoding="utf-8"))
        ids = [x["id"] for x in t if x["status"] != "verified" and "jigu.go.kr" in str(link.get(x["id"]))]
    ok = []
    with httpx.Client(timeout=60, follow_redirects=True, headers={"User-Agent": "Mozilla/5.0"}) as c:
        c.get(f"{BASE}/down/detail.do")
        for i in ids:
            r = run_one(c, i, link.get(i, ""))
            print(f"  {i} {'성공' if r['ok_ops'] else '실패'} {r.get('error') or r['ops'][0]['rows']}", flush=True)
            if r["ok_ops"]:
                ok.append(i)
    path = config.KNOWLEDGE / "targets.json"  # 상태 갱신
    t = json.loads(path.read_text(encoding="utf-8"))
    for x in t:
        if x["id"] in ids:
            x["status"] = "verified" if x["id"] in ok else "failed"
    path.write_text(json.dumps(t, ensure_ascii=False, indent=1), encoding="utf-8")
    print({"대상": len(ids), "성공": len(ok)})


if __name__ == "__main__":
    main(sys.argv[1:])
