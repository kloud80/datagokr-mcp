"""외부 라운드 — 나이스 교육정보 개방 포털(open.neis.go.kr). 포털 목록키 15122331(표준데이터 15107735 대체)의 실제 원천.

키: .env OPEN_NEIS_API_KEY (SNS 로그인 후 인증키 신청 → 즉시 발급).
절차: 학교기본정보(schoolInfo)를 전국 전수로 받아 교육청코드(ATPT_OFCDC_SC_CODE)+학교코드(SD_SCHUL_CODE)를 얻고 →
      표본 학교로 급식·학사일정·시간표·학급을 조회. 일상 정보 API는 두 코드가 모두 필수라 학교 마스터가 첫 조인이다.
출력: probe/runs|stats|data/{id} — 포털 API와 같은 형식
"""
from __future__ import annotations

import datetime as dt
import json
import os

import httpx
import pandas as pd

from pds import config
from pds.probe.deep import col_stats

P = config.ROOT / "probe"
DSID = "15122331"
HUB = "https://open.neis.go.kr/hub"
OFFICES = ["B10", "J10", "T10"]  # 서울·경기·제주
KINDS = {"초등학교": "elsTimetable", "중학교": "misTimetable", "고등학교": "hisTimetable"}


def _get(c: httpx.Client, op: str, max_rows: int = 5000, **params) -> tuple[list[dict], int, str]:
    rows, page, total, code = [], 1, 0, ""
    while len(rows) < max_rows:
        j = c.get(f"{HUB}/{op}", params={"KEY": os.getenv("OPEN_NEIS_API_KEY"), "Type": "json", "pIndex": page, "pSize": 1000,
                                         **params}).json()
        if op not in j:
            return rows, total, code or j.get("RESULT", {}).get("CODE", "")
        head = j[op][0]["head"]
        total, code = int(head[0]["list_total_count"]), head[1]["RESULT"]["CODE"]
        rows += j[op][1]["row"]
        if len(rows) >= total:
            break
        page += 1
    return rows, total, code


def run() -> dict:
    today = dt.date.today()
    monday = today - dt.timedelta(days=today.weekday() + 7)  # 지난주 월~금
    week = {"TI_FROM_YMD": f"{monday:%Y%m%d}", "TI_TO_YMD": f"{monday + dt.timedelta(days=4):%Y%m%d}"}
    frames: dict[str, list[pd.DataFrame]] = {}
    ops: dict[str, dict] = {}

    def add(op: str, rows: list[dict], total: int, code: str, params: dict) -> None:
        frames.setdefault(op, []).append(pd.DataFrame(rows))
        o = ops.setdefault(op, {"op": op, "ok": False, "rows": 0, "total_count": 0, "calls": 0, "attempts": []})
        o["rows"] += len(rows)
        o["total_count"] += total
        o["calls"] += 1
        o["ok"] |= bool(rows)
        o["attempts"].append({"fmt": "json", "params": params, "rows": len(rows), "code": code})

    with httpx.Client(timeout=60) as c:
        # 1) 학교 마스터 전수 (전국)
        schools, total, code = _get(c, "schoolInfo", max_rows=20000)
        add("schoolInfo", schools, total, code, {})
        sdf = pd.DataFrame(schools)
        # 2) 교육청 단위 목록형 (학원·학과·계열) — 표본 교육청만
        for op in ("acaInsTiInfo", "schoolMajorinfo", "schulAflcoinfo"):
            for of in OFFICES:
                rows, total, code = _get(c, op, max_rows=2000, ATPT_OFCDC_SC_CODE=of)
                add(op, rows, total, code, {"ATPT_OFCDC_SC_CODE": of})
        # 3) 학교 단위 일상 정보 — 교육청 × 학교급 1곳씩
        for of in OFFICES:
            for kind, tt in KINDS.items():
                m = sdf[(sdf.ATPT_OFCDC_SC_CODE == of) & (sdf.SCHUL_KND_SC_NM == kind)]
                if m.empty:
                    continue
                sc = {"ATPT_OFCDC_SC_CODE": of, "SD_SCHUL_CODE": m.iloc[0].SD_SCHUL_CODE}
                for op, p in (("mealServiceDietInfo", {"MLSV_FROM_YMD": f"{today.replace(day=1):%Y%m%d}", "MLSV_TO_YMD": f"{today:%Y%m%d}"}),
                              ("SchoolSchedule", {"AA_FROM_YMD": f"{today.year}0301", "AA_TO_YMD": f"{today.year + 1}0228"}),
                              (tt, week), ("classInfo", {"AY": str(today.year)})):
                    rows, total, code = _get(c, op, **sc, **p)
                    add(op, rows, total, code, {**sc, **p})

    (P / "data" / DSID).mkdir(parents=True, exist_ok=True)
    stats = {}
    for op, fs in frames.items():
        df = pd.concat(fs, ignore_index=True)
        if df.empty:
            continue
        ops[op]["columns"] = list(df.columns)
        df.astype(str).to_parquet(P / "data" / DSID / f"{op}_{today:%Y%m%d}.parquet")
        stats[op] = col_stats(df)
    (P / "stats" / f"{DSID}.json").write_text(json.dumps(stats, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    run = {"id": DSID, "channel": "external", "site": "open.neis.go.kr", "ok_ops": sum(o["ok"] for o in ops.values()),
           "ops": list(ops.values())}
    (P / "runs" / f"{DSID}.json").write_text(json.dumps(run, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    return {op: {"rows": o["rows"], "total": o["total_count"], "calls": o["calls"]} for op, o in ops.items()}


if __name__ == "__main__":
    print(run())
