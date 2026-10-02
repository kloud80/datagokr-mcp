"""외부 사이트 검증 — 키를 이미 가진 4곳(브이월드·서울 열린데이터광장·법제처·나이스)의 링크형 데이터 (python -m pds.probe.external_sites).

포털 '바로가기'가 가리키는 제공처 페이지(knowledge/expansion/external_links.json)에서 실제 호출 주소를 찾아 부른다:
  브이월드   검색 페이지(searchKeyword) → 상세(apiNum) → api.vworld.kr 주소 + 샘플값이 채워진 요청변수(필수만 + format/numOfRows)
  서울       openApiView(infId) 샘플 주소 /{KEY}/json/{서비스}/1/100/… (swopenAPI 포함), openapi.seoul.go.kr:8088 직접 링크
  법제처     guideResult(htmlName)의 target → law.go.kr/DRF/lawSearch.do (목록형만 — 본문형은 ID가 필요해 needs_params)
  나이스     open.neis.go.kr/hub/{서비스} (학교코드가 필요하면 학교기본정보 첫 행으로 다시)
출력: probe/runs|stats|data/{id} — 포털 API 검증과 같은 형식. 키·OC 값은 기록하지 않는다 (params에서 뺀다)
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import sys
from urllib.parse import parse_qs, urlparse

import httpx
import pandas as pd

from pds import config
from pds.probe.deep import _items_json, _items_xml, _total, col_stats

P = config.ROOT / "probe"
UA = {"User-Agent": "Mozilla/5.0 (pds-probe)"}
SECRET_PARAMS = {"key", "KEY", "OC", "serviceKey", "domain"}
# 브이월드 요청변수의 기본 표본 (상세 페이지 샘플이 없을 때) — 서울 성동구 성수동1가 필지
VW_SAMPLE = {"pnu": "1120011400100010000", "ldCode": "1120011400", "stdrYear": str(dt.date.today().year - 1),
             "bjdCode": "1120011400", "sigunguCd": "11200", "admCode": "11200", "attrFilter": "", "geomFilter": ""}
# 나이스 서비스 — 제목으로 (안내 페이지가 스크립트로 그려져 주소가 안 보일 때)
NEIS_SVC = [("급식", "mealServiceDietInfo"), ("학사일정", "SchoolSchedule"), ("학교기본정보", "schoolInfo"), ("학원", "acaInsTiInfo"),
            ("학급", "classInfo"), ("초등학교 시간표", "elsTimetable"), ("중학교 시간표", "misTimetable"), ("고등학교 시간표", "hisTimetable")]


def _keys() -> dict:
    v = json.loads((config.ROOT / "secrets" / "keys.json").read_text(encoding="utf-8")).get("vworld", {})
    return {"vworld": v.get("key"), "vworld_domain": v.get("domain", ""), "seoul": os.getenv("DATA_SEOUL_API_KEY"),
            "law": os.getenv("OPEN_LAW_GO_KR_API_KEY"), "neis": os.getenv("OPEN_NEIS_API_KEY")}


def _row_lists(o) -> list[dict] | None:
    if isinstance(o, dict):
        v = o.get("row")
        if isinstance(v, list) and v and isinstance(v[0], dict):
            return v
        for x in o.values():
            got = _row_lists(x)
            if got:
                return got
    elif isinstance(o, list):
        for x in o:
            got = _row_lists(x)
            if got:
                return got
    return None


def _parse(text: str) -> tuple[list[dict] | None, int | None, str | None]:
    """행·전체 건수·오류 문구."""
    if text.lstrip().startswith(("{", "[")):
        try:
            o = json.loads(text)
        except json.JSONDecodeError:
            return None, None, "json 파싱 실패"
        feats = (((o.get("response") or {}).get("result") or {}).get("featureCollection") or {}).get("features") if isinstance(o, dict) else None
        if feats is not None:  # 브이월드 2D 데이터 API — 피처의 속성만 행으로
            rec = (o.get("response") or {}).get("record") or {}
            err = None if feats else str((o.get("response") or {}).get("error") or (o.get("response") or {}).get("status"))[:150]
            return [f.get("properties") or {} for f in feats], int(rec.get("total") or 0) or None, err
        rows = _row_lists(o) or _items_json(o)  # 나이스 {서비스: [{head}, {row: […]}]} — head가 아니라 row
        err = None
        s = json.dumps(o, ensure_ascii=False)[:600]
        m = re.search(r'"(?:RESULT|result|status|resultCode)"[^}]{0,120}?"(?:MESSAGE|message|resultMsg|text)"\s*:\s*"([^"]+)"', s)
        if not rows and m:
            err = m.group(1)
        return rows, _total(o), err
    rows = _items_xml(text)
    m = re.search(r"<(?:totalCount|list_total_count|totalCnt)>(\d+)<", text)
    e = re.search(r"<(?:MESSAGE|message|resultMsg|errMsg|returnAuthMsg)>([^<]+)<", text)
    return rows, int(m.group(1)) if m else None, (e.group(1) if e and not rows else None)


# ───────────────────────── 사이트별 호출 주소 찾기
VW_BOX = "BOX(126.95,37.52,127.10,37.60)"  # 서울 도심 — 0건이면 전국 상자로 한 번 더


def _vworld(c: httpx.Client, link: str, keys: dict) -> dict | None:
    """링크 형태: 2D 데이터 안내(svcIde) · API 상세(apiNum) · 검색(searchKeyword). 그 밖(WMS 안내 등)은 데이터가 아니라 None."""
    q = parse_qs(urlparse(link).query)
    secret = {"key": keys["vworld"], "domain": keys["vworld_domain"]}
    if "2ddataguide2_s002" in link and q.get("svcIde"):
        g = c.get("https://www.vworld.kr/dev/v4dv_2ddataguide2_s002.do", params={"svcIde": q["svcIde"][0]}).text
        layer = next(iter(re.findall(r"\b(LT_[A-Z]_\w+|LP_[A-Z]{2}_\w+)\b", g)), None)
        if not layer:
            return None
        return {"site": "vworld", "url": "https://api.vworld.kr/req/data", "op": layer,
                "params": {"service": "data", "request": "GetFeature", "data": layer, "geomFilter": VW_BOX, "format": "json",
                           "size": 100, "geometry": "false", "attribute": "true", "crs": "EPSG:4326"}, "secret": secret}
    if "dtna_apiSvcFc_s001" in link and q.get("apiNum"):
        num, tit = q["apiNum"][0], ""
    else:
        kw = q.get("searchKeyword", [""])[0]
        if not kw.strip():
            return None  # 검색어가 없으면 목록 첫 항목이 엉뚱한 API다
        t = c.get("https://www.vworld.kr/dtna/dtna_apiSvcList_s001.do", params={"searchKeyword": kw}).text
        items = re.findall(r"goDetail\('(\d+)'\).*?<div class=\"tit\">([^<]+)</div>.*?<div class=\"format\">(.*?)</div>", t, re.S)
        if not items:
            return None

        def rank(it):  # 속성조회(JSON) > 그 밖의 JSON > WFS(XML) — WMS는 그림이라 뺀다
            _, tit, fmt = it
            return (0 if "속성" in tit and "json" in fmt else 1 if "json" in fmt else 2 if "WFS" in tit else 3)
        num, tit, _ = sorted(items, key=rank)[0]
        if "WMS" in tit:
            return None
    d = c.get("https://www.vworld.kr/dtna/dtna_apiSvcFc_s001.do", params={"apiNum": num}).text
    tit = tit or (re.findall(r'<h\d[^>]*class="[^"]*tit[^"]*"[^>]*>([^<]+)<', d) or [f"api{num}"])[0].strip()
    urls = re.findall(r"https?://api\.vworld\.kr/[\w/]+", d)
    if not urls:
        return None
    # 요청변수: 이름·필수여부, 샘플값(input value)
    req = dict(re.findall(r"\|([A-Za-z_]\w*)\|필수여부\|(필수|옵션)\|", "|" + re.sub(r"\|\s*(\|\s*)+", "|", re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "|", d))) + "|"))
    flat = re.sub(r"\|\s*(\|\s*)+", "|", re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "|", d)))
    samples = dict(VW_SAMPLE)
    samples |= {k: v for k, v in re.findall(r"\|(\w+)\|설명\|[^|]*\|샘플데이터\|([^|]+)\|", flat) if v.strip()}  # 출력 표의 샘플값
    samples |= {k: v for k, v in re.findall(r'<input[^>]*?(?:name|id)="(\w+)"[^>]*?value="([^"]+)"', d)}
    params = {k: samples.get(k, "") for k, v in req.items() if v == "필수" and k not in ("key", "domain")}
    params |= {"format": "json", "numOfRows": 100, "pageNo": 1} if "format" in req else {}
    return {"site": "vworld", "url": urls[0], "op": tit, "params": params, "secret": {"key": keys["vworld"], "domain": keys["vworld_domain"]}}


def _seoul(c: httpx.Client, link: str, keys: dict) -> dict | None:
    if "openapi.seoul.go.kr:8088" in link:
        m = re.search(r"8088/sample/\w+/(\w+)/", link)
        return {"site": "seoul", "url": f"http://openapi.seoul.go.kr:8088/{{KEY}}/json/{m.group(1)}/1/100/", "op": m.group(1),
                "params": {}, "secret": {"KEY": keys["seoul"]}} if m else None
    inf = re.search(r"(OA-\d+)", link)
    if not inf:
        return None
    t = c.get("https://data.seoul.go.kr/dataList/openApiView.do", params={"infId": inf.group(1), "srvType": "A"}).text
    m = re.search(r"(https?://(?:openapi\.seoul\.go\.kr:8088|swopenAPI\.seoul\.go\.kr/api/subway))/(?:sample|\(인증키\))/(?:xml|json)/(\w+)/\d+/\d+/?([^\"'<\s]*)", t)
    if not m:
        return None
    host, svc, rest = m.groups()
    url = f"{host}/{{KEY}}/json/{svc}/1/100/" + (rest.strip("/") + "/" if rest.strip("/") else "")
    return {"site": "seoul", "url": url, "op": svc, "params": {}, "secret": {"KEY": keys["seoul"]}}


def _law(c: httpx.Client, link: str, keys: dict) -> dict | None:
    t = c.get(link).text
    lst = re.search(r"lawSearch\.do\?[^\"'<]*?target=(\w+)", t)
    if lst:
        return {"site": "law", "url": "https://www.law.go.kr/DRF/lawSearch.do", "op": f"lawSearch:{lst.group(1)}",
                "params": {"target": lst.group(1), "type": "JSON", "display": 100, "page": 1}, "secret": {"OC": keys["law"]}}
    svc = re.search(r"lawService\.do\?[^\"'<]*?target=(\w+)", t)
    return {"site": "law", "url": None, "op": f"lawService:{svc.group(1) if svc else '?'}", "params": {}, "secret": {},
            "needs": "본문 조회형 — 목록에서 받은 ID가 필요"} if (svc or "target=" in t) else None


def _neis(c: httpx.Client, link: str, keys: dict, title: str = "") -> dict | None:
    t = c.get(link).text
    m = re.search(r"open\.neis\.go\.kr/hub/(\w+)", t)
    svc = m.group(1) if m else next((v for k, v in NEIS_SVC if k in title), None)
    if svc and svc.endswith("bgs"):  # 안내 페이지 이름(elsTimetablebgs) → 실제 서비스 이름
        svc = svc[:-3]
    return {"site": "neis", "url": f"https://open.neis.go.kr/hub/{svc}", "op": svc,
            "params": {"Type": "json", "pIndex": 1, "pSize": 100}, "secret": {"KEY": keys["neis"]}} if svc else None


SITES = {"www.vworld.kr": _vworld, "data.seoul.go.kr": _seoul, "openapi.seoul.go.kr:8088": _seoul,
         "open.law.go.kr": _law, "www.law.go.kr": _law, "open.neis.go.kr": _neis}


def _call(c: httpx.Client, spec: dict) -> tuple[list[dict] | None, int | None, str | None, int]:
    url = spec["url"]
    q = dict(spec["params"])
    for k, v in spec["secret"].items():
        if "{" + k + "}" in url:
            url = url.replace("{" + k + "}", v or "")
        else:
            q[k] = v
    r = c.get(url, params=q)
    rows, total, err = _parse(r.text)
    return rows, total, err, r.status_code


def _secrets(keys: dict) -> list[str]:
    """키와 .env의 계정 값 — 응답 안에 되돌아오는 경우가 있다(법제처 목록의 상세 링크에 OC=…)."""
    vals = [str(v) for v in keys.values() if v and len(str(v)) >= 4]
    for k, v in os.environ.items():
        if k.endswith(("_ID", "_PW", "_API_KEY", "_KEY")) and v and len(v) >= 4:
            vals.append(v)
    return sorted(set(vals), key=len, reverse=True)


def _mask(df: pd.DataFrame, keys: dict) -> pd.DataFrame:
    vals = _secrets(keys)
    if not vals:
        return df
    pat = "|".join(r"(?<![\w])" + re.escape(v) + r"(?![\w])" for v in vals)
    return df.apply(lambda c: c.str.replace(pat, "***", regex=True))


def run_one(c: httpx.Client, rec: dict, keys: dict) -> dict:
    dsid, link = rec["id"], rec["link"]
    host = urlparse(link).netloc
    run = {"id": dsid, "kind": "external", "site": host, "link": link, "started_at": dt.datetime.now().isoformat(timespec="seconds"), "ops": []}
    try:
        spec = SITES[host](c, link, keys, rec.get("title", "")) if host == "open.neis.go.kr" else SITES[host](c, link, keys)
    except Exception as e:  # noqa: BLE001
        spec, run["error"] = None, f"주소 찾기 실패: {type(e).__name__}: {str(e)[:150]}"
    if not spec or not spec.get("url"):
        run["ok_ops"] = 0
        run["skipped"] = (spec or {}).get("needs") or run.get("error") or "호출 주소를 찾지 못함"
    else:
        op = {"op": spec["op"], "url": spec["url"].replace("{KEY}/", ""), "params": spec["params"], "attempts": []}
        try:
            rows, total, err, status = _call(c, spec)
            if not rows and spec["params"].get("geomFilter") == VW_BOX:  # 서울 도심에 없는 레이어(비행구역·해안 등) — 전국 상자
                spec["params"] |= {"geomFilter": "BOX(124.5,33.0,131.0,38.7)", "size": 100}
                rows, total, err, status = _call(c, spec)
                op["params"] = spec["params"]
            if not rows and spec["site"] == "neis" and err and "필수" in err:  # 학교코드가 필요한 서비스 — 학교기본정보 첫 행으로
                base, _, _, _ = _call(c, {**spec, "url": "https://open.neis.go.kr/hub/schoolInfo"})
                if base:
                    day = dt.date.today() - dt.timedelta(days=(dt.date.today().weekday() + 3) % 7 + 1)  # 지난 평일 근처
                    spec["params"] |= {"ATPT_OFCDC_SC_CODE": base[0].get("ATPT_OFCDC_SC_CODE"), "SD_SCHUL_CODE": base[0].get("SD_SCHUL_CODE")}
                    if "Timetable" in spec["op"] or "meal" in spec["op"]:
                        spec["params"] |= {"ALL_TI_YMD" if "Timetable" in spec["op"] else "MLSV_YMD": day.strftime("%Y%m%d")}
                    rows, total, err, status = _call(c, spec)
                    op["params"] = spec["params"]
            op["attempts"].append({"page": 1, "status": status, "rows": len(rows or []), **({"error": err} if err else {})})
            op.update({"ok": bool(rows), "rows": len(rows or []), "total_count": total})
            if rows:
                df = _mask(pd.DataFrame(rows).astype(str), keys)
                op["columns"] = list(map(str, df.columns))
                (P / "data" / dsid).mkdir(parents=True, exist_ok=True)
                df.astype(str).to_parquet(P / "data" / dsid / f"ext_{dt.date.today():%Y%m%d}.parquet")
                (P / "stats").mkdir(parents=True, exist_ok=True)
                (P / "stats" / f"{dsid}.json").write_text(json.dumps({spec["op"]: col_stats(df)}, ensure_ascii=False, indent=1, default=str),
                                                         encoding="utf-8")
        except Exception as e:  # noqa: BLE001
            op.update({"ok": False, "error": f"{type(e).__name__}: {str(e)[:150]}"})
        run["ops"].append(op)
        run["ok_ops"] = int(bool(op.get("ok")))
    run["finished_at"] = dt.datetime.now().isoformat(timespec="seconds")
    text = json.dumps(run, ensure_ascii=False, indent=1, default=str)
    for v in _secrets(keys):  # 안전장치 — 키·계정 값이 섞여 들어갔으면 지운다
        text = re.sub(r"(?<![\w])" + re.escape(v) + r"(?![\w])", "***", text)
    (P / "runs" / f"{dsid}.json").write_text(text, encoding="utf-8")
    return run


def main() -> dict:
    sys.stdout.reconfigure(encoding="utf-8")
    keys = _keys()
    links = json.loads((config.KNOWLEDGE / "expansion" / "external_links.json").read_text(encoding="utf-8"))
    todo = [r for r in links if urlparse(r.get("link") or "").netloc in SITES]
    out = []
    with httpx.Client(timeout=40, follow_redirects=True, headers=UA) as c:
        for r in todo:
            run = run_one(c, r, keys)
            out.append(run)
            print(f"  {r['id']} {'성공' if run.get('ok_ops') else '실패'} {r['title'][:36]} {run.get('skipped') or (run['ops'][0].get('error') if run['ops'] else '') or ''}"[:160], flush=True)
    # targets.json 상태 갱신
    path = config.KNOWLEDGE / "targets.json"
    t = json.loads(path.read_text(encoding="utf-8"))
    ok = {r["id"]: bool(r.get("ok_ops")) for r in out}
    for x in t:
        if x["id"] in ok:
            x["status"] = "verified" if ok[x["id"]] else "failed"
    path.write_text(json.dumps(t, ensure_ascii=False, indent=1), encoding="utf-8")
    from collections import Counter
    res = {"대상": len(out), "성공": sum(ok.values()), "사이트별": dict(Counter((r["site"], bool(r.get("ok_ops"))) for r in out))}
    print(res)
    return res


if __name__ == "__main__":
    main()
