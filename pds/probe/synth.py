"""Phase 2 종합 — 받은 실데이터(parquet)에서 연계 키·좌표·날짜·형식을 값 기준으로 판정해 구조 설계용 표를 만든다.

키 판정은 컬럼 이름 + 값 패턴 둘 다 본다 (메타 추정이 아니라 실측):
  bizno 사업자번호(10자리) · crno 법인등록번호(13자리) · pnu 필지(19자리) · bjd 법정동(10자리) · sgg 시군구(5자리)
  sido 시도(2자리) · coord 위경도 · address 주소 · date 날짜 · ykiho 요양기관기호 등 도메인 키는 이름으로
출력: reports/phase2_round{n}_synthesis.md, probe/synthesis_round{n}.json, knowledge/targets.json status 갱신
"""
from __future__ import annotations

import datetime as dt
import json
import re

import pandas as pd

from pds import config
from pds.probe.report import _load, targets

P = config.ROOT / "probe"

NAME_KEYS = [
    ("bizno", r"(bizrno|brno|bsnm_?no|bizno|b_no|bno|busi.?no|bplc.?no|bzno|사업자.?번호|사업자등록번호|wkplBizno|bzmnNo)"),
    ("crno", r"(crno|jurirno|corp_?reg|법인등록번호|법인번호)"),
    ("pnu", r"(^pnu$|필지고유|platPlc|pnu_?cd)"),
    ("bjd", r"(bjd_?cd|bjdong|legaldong|법정동코드|ldong|stdg_?cd|lawd)"),
    ("sgg", r"(sigungu_?cd|signgu_?cd|sgg_?cd|sggcd|sigun_?cd|시군구코드|gugun|signguCode)"),
    ("sido", r"(ctprvn_?cd|sido_?cd|brtc_?cd|시도코드|siDo)"),
    ("coord", r"(^lat$|^lon$|^lng$|latitude|longitude|위도|경도|^x$|^y$|mapx|mapy|la$|lo$|xcrd|ycrd|lcLa|lcLo|wgs84)"),
    ("address", r"(addr|주소|rdnm|lnm|roadNm|adres|location|소재지)"),
    ("ykiho", r"ykiho"),
    ("apt_complex", r"(kaptCode|aptSeq|complex_?cd|단지코드)"),
    ("stock", r"(srtnCd|isinCd|stock_?cd|종목코드)"),
]


def _value_keys(s: pd.Series) -> set[str]:
    v = s.dropna().astype(str).str.replace(r"[-\s]", "", regex=True)
    v = v[v != ""].head(300)
    if v.empty:
        return set()
    out = set()
    digits = v.str.fullmatch(r"\d+")
    if digits.mean() > 0.9:
        lens = v.str.len().value_counts(normalize=True)
        top = lens.idxmax()
        if lens.max() > 0.8:
            out |= {10: {"bjd_or_bizno"}, 13: {"crno"}, 19: {"pnu"}, 5: {"sgg5"}}.get(top, set())
    num = pd.to_numeric(v, errors="coerce")
    if num.notna().mean() > 0.9:
        if num.between(33, 39).mean() > 0.9:
            out.add("lat")
        elif num.between(124, 132).mean() > 0.9:
            out.add("lon")
    if v.str.contains(r"(?:시|도)\S*\s*\S+(?:구|군|시)").mean() > 0.6 if not digits.mean() > 0.9 else False:
        out.add("address_text")
    return out


def analyse(dsid: str) -> dict:
    files = sorted((P / "data" / dsid).glob("*.parquet"))
    cols, keys, dates, rows = {}, set(), {}, 0
    for f in files:
        df = pd.read_parquet(f)
        rows += len(df)
        for c in df.columns:
            c = str(c)
            hit = {k for k, pat in NAME_KEYS if re.search(pat, c, re.I)}
            vk = _value_keys(df[c])
            if "bjd_or_bizno" in vk:
                vk = {"bizno"} if "bizno" in hit or re.search(r"(biz|brno|bsnm|사업자)", c, re.I) else {"bjd"} if "bjd" in hit else {"code10"}
            if "sgg5" in vk:
                vk = {"sgg"} if ("sgg" in hit or re.search(r"(sgg|sigungu|signgu|lawd|시군구)", c, re.I)) else set()
            if {"lat", "lon"} & vk:
                vk = {"coord"}
            if "address_text" in vk:
                vk = {"address"}
            found = (hit & {"ykiho", "apt_complex", "stock", "address", "coord", "sido"}) | (vk & {"bizno", "crno", "pnu", "bjd", "sgg", "coord", "address"})
            if found:
                cols[c] = sorted(found)
                keys |= found
            s = df[c].dropna().astype(str).str.replace(r"[^\d]", "", regex=True).str[:8]
            d = pd.to_datetime(s[s.str.len() == 8], format="%Y%m%d", errors="coerce").dropna()
            if len(d) > max(5, len(df) * 0.5) and d.between("1990-01-01", "2030-12-31").mean() > 0.9:
                dates[c] = {"min": str(d.min().date()), "max": str(d.max().date())}
    latest = max((v["max"] for v in dates.values()), default=None)
    lag = (dt.date.today() - dt.date.fromisoformat(latest)).days if latest else None
    return {"id": dsid, "rows": rows, "files": len(files), "keys": sorted(keys), "key_columns": cols, "dates": dates,
            "latest": latest, "lag_days": lag}


