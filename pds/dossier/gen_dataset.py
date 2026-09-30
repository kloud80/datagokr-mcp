"""pds gen-dataset — Phase 1 메타 + Phase 2 실측 → Dataset yaml (KNOWLEDGE-SPEC §3.1, §7-2).

원천: data/processed/{catalog,class,score}.parquet · knowledge/targets.json · probe/{specs,runs,stats,apply}/{id}.json ·
      probe/synthesis_round*.json(실측 키·날짜) · sectors/sector_tree.yaml(domain) · families/*/family.yaml(family)
재생성 규칙: 기계가 채우는 필드는 매번 새로 쓰고, 사람이 쓰는 필드(PRESERVE)와 생성기가 만들지 않은 claim은 기존 파일에서 보존한다.
"""
from __future__ import annotations

import datetime as dt
import json
import re
from functools import lru_cache

import pandas as pd
import yaml

from pds import config
from pds.schema import Dataset
from pds.schema import store

P = config.ROOT / "probe"
GENERATOR = "pds.dossier.gen_dataset"
PRESERVE = ("summary_user", "limits", "synonyms", "sla", "facets", "edges_hint", "family", "status", "cycle")
KIND = {"REST": "API", "SOAP": "API", "STD": "STD", "FILE": "FILE", "API_LINK": "EXTERNAL_API", "FILE_LINK": "EXTERNAL_FILE"}
# synth.py 실측 키 이름 → Key id
SYNTH_KEY = {"bizno": "bizno", "crno": "corp_rgst_no", "pnu": "pnu", "bjd": "bjd_cd", "sgg": "sgg_cd", "sido": "admin_area_code",
             "coord": "coord", "address": "address", "ykiho": "medical_inst_cd", "apt_complex": "apt_complex_cd", "stock": "stock_cd"}
# 판정 오탐 거르기 (consolidate §9-5): 이름이 이 모양일 때만 인정
NAME_OK = {
    "coord": re.compile(r"(lat|lon|lng|위도|경도|좌표|crd|xcnts|ycnts|geom|point|^x$|^y$|_x$|_y$|^xcode|^ycode|la$|lo$)", re.I),
    "address": re.compile(r"(addr|adres|adr$|주소|소재지|rdnm|lctn|locplc|jibun|지번|도로명)", re.I),
}
NAME_BAD = {"address": re.compile(r"(hmpg|homepage|url|mail|site|link)", re.I)}
# 외부 채널 서비스 틀 — 사이트마다 키 위치가 다르다 (consolidate §9-7)
EXTERNAL = {
    "open.neis.go.kr": {"endpoint": "https://open.neis.go.kr/hub/{op}", "security": {"scheme": "apiKey", "in": "query", "name": "KEY"},
                        "paging": {"page": "pIndex", "size": "pSize", "max_size": 1000}, "error_style": "http200_body_code"},
    "vworld.kr": {"endpoint": "https://api.vworld.kr/{op}", "security": {"scheme": "apiKey", "in": "query", "name": "key"},
                  "paging": {"page": "page", "size": "size", "max_size": 1000}, "error_style": "http200_body_code"},
    "data.seoul.go.kr": {"endpoint": "http://openapi.seoul.go.kr:8088/{{KEY}}/json/{op}/1/5/{{AREA_NM}}",
                         "security": {"scheme": "apiKey", "in": "path", "name": "KEY"}, "error_style": "http200_body_code"},
}


def _j(sub: str, dsid: str):
    f = P / sub / f"{dsid}.json"
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else None


def _v(x):
    if x is None or (isinstance(x, float) and pd.isna(x)) or x is pd.NA:
        return None
    if hasattr(x, "item"):
        x = x.item()
    return x


@lru_cache
def _frames():
    p = config.PROCESSED
    d = (pd.read_parquet(p / "catalog.parquet").merge(pd.read_parquet(p / "class.parquet"), on="id")
         .merge(pd.read_parquet(p / "score.parquet"), on="id"))
    return d.set_index("id")


@lru_cache
def _targets() -> dict:
    return {t["id"]: t for t in store.load("target")}


@lru_cache
def _synth() -> dict:
    out = {}
    for f in sorted(P.glob("synthesis_round*.json")):
        for r in json.loads(f.read_text(encoding="utf-8")):
            out[r["id"]] = r
    return out


@lru_cache
def _domains() -> dict:
    tree = yaml.safe_load((config.KNOWLEDGE / "sectors" / "sector_tree.yaml").read_text(encoding="utf-8")) or []
    return {s: d["id"] for d in tree for s in d.get("sectors", [])}


@lru_cache
def _families() -> dict:
    out = {}
    for f in (config.KNOWLEDGE / "families").glob("*/family.yaml"):
        fam = yaml.safe_load(f.read_text(encoding="utf-8"))
        for d in fam.get("datasets", []):
            out[str(d["id"])] = fam["family"]
    return out


