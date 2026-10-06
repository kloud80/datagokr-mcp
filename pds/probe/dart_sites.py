"""OpenDART(금감원 전자공시) 검증 — 개발가이드 페이지에서 API 주소·필수 요청 인자를 읽어 인증키로 부른다.

필수 인자 기본값: corp_code 삼성전자(00126380) · bsns_year 작년 · reprt_code 11011(사업보고서) · fs_div CFS · 기간 최근 90일 ·
corp_cls Y · idx_cl_code M210000 · rcept_no 공시검색 첫 건. 키 OPEN_DART_API_KEY (crtfc_key).
ZIP·문서 원문 API(document·corpCode·fnlttXbrl)는 표가 아니라 건너뛴다. 실행: python -m pds.probe.dart_sites
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
API = re.compile(r"https://opendart\.fss\.or\.kr/api/(\w+)\.json")
TODAY = dt.date.today()
DEFAULTS = {"corp_code": "00126380", "bsns_year": str(TODAY.year - 1), "reprt_code": "11011", "fs_div": "CFS",
            "bgn_de": (TODAY - dt.timedelta(days=90)).strftime("%Y%m%d"), "end_de": TODAY.strftime("%Y%m%d"),
            "corp_cls": "Y", "idx_cl_code": "M210000", "page_count": "100", "page_no": "1"}


def _required(html: str) -> list[str]:
    s = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " | ", html))
    i, j = s.find("요청 인자"), s.find("응답 결과")
    return [m.group(1) for m in re.finditer(r"\|\s*(\w+)\s*\|[^|]*\|\s*\|[^|]*\|\s*\|\s*Y\s*\|", s[i:j])] if i >= 0 else []


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    key = os.environ.get("OPEN_DART_API_KEY", "")
    lk = pd.read_parquet(config.KNOWLEDGE / "expansion" / "site_links.parquet", columns=["id", "host", "link"]).drop_duplicates("id")
    g = lk[lk["host"].fillna("").str.contains("opendart")]
    ok = 0
    with httpx.Client(timeout=40, follow_redirects=True, headers={"User-Agent": "Mozilla/5.0"}) as c:
        first = c.get("https://opendart.fss.or.kr/api/list.json", params={"crtfc_key": key, "corp_code": "00126380",
                                                                            "bgn_de": DEFAULTS["bgn_de"], "page_count": 1}).json()
        rcept = ((first.get("list") or [{}])[0]).get("rcept_no", "")
        for dsid, link in zip(g["id"], g["link"]):
            run = {"id": dsid, "kind": "external", "site": "opendart.fss.or.kr", "link": link,
                   "started_at": dt.datetime.now().isoformat(timespec="seconds"), "ops": []}
            try:
                html = c.get(link).text
                apis = list(dict.fromkeys(API.findall(html)))
                apis = [a for a in apis if a not in ("document", "corpCode", "fnlttXbrl")]
                if not apis:
                    raise ValueError("표 형태 API 주소 없음 (원문·ZIP·안내 페이지)")
                need = _required(html)
                params = {"crtfc_key": key, **{k: DEFAULTS[k] for k in need if k in DEFAULTS}}
                if "rcept_no" in need:
                    params["rcept_no"] = rcept
                obj = c.get(f"https://opendart.fss.or.kr/api/{apis[0]}.json", params=params).json()
                for _ in range(2):  # 오류 메시지가 빠진 필수값을 알려 준다 — 기본값으로 채워 다시
                    miss = re.findall(r"필수값\(([\w,]+)\)", str(obj.get("message")))
                    if obj.get("status") != "100" or not miss:
                        break
                    for k in miss[0].split(","):
                        params[k] = rcept if k == "rcept_no" else DEFAULTS.get(k, "BS" if k == "sj_div" else "")
                    obj = c.get(f"https://opendart.fss.or.kr/api/{apis[0]}.json", params=params).json()
                if obj.get("status") == "013" and "bgn_de" in params:  # 조회된 데이터 없음 — 기간을 3년으로
                    params["bgn_de"] = (TODAY - dt.timedelta(days=1095)).strftime("%Y%m%d")
                    obj = c.get(f"https://opendart.fss.or.kr/api/{apis[0]}.json", params=params).json()
                rows = obj.get("list") or ([{k: v for k, v in obj.items() if k not in ("status", "message")}] if obj.get("status") == "000" else [])
                if not rows:
                    raise ValueError(f"{apis[0]} status {obj.get('status')} {obj.get('message')}")
                df = pd.DataFrame(rows)
                (P / "data" / dsid).mkdir(parents=True, exist_ok=True)
                df.astype(str).to_parquet(P / "data" / dsid / f"dart_{TODAY:%Y%m%d}.parquet")
                (P / "stats" / f"{dsid}.json").write_text(json.dumps({apis[0]: col_stats(df)}, ensure_ascii=False, indent=1, default=str),
                                                         encoding="utf-8")
                run["ops"] = [{"op": apis[0], "url": f"https://opendart.fss.or.kr/api/{apis[0]}.json", "ok": True, "rows": len(df),
                               "total_count": obj.get("total_count"), "columns": list(map(str, df.columns)),
                               "params": {k: v for k, v in params.items() if k != "crtfc_key"}, "note": "인증키 crtfc_key(query) — 이메일 인증 후 즉시 발급"}]
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
