"""Phase 2-e~g 호출·다운로드·셀 통계 (BUILD-PLAN §2.1).

데이터 1건 = 1 run. 명세(probe/specs/{id}.json)의 오퍼레이션마다 최소 파라미터로 호출 → JSON 우선, 실패 시 XML →
페이지를 넘기며 최대 max_rows행 → parquet 저장 → 컬럼별 통계.
필수 파라미터는 이름 규칙으로 표본값을 채운다(PARAM_GUESS). 못 채우면 run에 needs_params로 남긴다.

출력: probe/runs/{id}.json · probe/data/{id}/{op}_{date}.parquet · probe/stats/{id}.json
인증키: env DATA_GO_KR_SERVICE_KEY (포털 마이페이지 일반 인증키, Decoding) — secrets/ 에서 읽어 넣는다
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import time
from pathlib import Path
from typing import Any

import httpx
import pandas as pd
from lxml import etree

from pds import config

ROOT = config.ROOT / "probe"
KEY_FILE = config.ROOT / "secrets" / "keys.json"
TODAY = dt.date.today()
LAST_MONTH = (TODAY.replace(day=1) - dt.timedelta(days=1))

# 이름(소문자, 정규식) → 표본값. 위에서부터 첫 일치
PARAM_GUESS: list[tuple[str, Any]] = [
    (r"^(servicekey|service_key)$", None),
    (r"^(pageno|page_no|page|pageindex)$", 1),
    (r"^(numofrows|num_of_rows|rows|perpage|pagesize|page_size|size)$", 100),
    (r"^(_type|type|datatype|resulttype|returntype|resulttyp|restype|response_type)$", "json"),
    (r"^lawd_cd$", "11110"),
    (r"^deal_ymd$", LAST_MONTH.strftime("%Y%m")),
    (r"(sigungucd|signgucd|sggcd|sigungu_cd|sigungucode)", "11110"),
    (r"(bjdongcd|bjdong_cd)", "10100"),
    (r"(sidocd|ctprvncd|sido_cd|areacode|ctpv)", "11"),
    (r"^mobileos$", "ETC"),
    (r"^mobileapp$", "PDS"),
    (r"^brtccode$", "11"),
    (r"^signgucode$", "11110"),
    (r"(start|from|st|begin|bgng|srch_?fr|fr)_?(date|dt|de|ymd)|(date|dt|ymd)_?(from|start|fr)$",
     (TODAY - dt.timedelta(days=30)).strftime("%Y%m%d")),
    (r"(end|to|ed|srch_?to)_?(date|dt|de|ymd)|(date|dt|ymd)_?(to|end)$", TODAY.strftime("%Y%m%d")),
    (r"^(?!.*(code|cd|nm|no)$).*(ymd|date|_dt|_de)$", TODAY.strftime("%Y%m%d")),
    (r"(yyyymm|ym)$", LAST_MONTH.strftime("%Y%m")),
    (r"(year|yyyy|yr)$", str(TODAY.year - 1)),
    (r"(radius)$", 500),
    (r"^(cx|lon|x|mapx|longitude)$", "126.9780"),
    (r"^(cy|lat|y|mapy|latitude)$", "37.5665"),
    (r"(divid|key|indsLclsCd)$", None),
]


def service_key() -> str:
    if os.getenv("DATA_GO_KR_SERVICE_KEY"):
        return os.environ["DATA_GO_KR_SERVICE_KEY"]
    if KEY_FILE.exists():
        return json.loads(KEY_FILE.read_text(encoding="utf-8"))["data.go.kr"]["decoding"]
    raise RuntimeError("data.go.kr 인증키 없음 — secrets/keys.json 또는 DATA_GO_KR_SERVICE_KEY")


def guess(name: str) -> Any:
    n = name.lower()
    for pat, val in PARAM_GUESS:
        if re.search(pat, n, re.I):
            return val
    return None


def build_params(op: dict, key: str, rows: int, fmt: str) -> tuple[dict, list[str]]:
    params, missing = {"serviceKey": key}, []
    names = {p["name"] for p in op.get("params") or [] if p.get("in") in (None, "query")}
    for p in op.get("params") or []:
        name = p["name"]
        if p.get("in") not in (None, "query") or name.lower() in ("servicekey", "service_key"):
            continue
        if name.startswith("cond[") and not p.get("required"):
            continue  # odcloud 선택 필터 — 예시값이 너무 좁아 0건이 된다
        ex = p.get("example")
        usable = ex not in (None, "") and not re.search(r"인증키|URL ?Encode|servicekey", str(ex), re.I)
        v = ex if usable else guess(name)   # 포털 예시값(paramtrBassValue) 우선, 없으면 이름 규칙
        if re.search(r"(numofrows|rows|perpage|pagesize|size)$", name, re.I):
            v = rows
        if re.search(r"^(_type|type|datatype|resulttype|returntype)$", name, re.I):
            v = fmt
        if v is not None:
            params[name] = v
        elif p.get("required"):
            missing.append(name)
    if not names:  # 명세에 파라미터가 없는 구형 API: 통상 이름으로 시도
        params.update({"pageNo": 1, "numOfRows": rows, "_type": fmt, "type": fmt, "dataType": fmt.upper()})
    return params, missing


def _items_json(obj: Any) -> list[dict] | None:
    """흔한 포털 JSON 형태에서 행 목록을 찾는다: response.body.items.item / data / items / list …"""
    if isinstance(obj, list):
        return obj if obj and isinstance(obj[0], dict) else None
    if not isinstance(obj, dict):
        return None
    for k in ("item", "items", "data", "list", "row", "rows", "result", "body", "response"):
        if k in obj:
            got = _items_json(obj[k])
            if got is not None:
                return got
    for v in obj.values():
        if isinstance(v, (dict, list)):
            got = _items_json(v)
            if got:
                return got
    return None


def _items_xml(text: str) -> list[dict] | None:
    try:
        root = etree.fromstring(text.encode("utf-8") if isinstance(text, str) else text)
    except etree.XMLSyntaxError:
        return None
    items = root.findall(".//item") or root.findall(".//row")
    if not items:  # 행 태그가 제각각인 API: 자식 요소를 가진 같은 태그가 2번 이상(또는 total>0인데 1번) 반복되는 요소
        from collections import Counter
        cand = Counter(e.tag for e in root.iter() if len(e) and all(len(c) == 0 for c in e))
        tag = next((t for t, n in cand.most_common() if n >= 1 and t not in ("header", "cmmMsgHeader")), None)
        items = root.findall(f".//{tag}") if tag else []
    return [{c.tag: (c.text or "").strip() for c in it} for it in items] if items else []


def _total(obj: Any) -> int | None:
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k.lower() in ("totalcount", "total_count", "totalcnt", "matchcount", "currentcount") and str(v).isdigit():
                return int(v)
            t = _total(v)
            if t is not None:
                return t
    return None


def _error_text(text: str) -> str | None:
    m = re.search(r"<(returnAuthMsg|errMsg|resultMsg|returnReasonCode)>([^<]+)<", text)
    if m and m.group(2).strip().upper() not in ("NORMAL SERVICE.", "NORMAL SERVICE", "00", "OK", "정상"):
        return f"{m.group(1)}={m.group(2).strip()}"
    if "SERVICE_KEY_IS_NOT_REGISTERED" in text or "Unauthorized" in text[:200]:
        return "unauthorized"
    return None


OVERRIDES = config.KNOWLEDGE / "probe_params.yaml"


def overrides(dataset_id: str, op_path: str) -> dict:
    """사람이 정한 파라미터 (knowledge/probe_params.yaml: {id: {'*' 또는 op path: {param: value}}})."""
    if not OVERRIDES.exists():
        return {}
    import yaml
    d = (yaml.safe_load(OVERRIDES.read_text(encoding="utf-8")) or {}).get(str(dataset_id)) or {}
    return {**(d.get("*") or {}), **(d.get(op_path) or {})}


def refresh_dates(params: dict) -> dict:
    """예시 날짜를 형식을 유지한 채 최근 값으로 (실시간·최근 N일만 조회되는 API용)."""
    now = dt.datetime.now()
    y = now - dt.timedelta(days=1)
    out = {}
    for k, v in params.items():
        sv = str(v)
        if k.lower() in ("servicekey", "pageno", "numofrows", "page", "perpage"):
            out[k] = v
        elif re.fullmatch(r"20\d{10}", sv):
            out[k] = (now - dt.timedelta(hours=1)).strftime("%Y%m%d%H00")
        elif re.fullmatch(r"20\d{6}", sv):
            out[k] = y.strftime("%Y%m%d")
        elif re.fullmatch(r"20\d{2}-\d{2}-\d{2}", sv):
            out[k] = y.strftime("%Y-%m-%d")
        elif re.fullmatch(r"20\d{4}", sv):
            out[k] = LAST_MONTH.strftime("%Y%m")
        elif re.fullmatch(r"20\d{2}", sv) and re.search(r"(year|yr|yyyy)", k, re.I):
            out[k] = str(TODAY.year - 1)
        else:
            out[k] = v
    return out


def call_op(client: httpx.Client, base: str, op: dict, key: str, max_rows: int, rows: int = 100,
            extra: dict | None = None) -> dict:
    url = base.rstrip("/") + op["path"]
    rec: dict = {"op": op["path"], "url": url, "attempts": []}
    params, missing = build_params(op, key, rows, "json")
    if extra:
        params.update(extra)
        for k in [k for k, v in extra.items() if v is None]:  # 값 None = 이 파라미터를 보내지 않음
            params.pop(k, None)
        missing = [m for m in missing if m not in extra]
    rec["needs_params"] = missing
    rec["params"] = {k: v for k, v in params.items() if k.lower() not in ("servicekey", "service_key")}  # 실측 조건 기록 (키 제외)
    frames, page, total, fmt = [], 1, None, "json"
    while True:
        params = {**params}
        for k in list(params):
            if re.search(r"^(pageno|page_no|page|pageindex)$", k, re.I):
                params[k] = page
        t0 = time.time()
        try:
            if op.get("method") == "POST" or "__body__" in params:  # JSON 본문 API (예: 국세청 사업자 상태조회)
                body = params.pop("__body__", None)
                q = {k: v for k, v in params.items() if k.lower() == "servicekey"}
                r = client.post(url, params=q, json=body, timeout=40)
                params["__body__"] = body
            else:
                r = client.get(url, params=params, timeout=40)
        except Exception as e:  # noqa: BLE001
            rec["attempts"].append({"page": page, "error": repr(e)[:200]})
            break
        ms = int((time.time() - t0) * 1000)
        text = r.text
        att = {"page": page, "status": r.status_code, "ms": ms, "bytes": len(r.content), "fmt": fmt}
        rows_ = None
        if text.lstrip().startswith(("{", "[")):
            try:
                obj = r.json()
                rows_ = _items_json(obj)
                total = total or _total(obj)
            except json.JSONDecodeError:
                pass
        if rows_ is None:
            err = _error_text(text)
            if err:
                att["error"] = err
            rows_ = _items_xml(text)
            if rows_ is not None:
                att["fmt"] = "xml"
                m = re.search(r"<totalCount>(\d+)</totalCount>", text)
                total = total or (int(m.group(1)) if m else None)
        att["rows"] = len(rows_ or [])
        if rows_ is None:
            att["body_head"] = text[:300]
        rec["attempts"].append(att)
        if not rows_:
            break
        frames.append(pd.DataFrame(rows_))
        got = sum(len(f) for f in frames)
        if got >= max_rows or (total is not None and got >= total) or len(rows_) < rows:
            break
        page += 1
        time.sleep(0.3)
    rec["total_count"] = total
    rec["rows"] = sum(len(f) for f in frames)
    rec["ok"] = rec["rows"] > 0
    rec["_df"] = pd.concat(frames, ignore_index=True) if frames else None
    return rec


def col_stats(df: pd.DataFrame) -> dict:
    out = {}
    for c in df.columns:
        s = df[c]
        s_str = s.astype(str).where(s.notna())
        nonnull = s_str.dropna()
        nonnull = nonnull[nonnull.str.strip() != ""]
        info = {"null_rate": round(1 - len(nonnull) / max(len(s), 1), 4), "unique": int(nonnull.nunique()),
                "top": nonnull.value_counts().head(10).to_dict()}
        num = pd.to_numeric(nonnull.str.replace(",", ""), errors="coerce")
        if len(nonnull) and num.notna().mean() > 0.95:
            info.update({"type": "number", "min": float(num.min()), "p50": float(num.median()), "max": float(num.max())})
        else:
            dates = pd.to_datetime(nonnull.str.replace(r"[^\d]", "", regex=True).str[:8], format="%Y%m%d", errors="coerce")
            if len(nonnull) and dates.notna().mean() > 0.9:
                info.update({"type": "date", "min": str(dates.min().date()), "max": str(dates.max().date())})
            else:
                info["type"] = "code" if info["unique"] <= max(50, len(nonnull) * 0.05) else "text"
        out[str(c)] = info
    return out


def run_one(dataset_id: str, max_rows: int = 1000, max_ops: int = 6) -> dict:
    spec = json.loads((ROOT / "specs" / f"{dataset_id}.json").read_text(encoding="utf-8"))
    key = service_key()
    run = {"id": dataset_id, "started_at": dt.datetime.now().isoformat(timespec="seconds"), "ops": []}
    if spec.get("swagger"):
        scheme = "https" if "https" in (spec.get("schemes") or ["https"]) else "http"
        base = f"{scheme}://{spec['host']}{spec.get('base_path') or ''}"
        ops = spec["operations"]
    elif spec.get("operations"):  # 구형 API: 상세 페이지 표에서 읽은 오퍼레이션 (path가 전체 URL)
        base, ops = "", [o for o in spec["operations"] if o.get("path")]
    elif spec.get("request_url"):  # 외부 요청주소형 (기관 서버, 파라미터 명세 없음)
        base, ops = "", [{"path": spec["request_url"], "params": []}]
    else:
        eps = [e for e in spec.get("endpoints") or [] if e.count("/") >= 5]
        if not eps:
            run["skipped"] = "no endpoint in spec (파일/표준데이터 또는 참고문서 확인 필요)"
            return run
        base = ""
        ops = [{"path": e, "params": []} for e in eps]
    (ROOT / "data" / dataset_id).mkdir(parents=True, exist_ok=True)
    stats = {}
    with httpx.Client(headers={"User-Agent": "pds-probe/0.1"}) as client:
        for op in ops[:max_ops]:
            extra = overrides(dataset_id, op["path"])
            if op.get("method", "GET") != "GET" and "__body__" not in extra:
                continue  # 본문이 필요한 POST는 probe_params.yaml에 __body__가 있을 때만
            rec = call_op(client, base, op, key, max_rows, extra=extra)
            if not rec["ok"]:  # 날짜를 최근으로 바꿔 한 번 더
                params0, _ = build_params(op, key, 100, "json")
                fresh = {k: v for k, v in refresh_dates({**params0, **extra}).items() if params0.get(k, extra.get(k)) != v}
                if fresh:
                    rec2 = call_op(client, base, op, key, max_rows, extra={**extra, **fresh})
                    if rec2["ok"]:
                        rec2["date_refreshed"] = fresh
                        rec = rec2
            df = rec.pop("_df")
            if df is not None:
                name = re.sub(r"[^\w]+", "_", op["path"]).strip("_") or "op"
                df.astype(str).to_parquet(ROOT / "data" / dataset_id / f"{name}_{TODAY:%Y%m%d}.parquet")
                rec["columns"] = list(map(str, df.columns))
                stats[op["path"]] = col_stats(df)
            run["ops"].append(rec)
    run["finished_at"] = dt.datetime.now().isoformat(timespec="seconds")
    run["ok_ops"] = sum(1 for o in run["ops"] if o["ok"])
    for sub, obj in (("runs", run), ("stats", stats)):
        (ROOT / sub).mkdir(parents=True, exist_ok=True)
        (ROOT / sub / f"{dataset_id}.json").write_text(json.dumps(obj, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    return run