LAW_RE = re.compile(r"([가-힣A-Za-z0-9·ㆍ\s]{2,60}?(?:법률|법|시행령|시행규칙|조례|규칙))\s*((?:제\s*\d+\s*조(?:의\s*\d+)?[\s,~·및]*)*)")


def parse_legislation(text: str | None) -> list[dict]:
    """포털 보유근거 → 법령명·조문. 법령명으로 끝나는 것만 (내부보고·절차서 같은 문구는 버린다)."""
    if not text:
        return []
    out, seen = [], set()
    for chunk in re.split(r"[\n;/]|(?<=[.)」])\s*-|^-", text):
        for m in LAW_RE.finditer(chunk.replace("「", " ").replace("」", " ")):
            name = re.sub(r"^\s*[-·\d.)]+\s*", "", m.group(1)).strip()
            name = re.sub(r"^(및|또는|등)\s+", "", name)
            if len(name) < 3 or name in seen or name.endswith(("사업법", "방법")) and len(name) < 5:
                continue
            seen.add(name)
            arts = re.findall(r"제\s*(\d+)\s*조(?:의\s*(\d+))?", m.group(2) or "")
            out.append({"law": name, "articles": [a + (f"의{b}" if b else "") for a, b in arts], "source": "portal_meta:보유근거"})
    return out


def _field_type(t: str | None) -> str:
    return {"number": "number", "code": "code", "text": "string", "date": "date"}.get(t or "", "any")


def _semantic(col: str, synth_keys: dict) -> str | None:
    for k in synth_keys.get(col, []):
        if k in NAME_OK and not NAME_OK[k].search(col):
            continue
        if k in NAME_BAD and NAME_BAD[k].search(col):
            continue
        if k in SYNTH_KEY:
            return SYNTH_KEY[k]
    return None


def _num(v):
    if isinstance(v, float) and v.is_integer():
        return int(v)
    return v


def _fields(dsid: str, spec: dict | None, synth: dict) -> list[dict]:
    desc = {}
    for o in (spec or {}).get("operations") or []:
        for f in o.get("response_fields") or []:
            desc.setdefault(str(f.get("name")).split(".")[-1].lower(), f.get("desc"))
    st = _j("stats", dsid) or {}
    kc = synth.get("key_columns") or {}
    multi = len([o for o in st.values() if isinstance(o, dict) and o]) > 1
    out = []
    for op, cols in st.items():
        if not isinstance(cols, dict):
            continue
        for name, s in cols.items():
            s = s or {}
            f = {"name": str(name), "title": desc.get(str(name).lower()), "type": _field_type(s.get("type")),
                 "semantic_type": _semantic(str(name), kc),
                 "null_rate": round(float(s["null_rate"]), 4) if isinstance(s.get("null_rate"), (int, float)) else None,
                 "sample_values": [str(k)[:80] for k in list((s.get("top") or {}).keys())[:3]],
                 "op": op if multi else None}
            if s.get("min") is not None or s.get("unique") is not None:
                f["stats"] = {k: _num(s.get(k)) for k in ("min", "p50", "max") if s.get(k) is not None} | (
                    {"unique": int(s["unique"])} if s.get("unique") is not None else {})
            out.append({k: v for k, v in f.items() if v not in (None, [], {})})
    return out