def build(rnd: str = "1") -> str:
    summary = {r["id"]: r for r in json.loads((P / f"summary_round{rnd}.json").read_text(encoding="utf-8"))}
    out = []
    for t in targets(rnd):
        s = summary.get(t["id"], {})
        rec = {"id": t["id"], "title": t["title"], "sector": t["sector"], "subsector": t["subsector"], "verdict": s.get("verdict")}
        if (P / "data" / t["id"]).exists():
            rec.update(analyse(t["id"]))
        run = _load("runs", t["id"]) or {}
        fmts = {a.get("fmt") for o in run.get("ops", []) for a in o.get("attempts", []) if a.get("rows")}
        rec["formats"] = sorted(f for f in fmts if f)
        rec["total_count"] = s.get("total")
        rec["ms"] = s.get("ms")
        out.append(rec)
    (P / f"synthesis_round{rnd}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    # targets.json 상태 갱신
    tp = config.KNOWLEDGE / "targets.json"
    tj = json.loads(tp.read_text(encoding="utf-8"))
    by = {r["id"]: r for r in out}
    for t in tj:
        r = by.get(t["id"])
        if r:
            t["status"] = "verified" if r.get("rows") else "failed"
            t["probe"] = {k: r.get(k) for k in ("verdict", "rows", "total_count", "keys", "latest", "lag_days", "formats")}
    tp.write_text(json.dumps(tj, ensure_ascii=False, indent=1), encoding="utf-8")
    # 표
    KEYS = ["bizno", "crno", "pnu", "bjd", "sgg", "sido", "coord", "address", "ykiho", "apt_complex", "stock"]
    ok = [r for r in out if r.get("rows")]
    L = [f"# Phase 2 라운드 {rnd} 종합 — 실데이터 기준 연계 키·최신성", "",
         f"검증 성공 {len(ok)}/{len(out)}건. 키는 컬럼 이름과 실제 값 패턴(자릿수·좌표 범위)으로 판정했다. "
         "'최신'은 날짜 컬럼 최대값, '지연'은 오늘과의 차이(일).", "",
         "## 연계 키 매트릭스", "",
         "| 데이터 | 부문 | 행 | " + " | ".join(KEYS) + " | 최신 | 지연 |", "|---|---|---|" + "---|" * len(KEYS) + "---|---|"]
    for r in sorted(ok, key=lambda r: (-len(r["keys"]), r["sector"])):
        marks = " | ".join("●" if k in r["keys"] else "" for k in KEYS)
        L.append(f"| {r['title'][:38]} | {r['sector'].split(' - ')[1]} | {r['rows']:,} | {marks} | {r.get('latest') or ''} | "
                 f"{'' if r.get('lag_days') is None else r['lag_days']} |")
    from collections import Counter
    kc = Counter(k for r in ok for k in r["keys"])
    L += ["", "## 키별 보유 데이터 수", "", " · ".join(f"{k} {kc.get(k, 0)}" for k in KEYS), "",
          "## 실패·보류", "", "| 판정 | 데이터 | 조치 |", "|---|---|---|"]
    ACTION = {"키미등록": "기관 전용 또는 신청 미완료 — 포털에서 상태 확인", "승인대기": "심의 승인 대기", "파라미터부족": "다른 API 결과(코드)가 필요한 필수 파라미터 — probe_params.yaml에 체인 값 지정",
              "응답0행": "예시값 조합이 0건이거나 제공기관 오류·기한 만료 — 개별 확인", "미실행": "명세 없음(외부 시스템)"}
    for r in out:
        if not r.get("rows") and r.get("verdict") != "파일(별도)":
            L.append(f"| {r['verdict']} | {r['title']} | {ACTION.get(r['verdict'], '')} |")
    path = config.REPORTS / f"phase2_round{rnd}_synthesis.md"
    path.write_text("\n".join(L) + "\n", encoding="utf-8")
    return str(path)


if __name__ == "__main__":
    import sys
    print(build(sys.argv[1] if len(sys.argv) > 1 else "1"))
