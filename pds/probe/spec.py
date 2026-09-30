"""Phase 2-a 명세 수집 — 포털 상세 페이지(로그인 불필요)에서 오퍼레이션 명세를 뽑는다.

- openapi.do: 페이지에 swaggerJson(JS 템플릿 문자열)이 들어 있으면 그대로 파싱 → host·basePath·오퍼레이션·파라미터·응답 필드
  없으면(구형 API) '요청주소'·'서비스URL' 텍스트와 참고문서 목록만 기록
- standard.do / fileData.do: 파일 다운로드 정보(파일명·확장자·수정일)와 표준 API 여부
출력: probe/specs/{id}.json
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

import httpx
from lxml import html as lh

from pds import config

OUT = config.ROOT / "probe" / "specs"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/140 Safari/537.36"}


def _swagger(text: str) -> dict | None:
    m = re.search(r"const swaggerJson = `(.*?)`;", text, re.S)
    if not m or not m.group(1).strip():
        return None
    raw = m.group(1).replace("\\\\", "\\")  # JS 템플릿 문자열 → JSON 문자열
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return json.loads(raw, strict=False)


def _examples(sw: dict) -> dict[str, dict]:
    """포털 전용 swaggerOprtinVOs: 오퍼레이션별 요청변수 예시값(paramtrBassValue)·원천 URL."""
    out = {}
    for vo in sw.get("swaggerOprtinVOs") or []:
        ex = {r.get("paramtrNm"): r.get("paramtrBassValue") for r in vo.get("reqList") or [] if r.get("paramtrNm")}
        info = {"examples": ex, "origin_url": vo.get("oprtinUrl"), "name": vo.get("oprtinNm")}
        for k in (vo.get("operationId"), vo.get("gwSvcNm")):
            if k:
                out[k] = info
    return out


def _ops(sw: dict) -> list[dict]:
    ops, exs = [], _examples(sw)
    for path, methods in (sw.get("paths") or {}).items():
        shared = methods.get("parameters") or []  # 경로 단위 파라미터 (포털 swagger는 대부분 여기에 있다)
        for method, op in methods.items():
            if not isinstance(op, dict):
                continue
            ex = exs.get(op.get("operationId") or "") or exs.get(path.strip("/")) or {}
            params = [{"name": p.get("name"), "in": p.get("in"), "required": bool(p.get("required")),
                       "type": p.get("type") or (p.get("schema") or {}).get("type"), "desc": (p.get("description") or "")[:200],
                       "example": (ex.get("examples") or {}).get(p.get("name"))}
                      for p in list(shared) + list(op.get("parameters") or [])]
            resp = ((op.get("responses") or {}).get("200") or {}).get("schema") or {}
            fields = _fields(resp)
            ops.append({"path": path, "method": method.upper(), "summary": (op.get("summary") or op.get("description") or "")[:200],
                        "name": ex.get("name"), "origin_url": ex.get("origin_url"), "params": params, "response_fields": fields})
    return ops


def _fields(schema: dict, prefix: str = "", depth: int = 0) -> list[dict]:
    out = []
    if depth > 6 or not isinstance(schema, dict):
        return out
    props = schema.get("properties") or (schema.get("items") or {}).get("properties") or {}
    for k, v in props.items():
        if not isinstance(v, dict):
            continue
        name = f"{prefix}{k}"
        sub = v.get("properties") or (v.get("items") or {}).get("properties")
        if sub:
            out += _fields(v, name + ".", depth + 1)
        else:
            out.append({"name": name, "type": v.get("type"), "desc": (v.get("description") or "")[:120]})
    return out


def _text_fields(doc) -> dict:
    """구형 페이지: 기본 정보 표(th → td)와 '요청주소'·'서비스URL' 값."""
    info = {}
    for tr in doc.xpath("//table//tr"):
        th = " ".join(tr.xpath("./th//text()")).strip()
        td = " ".join(" ".join(tr.xpath("./td//text()")).split())
        if th and td and len(th) < 30:
            info[th] = td[:500]
    return info


def fetch(dataset_id: str, url: str, client: httpx.Client) -> dict:
    r = client.get(url, headers=UA, timeout=30, follow_redirects=True)
    rec = {"id": dataset_id, "url": url, "status": r.status_code, "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%S")}
    doc = lh.fromstring(r.text)
    rec["info"] = _text_fields(doc)
    sw = _swagger(r.text)
    su = re.search(r"const swaggerUrl = '([^']+)'", r.text)
    if not sw and su:  # odcloud형: swagger가 페이지 밖 URL
        try:
            sw = client.get(su.group(1), headers=UA, timeout=30).json()
            rec["swagger_url"] = su.group(1)
        except Exception as e:  # noqa: BLE001
            rec["swagger_url_error"] = repr(e)[:200]
    req = re.search(r"요청주소</strong>.*?(https?://[^\s<\"']+)", r.text, re.S)
    if req:
        rec["request_url"] = req.group(1).strip()
    if sw:
        rec["swagger"] = True
        rec["host"] = sw.get("host")
        rec["base_path"] = sw.get("basePath")
        if not rec["host"] and sw.get("servers"):  # OpenAPI 3 (odcloud)
            from urllib.parse import urlparse
            u = urlparse(sw["servers"][0]["url"])
            rec["host"], rec["base_path"], rec["schemes"] = u.netloc, u.path, [u.scheme or "https"]
        rec["schemes"] = sw.get("schemes")
        rec["operations"] = _ops(sw)
    else:
        rec["swagger"] = False
        rec["endpoints"] = sorted(set(re.findall(r"https?://apis\.data\.go\.kr/[\w/.\-]+", r.text)))
    rec["files"] = sorted(set(re.findall(r'fileDetailSn["\']?\s*[:=]\s*["\']?(\d+)', r.text)))
    rec["reference_docs"] = sorted(set(x.strip() for x in doc.xpath("//*[contains(@class,'file')]//a/text()") if x.strip()))[:20]
    return rec


def run(ids: list[tuple[str, str]], sleep: float = 0.7) -> list[dict]:
    OUT.mkdir(parents=True, exist_ok=True)
    out = []
    with httpx.Client() as c:
        for dsid, url in ids:
            try:
                rec = fetch(dsid, url, c)
            except Exception as e:  # noqa: BLE001 — 한 건 실패로 전체를 멈추지 않는다
                rec = {"id": dsid, "url": url, "error": repr(e)}
            (OUT / f"{dsid}.json").write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
            out.append(rec)
            time.sleep(sleep)
    return out


if __name__ == "__main__":
    import sys
    t = json.loads((config.KNOWLEDGE / "targets.json").read_text(encoding="utf-8"))
    rnd = sys.argv[1] if len(sys.argv) > 1 else "1"
    recs = run([(x["id"], x["url"]) for x in t if x["round"] == rnd])
    ok = sum(1 for r in recs if r.get("swagger"))
    print(f"round {rnd}: {len(recs)} specs, swagger {ok}, errors {sum(1 for r in recs if 'error' in r)}")
