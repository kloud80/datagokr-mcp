"""문화공공데이터광장 검증 — API마다 메일로 온 서비스키(secrets/culture_mail_parsed.json)를 API 이름으로 짝지어 호출한다.

메일: '구름 님께서 신청하신 {API 이름} 의 서비스키는 …' → (이름, 키). 신청 기록(probe/apply_culture)의 API 상세 페이지에서
제목·요청 주소(api.kcisa.kr)를 읽어 이름이 가장 가까운 메일 키로 serviceKey 호출. 키는 secrets/culture_keys.json(api id → 키, git 밖)에 남긴다.
실행: python -m pds.probe.culture_verify
"""
from __future__ import annotations

import datetime as dt
import difflib
import json
import re
import sys

import httpx
import pandas as pd

from pds import config
from pds.probe.deep import _items_json, _items_xml, col_stats

P = config.ROOT / "probe"
S = config.ROOT / "secrets"


def _norm(t: str) -> str:
    return re.sub(r"[\s()\[\]·_\-.,]|정보|서비스|조회|목록", "", re.sub(r"^.*?_", "", str(t)))


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    mails = json.loads((S / "culture_mail_parsed.json").read_text(encoding="utf-8"))
    by_name = {}
    for m in mails:
        nm = re.search(r"신청하신 (.+?) 의 서비스키", m["text"])
        if nm:
            by_name[_norm(nm.group(1))] = (nm.group(1).strip(), m["key"])
    recs = [json.loads(f.read_text(encoding="utf-8")) for f in (P / "apply_culture").glob("*.json")]
    keys, ok = {}, 0
    with httpx.Client(timeout=40, follow_redirects=True, headers={"User-Agent": "Mozilla/5.0"}) as c:
        api_page = {}
        for r in recs:
            aid, dsid = r.get("api_id"), r.get("dataset")
            if not aid or not dsid:
                continue
            if aid not in api_page:
                h = c.get(f"https://www.culture.go.kr/data/openapi/openapiView.do?id={aid}").text
                t = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " | ", h))
                title = next(iter(re.findall(r"상세 \|[ |]*([^|]{4,80}?) \|[ |]*활용신청", t)), "")
                api_page[aid] = (title.strip(), next(iter(re.findall(r"(https?://api\.kcisa\.kr/[\w/.-]+)", h)), None))
            title, ep = api_page[aid]
            run = {"id": dsid, "kind": "external", "site": "api.kcisa.kr", "link": r.get("link"),
                   "started_at": dt.datetime.now().isoformat(timespec="seconds"), "ops": []}
            try:
                best = difflib.get_close_matches(_norm(title), list(by_name), n=1, cutoff=0.5) if title else []
                if not best or not ep:
                    raise ValueError(f"메일 키와 짝을 찾지 못함 ({title[:30]})")
                name, key = by_name[best[0]]
                keys[aid] = key
                resp = c.get(ep, params={"serviceKey": key, "numOfRows": 100, "pageNo": 1})
                rows = None
                if resp.text.lstrip().startswith(("{", "[")):
                    rows = _items_json(resp.json())
                if rows is None:
                    rows = _items_xml(resp.text)
                if not rows:
                    raise ValueError(f"0행 status {resp.status_code} {resp.text[:100]}")
                df = pd.DataFrame(rows)
                (P / "data" / dsid).mkdir(parents=True, exist_ok=True)
                df.astype(str).to_parquet(P / "data" / dsid / f"culture_{dt.date.today():%Y%m%d}.parquet")
                op = ep.rsplit("/", 1)[-1]
                (P / "stats" / f"{dsid}.json").write_text(json.dumps({op: col_stats(df)}, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
                run["ops"] = [{"op": op, "url": ep, "ok": True, "rows": len(df), "columns": list(map(str, df.columns)),
                               "params": {"numOfRows": 100, "pageNo": 1}, "note": f"API별 서비스키 (메일 발급, '{name}') — serviceKey(query)"}]
                run["ok_ops"] = 1
                ok += 1
            except Exception as e:  # noqa: BLE001
                run.update({"ok_ops": 0, "error": f"{type(e).__name__}: {str(e)[:150]}"})
            run["finished_at"] = dt.datetime.now().isoformat(timespec="seconds")
            (P / "runs" / f"{dsid}.json").write_text(json.dumps(run, ensure_ascii=False, indent=1), encoding="utf-8")
            print(f"  {dsid} {aid} {'성공' if run.get('ok_ops') else '실패'} {title[:30]} {run.get('error', '')[:60]}", flush=True)
    (S / "culture_keys.json").write_text(json.dumps(keys, ensure_ascii=False, indent=1), encoding="utf-8")
    print({"신청 기록": len(recs), "성공": ok, "키 짝": len(keys)})


if __name__ == "__main__":
    main()
