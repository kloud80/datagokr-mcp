"""열린재정(openfiscaldata.go.kr) 검증 — 포털 링크형을 열린재정 오픈API로 불러 확인한다 (OPEN_FISCAL_DATA_API_KEY).

1. 포털 링크의 통계 화면 UOPKOSDA01?odtId=… → 화면이 쓰는 조회 dtsStatsAcol/selectAcolViewList.do(odtId·rlsSvTyCd=A·odtSvSeq)에서
   요청 주소(https://openapi.openfiscaldata.go.kr/{서비스}), 요청 인자, 출력 항목(영문 이름 → 한글 이름)을 읽는다
2. 공통 인자 Key·Type=json·pIndex·pSize. 회계연도(FSCL_YY)가 필수인 서비스가 많다 — 인자 없이 → 올해부터 6년 전까지 거꾸로.
   그 밖의 필수 인자(요청 인자 표의 'String(필수)')는 실측으로 확인한 값을 넣는다 (DEFAULTS):
   조회기준(REVN_/ANEXP_INQ_STND_CD) 1 · 예산기금구분(BDG_FND_DIV_CD) 0 · 추경 차수(SBUDG_DGR) 0(본예산) · 집행월(EXE_M) 01 · 소관 코드(OFFC_CD) 004
3. 보고서·문서 내려받기 화면(fd·be·sm — odtId 없음)은 행 데이터가 아니라 실패로 남긴다
파일형(FILE_LINK)도 같은 통계 화면을 가리키면 같은 오픈API로 검증한다 (note에 적는다). 응답·기록에 키를 싣지 않는다.
실행: python -m pds.probe.openfiscal_sites [id…] · 조인 실측: … joins (→ logs/openfiscal_joins.json)
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
from pds.probe.deep import col_stats, save_run

P = config.ROOT / "probe"
B = "https://www.openfiscaldata.go.kr"
HOST = "openfiscaldata.go.kr"
DEFAULTS = {"REVN_INQ_STND_CD": "1", "ANEXP_INQ_STND_CD": "1", "BDG_FND_DIV_CD": "0", "SBUDG_DGR": "0", "EXE_M": "01", "OFFC_CD": "004"}


def key() -> str:
    return (os.environ.get("OPEN_FISCAL_DATA_API_KEY") or os.environ.get("OPENFISCAL_API_KEY") or "").strip()


def spec(c: httpx.Client, odt: str) -> dict | None:
    """통계 화면의 오픈API 안내 — 요청 주소·요청 인자·출력 항목. 오픈API 탭이 없으면 None."""
    for seq in ("1", "2", "3", "4", "5"):
        j = c.post(f"{B}/op/ko/sd/dtsStatsAcol/selectAcolViewList.do",
                   json={"odtId": odt, "rlsSvTyCd": "A", "odtSvSeq": seq, "odtNm": "", "paramVO": {"odtNm": ""}}).json()
        res = j.get("selectApiRes")
        if res and res.get("dmndUrl"):
            return {"url": res["dmndUrl"].strip(), "limit": res.get("apiDdDdSvLmCnt"),
                    "req": [v["dsColId"] for v in j.get("selectApiReqVarList") or [] if v.get("dsColId")],
                    "required": [v["dsColId"] for v in j.get("selectApiReqVarList") or [] if v.get("dsColId") and "필수" in str(v.get("reqType"))],
                    "labels": {v["dsColId"]: v.get("dpColHgNm") for v in j.get("selectApiOutputValList") or [] if v.get("dsColId")}}
    return None


def _call(c: httpx.Client, url: str, p: dict) -> tuple[list[dict], int | None, str | None]:
    time.sleep(0.3)
    try:
        r = c.get(url, params={"Key": key(), "Type": "json", "pIndex": 1, "pSize": 100, **p})
    except httpx.HTTPError as e:
        return [], None, f"{type(e).__name__}"
    try:
        j = json.loads(r.text)
        j = json.loads(j) if isinstance(j, str) else j  # 응답이 문자열로 한 번 더 감싸여 온다
    except ValueError:
        return [], None, f"json 아님 {r.status_code}"
    svc = url.rstrip("/").rsplit("/", 1)[-1]
    if isinstance(j, dict) and isinstance(j.get(svc), list):
        head = j[svc][0].get("head") or [{}, {}]
        rows = j[svc][1].get("row") or [] if len(j[svc]) > 1 else []
        return rows, head[0].get("list_total_count"), None if rows else str((head[1] or {}).get("RESULT"))
    return [], None, str((j or {}).get("RESULT") or j)[:150]


def attempts(req: list[str], required: list[str]):
    base = {k: DEFAULTS[k] for k in DEFAULTS if k in req and (k in required or k == "SBUDG_DGR")}
    yield dict(base)
    if "FSCL_YY" in req:
        for y in range(dt.date.today().year, dt.date.today().year - 7, -1):
            yield {**base, "FSCL_YY": str(y)}


def run_one(c: httpx.Client, dsid: str, link: str, kind: str) -> dict:
    run = {"id": dsid, "kind": "external", "site": "www.openfiscaldata.go.kr", "link": link,
           "started_at": dt.datetime.now().isoformat(timespec="seconds"), "ops": []}
    m = re.search(r"odtId=(\w+)", link or "")
    sp = spec(c, m.group(1)) if m else None
    if not sp:
        run.update({"ok_ops": 0, "error": "오픈API 없음 — 보고서·문서 내려받기 화면 (행 데이터 아님)" if not m else "통계 화면에 오픈API 탭이 없음"})
    else:
        rows, total, err, used = [], None, None, {}
        for p in attempts(sp["req"], sp["required"]):
            rows, total, err = _call(c, sp["url"], p)
            used = p
            if rows:
                break
        svc = sp["url"].rstrip("/").rsplit("/", 1)[-1]
        if not rows:
            run.update({"ok_ops": 0, "error": f"{svc} {err}"})
        else:
            df = pd.DataFrame(rows)
            (P / "data" / dsid).mkdir(parents=True, exist_ok=True)
            df.astype(str).to_parquet(P / "data" / dsid / f"openfiscal_{dt.date.today():%Y%m%d}.parquet")
            (P / "stats" / f"{dsid}.json").write_text(json.dumps({svc: col_stats(df)}, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
            run["ops"] = [{"op": svc, "url": sp["url"], "ok": True, "rows": len(df), "total_count": total, "columns": list(map(str, df.columns)),
                           "params": {**used, "Type": "json", "pIndex": 1, "pSize": 100}, "request_vars": sp["req"], "required": sp["required"], "labels": sp["labels"],
                           "daily_limit": sp["limit"] or None,
                           "note": "열린재정 오픈API · Key(query)" + (" — 포털 파일형 링크는 같은 통계 화면" if kind == "FILE_LINK" else "")
                                   + (f" · 회계연도 {used['FSCL_YY']} 기준" if used.get("FSCL_YY") else "")}]
            run["ok_ops"] = 1
    run["finished_at"] = dt.datetime.now().isoformat(timespec="seconds")
    save_run(run)  # 실패면 기존 성공 기록을 덮지 않는다
    return run


def main(only: set[str] | None = None) -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    if not key():
        raise SystemExit(".env에 OPEN_FISCAL_DATA_API_KEY가 없다")
    lk = pd.read_parquet(config.KNOWLEDGE / "expansion" / "site_links.parquet", columns=["id", "host", "link", "title", "api_kind_label"]).drop_duplicates("id")
    lk = lk[lk["host"].fillna("") == HOST]
    if only:
        lk = lk[lk["id"].isin(only)]
    ok = 0
    with httpx.Client(timeout=180, headers={"User-Agent": "Mozilla/5.0"}, follow_redirects=True) as c:
        for n, r in enumerate(lk.itertuples(), 1):
            run = run_one(c, r.id, r.link, r.api_kind_label)
            ok += bool(run.get("ok_ops"))
            print(f"  {n}/{len(lk)} {r.id} {'성공' if run.get('ok_ops') else '실패'} {str(r.title)[:30]} "
                  f"{run.get('error') or str(run['ops'][0]['rows']) + '행 / 전체 ' + str(run['ops'][0]['total_count'])}"[:170], flush=True)
    print({"열린재정 링크": len(lk), "성공": ok})




# ───────────────────────── 열린재정 데이터끼리 잇는 키 (python -m pds.probe.openfiscal_sites joins)
# (src, dst, 키, 관계, 메모) — 같은 회계연도(FSCL_YY)로 맞춰 받아 src 고유 키 중 dst에 있는 비율을 잰다
JOINS = [
    ("3073756", "15054312", ["FSCL_YY", "OFFC_NM", "ACTV_NM"], "one_to_many", "세부사업 예산 ↔ 세출 결산 — 같은 연도의 소관·단위사업으로 예산 대비 집행(결산)"),
    ("3073756", "15094215", ["FSCL_YY", "OFFC_NM", "SACTV_NM"], "one_to_many", "세부사업 예산 → 세목(비목)별 예산 — 사업 하나를 인건비·물건비 등으로 쪼갬"),
    ("3073756", "15058905", ["FSCL_YY", "OFFC_NM", "SACTV_NM"], "one_to_many", "본예산 세부사업 ↔ 추경 포함 세출예산 — 추경 차수(SBUDG_DGR)별 증감"),
    ("15076069", "3073756", ["FSCL_YY", "OFFC_NM", "SACTV_NM"], "many_to_one", "정부구매예산 → 세부사업 예산 — 사업 예산 중 조달 구매분"),
    ("15050495", "15056940", ["FSCL_YY", "OFFC_NM", "IKWAN_NM"], "many_to_many", "세입 예산 ↔ 세입 결산 — 소관·수입관별 예산 대비 실제 수납"),
    ("15076076", "15056940", ["FSCL_YY", "OFFC_NM"], "many_to_many", "월별 수입운용(당해 진행) ↔ 세입 결산(확정) — 소관 단위"),
    ("15076088", "3073756", ["OFFC_NM"], "many_to_many", "소관별 재정운영표(발생주의 비용) ↔ 세부사업 예산(현금주의) — 소관 이름으로"),
]
YEAR = "2025"
PAGES = 50  # 1천 행씩 — 세목·추경 예산은 연 4만 행이라 전부 받는다


def _all(c: httpx.Client, url: str, base: dict, cols: list[str]) -> set[tuple]:
    keys: set[tuple] = set()
    for pg in range(1, PAGES + 1):
        time.sleep(0.3)
        try:
            r = c.get(url, params={"Key": key(), "Type": "json", "pIndex": pg, "pSize": 1000, **base})
            j = json.loads(r.text)
            j = json.loads(j) if isinstance(j, str) else j
        except (httpx.HTTPError, ValueError):
            break
        svc = url.rstrip("/").rsplit("/", 1)[-1]
        rows = (j.get(svc) or [{}, {}])[1].get("row") if isinstance(j.get(svc), list) and len(j[svc]) > 1 else None
        if not rows:
            break
        keys |= {tuple(str(x.get(k) or "").strip() for k in cols) for x in rows}
        if len(rows) < 1000:
            break
    return keys


def joins() -> list[dict]:
    """JOINS를 실측 — probe/joins/{edge}.json을 쓰고, edges.yaml에 붙일 항목을 돌려준다."""
    out = []
    today = dt.date.today().isoformat()
    with httpx.Client(timeout=180, headers={"User-Agent": "Mozilla/5.0"}, follow_redirects=True) as c:
        for src, dst, on, rel, note in JOINS:
            side = []
            for i in (src, dst):
                op = json.loads((P / "runs" / f"{i}.json").read_text(encoding="utf-8"))["ops"][0]
                base = {k: v for k, v in op["params"].items() if k not in ("Type", "pIndex", "pSize")}
                if "FSCL_YY" in on:  # 연도로 맞추는 조인만 같은 해로 — 아니면 실측한 해 그대로
                    base["FSCL_YY"] = YEAR
                side.append(_all(c, op["url"], base, on))
            a, b = side
            rate = round(len(a & b) / len(a), 4) if a else None
            out.append({"src": src, "dst": dst, "on": on, "rel": rel, "note": note, "match_rate": rate, "n": len(a), "right_n": len(b), "at": today})
            print(src, "→", dst, on, {"src 키": len(a), "dst 키": len(b), "매칭률": rate}, flush=True)
    return out


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv(config.ROOT / ".env")
    if sys.argv[1:] == ["joins"]:
        sys.stdout.reconfigure(encoding="utf-8")
        (config.ROOT / "logs" / "openfiscal_joins.json").write_text(json.dumps(joins(), ensure_ascii=False, indent=1), encoding="utf-8")
    else:
        main(set(sys.argv[1:]) or None)
