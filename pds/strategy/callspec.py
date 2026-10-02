"""검증 때 실제로 성공한 호출을 다시 꾸민다 — 코드 생성·전략 응답의 fetch 정보.

명세(probe/specs) + 검증 기록(probe/runs)에서:
  · 성공한 오퍼레이션의 URL
  · 그때 쓴 파라미터 (기록이 있으면 그대로, 없으면 검증과 같은 규칙 build_params + probe_params.yaml + 날짜 갱신으로 재구성)
  · 페이지 파라미터 이름과 실제 페이지 크기(요청 1000이어도 100만 주는 API가 많다), 응답 형식(json/xml), 전체 건수
키 값은 담지 않는다.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache

from pds import config

PAGE_RE = re.compile(r"^(pageno|page_no|page|pageindex|startpage|currentpage)$", re.I)
SIZE_RE = re.compile(r"^(numofrows|num_of_rows|rows|perpage|pagesize|page_size|size|listcnt)$", re.I)
KEY_RE = re.compile(r"^(servicekey|service_key|authkey|apikey)$", re.I)
# 사용자가 목적에 맞게 바꿔야 하는 값 (검증 땐 표본값을 넣었다)
USER_RE = re.compile(r"(lawd_cd|sigungu|signgu|sgg|sido|ctprvn|bjdong|areacode|stage1|stage2|ymd|date|dt$|de$|yyyymm|ym$|year|"
                     r"^x$|^y$|lat|lon|radius|kaptcode|ykiho|hpid|bidntce|cond\[)", re.I)

PROBE = config.ROOT / "probe"


def _load(sub: str, i: str) -> dict | None:
    f = PROBE / sub / f"{i}.json"
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else None


def _spec_ops(spec: dict) -> tuple[str, list[dict]]:
    if spec.get("swagger"):
        scheme = "https" if "https" in (spec.get("schemes") or ["https"]) else "http"
        return f"{scheme}://{spec['host']}{spec.get('base_path') or ''}", spec["operations"]
    if spec.get("operations"):
        return "", [o for o in spec["operations"] if o.get("path")]
    if spec.get("request_url"):
        return "", [{"path": spec["request_url"], "params": []}]
    return "", [{"path": e, "params": []} for e in spec.get("endpoints") or [] if e.count("/") >= 5]


def _widen_ranges(params: dict) -> dict:
    """refresh_dates는 시작·끝을 같은 시각으로 맞춘다 — 기간 쌍(Bgn/End, start/end …)이면 시작을 7일 전으로."""
    import datetime as dt
    out = dict(params)
    for k, v in params.items():
        m = re.match(r"^(.*?)(bgn|begin|start|from|strt|st|fr)(.*)$", k, re.I)
        if not m:
            continue
        twin = next((x for x in params if x != k and re.fullmatch(re.escape(m.group(1)) + r"(end|to|ed)" + re.escape(m.group(3)), x, re.I)), None)
        if not twin or str(params[twin]) != str(v):
            continue
        sv = str(v)
        for fmt, n in (("%Y%m%d%H%M", 12), ("%Y%m%d", 8), ("%Y-%m-%d", 10), ("%Y%m", 6)):
            if len(sv) == n:
                try:
                    end = dt.datetime.strptime(sv, fmt)
                except ValueError:
                    continue
                days = 31 if n == 6 else 7
                out[k] = (end - dt.timedelta(days=days)).strftime(fmt if n != 12 else "%Y%m%d0000")
                break
    return out


def overrides_for(dsid: str, op_path: str) -> dict:
    from pds.probe.deep import overrides
    return overrides(dsid, op_path)


@lru_cache(maxsize=1024)
def call_spec(dsid: str, need: tuple[str, ...] = ()) -> dict | None:
    """성공한 호출 하나 — {url, method, params, user_params, page, size, page_size, fmt, total_count, verified_at}. 없으면 None.
    need: 조인에 쓰는 열 — 성공한 오퍼레이션 중 그 열을 돌려주는 것을 고른다 (상세 vs 기본정보처럼 열이 다르다)."""
    run = _load("runs", dsid)
    if not run:
        return None
    oks = [o for o in run.get("ops") or [] if o.get("ok")]
    rec = next((o for o in oks if need and set(need) <= set(o.get("columns") or [])), None) or (oks[0] if oks else None)
    if not rec:
        return None
    spec = _load("specs", dsid) or {}
    base, ops = _spec_ops(spec) if spec else ("", [])
    op = next((o for o in ops if o.get("path") == rec.get("op")), None)
    url = rec.get("url") or (base.rstrip("/") + rec["op"] if base and rec.get("op", "").startswith("/") else rec.get("op"))
    if not url or not str(url).startswith("http"):
        return None  # 외부 기관 전용 경로(브이월드 등)로 검증된 것 — 별도 안내
    if rec.get("params") is not None:
        params = dict(rec["params"])
    else:
        from pds.probe.deep import build_params, overrides
        params, _ = build_params(op or {"params": []}, "", 100, "json")
        params.update({k: v for k, v in overrides(dsid, rec.get("op", "")).items() if v is not None})
        params.update(rec.get("date_refreshed") or {})
    params = {k: v for k, v in params.items() if not KEY_RE.match(k) and k != "__body__"}
    page = next((k for k in params if PAGE_RE.match(k)), None)
    size = next((k for k in params if SIZE_RE.match(k)), None)
    att = rec.get("attempts") or []
    seen = [a.get("rows") or 0 for a in att if a.get("rows")]
    asked = int(params.get(size) or 100) if size else 100
    # 여러 쪽을 받았으면 실제로 준 크기, 한 쪽뿐이면(전체가 작았음) 요청한 크기
    page_size = max(seen) if len(seen) > 1 else asked
    for k in (page, size):
        params.pop(k, None)
    if op and op.get("params"):  # 선택 파라미터의 포털 예시값(서울의료원 등)은 범위를 좁혀 버린다 — 필수·형식만 남긴다
        req = {p["name"] for p in op["params"] if p.get("required")}
        params = {k: v for k, v in params.items() if k in req or re.match(r"^(_type|type|datatype|resulttype|returntype|output)$", k, re.I)
                  or k in (overrides_for(dsid, rec.get("op", "")))}
    from pds.probe.deep import refresh_dates
    params = _widen_ranges(refresh_dates(params))  # 예시 날짜(2015년 등)를 최근으로, 시작~끝은 최근 7일
    # 선택 파라미터 중 지역을 좁히는 것 — 목표 지역이 있으면 코드 생성이 채운다
    region = {}
    for prm in (op or {}).get("params") or []:
        n = prm["name"]
        if prm.get("required") or n in params:
            continue
        if re.search(r"OPN_ATMY_GRP_CD", n, re.I):
            region.setdefault("instt", n)
        elif re.search(r"(lawd_cd|sigungu_?c(o)?d|signgu_?cd|sgg_?cd)", n, re.I):
            region.setdefault("sgg5", n)
        elif re.search(r"ADDR.*LIKE", n, re.I):
            region.setdefault("addr_like", n)
    return {"url": url, "method": (op or {}).get("method", "GET"), "params": params,
            "user_params": sorted(k for k in params if USER_RE.search(k)), "region_params": region,
            "page": page, "size": size, "page_size": int(page_size) if page_size else 100,
            "paged": len(att) > 1 or bool(page), "fmt": next((a.get("fmt") for a in att if a.get("fmt")), "json"),
            "total_count": int(rec["total_count"]) if str(rec.get("total_count") or "").isdigit() else None,
            "verified_at": (run.get("started_at") or "")[:10], "columns": rec.get("columns") or []}