def _services(dsid: str, spec: dict | None, run: dict, apply: dict | None, m) -> list[dict]:
    ops_run = {o.get("op"): o for o in run.get("ops") or []}
    fmts = sorted({a.get("fmt") for o in run.get("ops") or [] for a in o.get("attempts") or [] if a.get("fmt")})
    approval = {"자동승인": "auto", "심의": "review"}.get((apply or {}).get("심의여부", ""), "unknown")
    traffic = {"dev": int(m.daily_traffic_dev)} if _v(m.daily_traffic_dev) and str(m.daily_traffic_dev).isdigit() else {}
    out = []
    if run.get("channel") == "external":
        site = run.get("site")
        tpl = EXTERNAL.get(site)
        if not tpl:
            return out
        for op, o in ops_run.items():
            name = op.split()[0]
            params = [{"name": k, "required": True, "example": str(v)} for k, v in
                      ((o.get("attempts") or [{}])[0].get("params") or {}).items()]
            out.append({"op": name, "name": op, "endpoint": tpl["endpoint"].format(op=name), "method": "GET",
                        "security": tpl["security"] | {"issuer": site}, "params": params, "paging": tpl.get("paging"),
                        "approval": "external", "format": fmts or ["json"], "error_style": tpl["error_style"],
                        "verified_ok": bool(o.get("ok"))})
        return [{k: v for k, v in s.items() if v not in (None, [], {})} for s in out]
    host = (spec or {}).get("host")
    scheme = "https" if "https" in ((spec or {}).get("schemes") or ["https"]) else "http"
    for o in (spec or {}).get("operations") or []:
        path = o.get("path") or ""
        if path.startswith("http"):  # Swagger 없는 명세(상세 표): path가 전체 URL
            endpoint, op = path, "/" + path.rstrip("/").rsplit("/", 1)[-1]
        elif host:
            endpoint, op = f"{scheme}://{host}{spec.get('base_path') or ''}{path}", path
        else:
            continue
        names = {p["name"] for p in o.get("params") or []}
        params = [{"name": p["name"], "required": bool(p.get("required")), "example": None if p.get("example") in (None, "-", "")
                   else str(p["example"])[:80], "desc": (p.get("desc") or None)}
                  for p in o.get("params") or [] if p["name"].lower() != "servicekey"]
        paging = {"page": "pageNo", "size": "numOfRows", "max_size": 1000} if {"pageNo", "numOfRows"} <= names else None
        r = ops_run.get(path) or ops_run.get(endpoint) or {}
        out.append({"op": op, "name": o.get("summary") or o.get("name"),
                    "endpoint": endpoint, "method": o.get("method", "GET"),
                    "security": {"scheme": "apiKey", "in": "query", "name": "serviceKey", "issuer": "data.go.kr"},
                    "params": [{k: v for k, v in p.items() if v is not None} for p in params], "paging": paging,
                    "approval": approval, "traffic": traffic, "format": fmts, "error_style": "http200_body_code",
                    "verified_ok": bool(r.get("ok")) if r else None})
    if not out:  # 명세에 오퍼레이션이 없고 실행 기록에만 원 서버 URL이 있는 경우 (기관 자체 서버 경유)
        for url, r in ops_run.items():
            if not str(url).startswith("http"):
                continue
            params = [{"name": k, "required": True, "example": str(v)[:80]}
                      for k, v in ((r.get("attempts") or [{}])[0].get("params") or {}).items() if k.lower() != "servicekey"]
            out.append({"op": "/" + url.rstrip("/").rsplit("/", 1)[-1], "endpoint": url, "method": "GET",
                        "security": {"scheme": "apiKey", "in": "query", "name": "serviceKey", "issuer": "data.go.kr"},
                        "params": params, "approval": approval, "traffic": traffic, "format": fmts,
                        "error_style": "http200_body_code", "verified_ok": bool(r.get("ok"))})
    return [{k: v for k, v in s.items() if v not in (None, [], {})} for s in out]


def _distributions(run: dict, m) -> list[dict]:
    if run.get("kind") != "file":
        return []
    return [{"title": run.get("file"), "url": run.get("url"), "format": (run.get("file") or "").rsplit(".", 1)[-1].lower() or None,
             "size": run.get("bytes")}]


def _verdict(v: str | None, tier: str, run: dict) -> str:
    """Phase 2 판정을 그대로 두되, 파일은 다운로드·셀 통계까지 됐으면 성공으로 (targets.json status=verified의 뜻)."""
    v = v or ""
    if tier == "verified" and not v.startswith("성공"):
        return "성공(파일 다운로드)" if run.get("kind") == "file" or v == "파일(별도)" else f"성공({v or '실측'})"
    return v or "미실행"


def build(dsid: str) -> dict:
    df = _frames()
    t = _targets().get(dsid)
    if t is None:
        raise KeyError(f"{dsid}: targets.json에 없음")
    m = df.loc[dsid]
    run = _j("runs", dsid) or {}
    spec = _j("specs", dsid)
    apply = _j("apply", dsid)
    syn = _synth().get(dsid, {})
    pr = t.get("probe") or {}
    field_, area = m.sector.split(" - ", 1)
    sector = f"{field_}/{area}/{m.subsector}"
    external = run.get("channel") == "external" or t["kind"] in ("API_LINK", "FILE_LINK")
    tier = "verified" if t["status"] == "verified" else "candidate"
    fields = _fields(dsid, spec, syn)
    fks, seen = [], set()
    for f in fields:
        if f.get("semantic_type") and (f["name"], f["semantic_type"]) not in seen:
            seen.add((f["name"], f["semantic_type"]))
            fks.append({"fields": [f["name"]], "reference": {"key": f["semantic_type"]}, "evidence": "measured"})
    for k in pr.get("keys") or []:  # 외부 라운드에서 사람이 판정한 키 (예: neis_school_cd)
        if k not in SYNTH_KEY and k in {x["id"] for x in store.load("key")}:
            fks.append({"fields": ["(복합)"], "reference": {"key": k}, "evidence": "measured"})
    dates = syn.get("dates") or {}
    temporal = None
    if dates:
        lo = min(v["min"] for v in dates.values())
        hi = max(v["max"] for v in dates.values())
        temporal = f"{lo} ~ {hi}"
    started = (run.get("started_at") or "")[:10] or None
    ops = run.get("ops") or []
    kw = [k.strip() for k in str(_v(m.keywords) or "").split(",") if k.strip()]
    rec = {
        "id": dsid, "tier": tier, "title": t["title"], "family": _families().get(dsid), "sector": sector,
        "domain": _domains().get(m.sector), "agency": {"id": _v(m.agency_code), "name": m.agency_name},
        "kind": KIND[t["kind"]], "channel": "external" if external else "portal", "portal_url": t["url"],
        "synonyms": list(dict.fromkeys(kw))[:10],
        "description_portal": (_v(m.description) or "").strip() or None,
        "applicable_legislation": parse_legislation(_v(m.legal_basis)),
        "legal_basis_portal": (_v(m.legal_basis) or "").strip() or None,
        "accrual_periodicity": _v(m.update_cycle),
        "team": {"dept": _v(m.dept)} if _v(m.dept) else None,
        "services": _services(dsid, spec, run, apply, m),
        "distributions": _distributions(run, m),
        "schema": {"fields": fields, "foreign_keys": fks},
        "coverage": {"spatial": _v(m.coverage), "admin_unit": _v(m.admin_unit), "temporal": temporal},
        "cycle": "event" if _v(m.cycle_override) == "event" else "default",
        "classification": {"subsector_name": t["subsector_name"], "depth": _v(m.subsector_depth), "novelty": _v(m.novelty),
                           "cross_cutting": bool(_v(m.cross_cutting)), "prelim_score": round(float(m.prelim_score), 4),
                           "rank_in_sector": int(m.rank_in_sector) if _v(m.rank_in_sector) else None, "brm": _v(m.brm),
                           "sector_rule": _v(m.sector_rule), "why": t.get("why")},
        "verification": {"verdict": _verdict(pr.get("verdict"), tier, run),
                         "probed_at": started, "channel": "external" if external else "portal",
                         "rows": pr.get("rows") if pr.get("rows") is not None else syn.get("rows"),
                         "total_count": pr.get("total_count") or syn.get("total_count") or None,
                         "ops_ok": f"{sum(bool(o.get('ok')) for o in ops)}/{len(ops)}" if ops else None,
                         "latency_ms": syn.get("ms"), "latest": pr.get("latest") or syn.get("latest"),
                         "lag_days": pr.get("lag_days") if pr.get("lag_days") is not None else syn.get("lag_days"),
                         "run": f"probe/runs/{dsid}.json" if run else None,
                         "stats": f"probe/stats/{dsid}.json" if (P / "stats" / f"{dsid}.json").exists() else None,
                         "data": f"probe/data/{dsid}/" if (P / "data" / dsid).exists() else None},
        "status": "active",
    }
    rec = _clean(rec)
    from pds.dossier.claims import make
    rec["claims"] = make(rec, t, run, apply, m)
    return rec


def _clean(x):
    if isinstance(x, dict):
        return {k: _clean(v) for k, v in x.items() if v not in (None, [], {}, "")}
    if isinstance(x, list):
        return [_clean(v) for v in x]
    return x


def write(dsid: str) -> tuple[str, list[str]]:
    rec = build(dsid)
    path = store.dataset_path(rec["sector"], dsid)
    if path.exists():  # 사람이 쓴 필드·claim 보존
        old = store.read(path) or {}
        for k in PRESERVE:
            if k in old:
                rec[k] = old[k]
        keep = [c for c in old.get("claims") or [] if not (c.get("qualifiers") or {}).get("generated_by")]
        auto = [c for c in rec.get("claims") or []]
        if keep or auto:
            rec["claims"] = keep + auto
    order = list(Dataset.model_fields)
    alias = {"schema_": "schema"}
    ordered = {alias.get(k, k): rec[alias.get(k, k)] for k in order if alias.get(k, k) in rec}
    Dataset.model_validate(ordered)
    store.dump(ordered, path, header=f"Dataset {dsid} — KNOWLEDGE-SPEC §3.1. 기계 필드는 `python -m pds gen-dataset`가 다시 쓴다.\n"
                                     f"사람이 쓰는 필드({', '.join(PRESERVE)})와 generated_by 없는 claim은 보존된다.")
    return store.rel(path), []


def write_all(status: str = "verified") -> dict:
    ok, bad = [], {}
    for dsid, t in _targets().items():
        if t["status"] != status:
            continue
        try:
            ok.append(write(dsid)[0])
        except Exception as e:  # noqa: BLE001 — 한 건 실패가 전체를 막지 않게, 목록으로 보고
            bad[dsid] = f"{type(e).__name__}: {str(e)[:300]}"
    return {"written": len(ok), "failed": bad, "at": dt.datetime.now().isoformat(timespec="seconds")}
