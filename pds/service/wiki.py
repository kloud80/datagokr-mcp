"""위키 — knowledge/datasets yaml을 사람이 찾아 읽고, 관계를 따라 옮겨 다니고, 수정을 제안하는 화면의 서버 쪽.

  탐색   search() 글자 검색(색인 BM25) + 부문·기관·등급·연결 여부 거르기 · facets() 거르기 목록
  문서   page()   데이터셋 yaml 전체 + 관계(Edge, 상대 이름 풀어서) + 같은 키를 쓰는 데이터 + 설명서 + 이 데이터에 온 제안
         key_page() 키(사업자번호·PNU·법정동 코드…) 하나를 쓰는 데이터 목록
  제안   propose() 누구나 — DB(pds_wiki_proposal, sql/008)에 pending으로 쌓는다. yaml은 건드리지 않는다.
  승인   review()  승인권자만 (.env WIKI_ADMIN_TOKENS="이름:토큰,이름:토큰" — 이름은 토큰에서 정해진다)
         승인하면 apply()가 yaml의 사람 필드(summary_user·synonyms·limits·edges_hint)나 admin_review claim으로 반영한다.
         gen-dataset은 사람 필드와 generated_by 없는 claim을 보존하므로 재생성해도 남는다.
"""
from __future__ import annotations

import datetime as dt
import hmac
import json
import os
import re
import threading
from collections import Counter, defaultdict

from pds import config
from pds.schema import store

KINDS = {"summary": "설명 고쳐 쓰기", "synonym": "검색어 추가", "limit": "주의사항 추가", "field": "필드 설명",
         "relation": "다른 데이터와의 관계", "note": "그 밖의 사실·의견"}
PAGE_EDGES = 200  # 관계가 수천 개인 허브(법정동 코드표 등)는 앞쪽만 싣고 전체 수는 따로
_LOCK = threading.Lock()
_CACHE: dict[int, dict] = {}


# ─────────── 색인 파생 (색인 객체마다 한 번)
def _derived(ix) -> dict:
    c = _CACHE.get(id(ix))
    if c:
        return c
    degree, measured = Counter(), Counter()
    for e in ix.edges:
        for s in (e["src"], e["dst"]):
            degree[s] += 1
            if e.get("verified"):
                measured[s] += 1
    by_key: dict[str, set[str]] = defaultdict(set)
    key_field: dict[tuple[str, str], list[str]] = defaultdict(list)  # (키, 데이터) → 그 키를 담은 필드 이름
    code_users: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))  # 코드표 → 데이터 → 필드
    for d in ix.datasets.values():
        for k in _keys_of(d):
            by_key[k].add(d["id"])
        sch = d.get("schema") or {}
        for f in sch.get("fields") or []:
            if f.get("semantic_type"):
                key_field[(f["semantic_type"], d["id"])].append(f["name"])
            if f.get("code_list"):
                code_users[f["code_list"]][d["id"]].append(f["name"])
        for fk in sch.get("foreign_keys") or []:
            k = (fk.get("reference") or {}).get("key")
            for name in fk.get("fields") or []:
                if k and name not in key_field[(k, d["id"])]:
                    key_field[(k, d["id"])].append(name)
    for k in ix.keys.values():  # 기관 고유 키처럼 필드 이름이 데이터마다 다른 키 (Key.fields)
        for kf in k.get("fields") or []:
            for dsid in kf.get("datasets") or []:
                if dsid in ix.datasets:
                    by_key[k["id"]].add(dsid)
                    for name in kf.get("names") or []:
                        if name not in key_field[(k["id"], dsid)]:
                            key_field[(k["id"], dsid)].append(name)
    for c in ix.codes.values():
        for u in c.get("used_by") or []:
            if u.get("dataset") in ix.datasets and u.get("field") not in code_users[c["id"]][u["dataset"]]:
                code_users[c["id"]][u["dataset"]].append(u["field"])
    cat = {}
    if ix.catalog is not None:
        cat = dict(zip(ix.catalog["id"].astype(str), ix.catalog["title"].fillna("")))
    sectors = Counter(d["sector"].split("/")[0] for d in ix.datasets.values())
    agencies = Counter(d["agency"]["name"] for d in ix.datasets.values())
    grades = Counter(((d.get("facets") or {}).get("grade") or ["핵심"])[0] for d in ix.datasets.values())
    c = {"degree": degree, "measured": measured, "by_key": by_key, "key_field": key_field, "code_users": code_users, "catalog_title": cat,
         "facets": {"counts": {"datasets": len(ix.datasets), "keys": len(ix.keys), "codes": len(ix.codes)},
                    "sectors": sectors.most_common(), "agencies": agencies.most_common(400), "grades": grades.most_common(),
                    "keys": sorted(((k, len(v)) for k, v in by_key.items()), key=lambda x: -x[1])}}
    _CACHE.clear()
    _CACHE[id(ix)] = c
    return c


def _keys_of(d: dict) -> set[str]:
    sch = d.get("schema") or {}
    ks = {f["semantic_type"] for f in sch.get("fields") or [] if f.get("semantic_type")}
    ks |= {(fk.get("reference") or {}).get("key") for fk in sch.get("foreign_keys") or []}
    return {k for k in ks if k}


def _grade(d: dict) -> str:
    return ((d.get("facets") or {}).get("grade") or ["핵심"])[0]


def _row(d: dict, x: dict) -> dict:
    return {"id": d["id"], "title": d["title"], "agency": d["agency"]["name"], "sector": d["sector"], "tier": d["tier"],
            "kind": d["kind"], "grade": _grade(d), "summary": (d.get("summary_user") or d.get("description_portal") or "")[:180],
            "edges": x["degree"].get(d["id"], 0), "measured": x["measured"].get(d["id"], 0), "keys": sorted(_keys_of(d))}


def facets(ix) -> dict:
    return _derived(ix)["facets"]


def search(ix, q: str = "", sector: str = "", agency: str = "", grade: str = "", key: str = "", linked: bool = False,
           sort: str = "relevance", page: int = 1, size: int = 30) -> dict:
    x = _derived(ix)
    q = (q or "").strip()
    if q and q in ix.datasets:  # id로 바로
        ds = [ix.datasets[q]]
    elif q:
        hits = ix.search_datasets(q, k=600)
        top = hits[0][1] if hits else 0
        ds = [d for d, s in hits if s >= 0.3 * top]  # 2-gram 하나만 겹치는 먼 결과는 뺀다
    else:
        ds = list(ix.datasets.values())
    if sector:
        ds = [d for d in ds if d["sector"].split("/")[0] == sector]
    if agency:
        ds = [d for d in ds if d["agency"]["name"] == agency]
    if grade:
        ds = [d for d in ds if _grade(d) == grade]
    if key:
        ids = x["by_key"].get(key, set())
        ds = [d for d in ds if d["id"] in ids]
    if linked:
        ds = [d for d in ds if x["measured"].get(d["id"])]
    if sort == "edges" or (sort == "relevance" and not q):
        ds.sort(key=lambda d: (-x["measured"].get(d["id"], 0), -x["degree"].get(d["id"], 0), d["title"]))
    elif sort == "title":
        ds.sort(key=lambda d: d["title"])
    size = max(10, min(size, 100))
    page = max(1, page)
    return {"total": len(ds), "page": page, "size": size, "rows": [_row(d, x) for d in ds[(page - 1) * size: page * size]]}


def _title(ix, x: dict, dsid: str) -> tuple[str | None, bool]:
    d = ix.datasets.get(dsid)
    if d:
        return d["title"], True
    return x["catalog_title"].get(dsid) or None, False


def page(ix, dsid: str) -> dict | None:
    d = ix.datasets.get(dsid)
    if not d:
        return None
    x = _derived(ix)
    rels = []
    for e in ix.edges:
        if dsid not in (e["src"], e["dst"]):
            continue
        other = e["dst"] if e["src"] == dsid else e["src"]
        t, known = _title(ix, x, other)
        od = ix.datasets.get(other) or {}
        on = e.get("on") or {}
        rels.append({"edge": e["id"], "rel": e["rel"], "dir": "out" if e["src"] == dsid else "in", "other": other, "other_title": t,
                     "other_known": known, "other_sector": od.get("sector"), "other_agency": (od.get("agency") or {}).get("name"),
                     "left": on.get("left"), "right": on.get("right"), "transform": on.get("transform"), "via_mapping": on.get("via_mapping"),
                     "relationship": e.get("relationship"), "confidence": e.get("confidence"), "source": e.get("source"),
                     "note": e.get("note"), "match_rate": (e.get("verified") or {}).get("match_rate"),
                     "measured_at": (e.get("verified") or {}).get("at")})
    rank = {"joinable": 0, "lookup": 1, "related_to": 2}
    rels.sort(key=lambda r: (rank.get(r["rel"], 9), r["match_rate"] is None, -(r["match_rate"] or 0), -(r["confidence"] or 0)))
    totals = dict(Counter(r["rel"] for r in rels))
    shown = [r for rel in rank for r in [r for r in rels if r["rel"] == rel][:PAGE_EDGES]]
    keys = []
    for k in sorted(_keys_of(d)):
        meta = ix.keys.get(k) or {}
        keys.append({"id": k, "name": meta.get("name") or k, "datasets": len(x["by_key"].get(k, ()))})
    family = []
    if d.get("family"):
        family = [{"id": o["id"], "title": o["title"], "agency": o["agency"]["name"]} for o in ix.datasets.values()
                  if o.get("family") == d["family"] and o["id"] != dsid][:50]
    md = config.ROOT / "docs" / "dossiers" / f"{d.get('family') or dsid}.md"
    return {"dataset": d, "relations": shown, "relation_totals": totals, "keys": keys, "family": family,
            "dossier_md": md.read_text(encoding="utf-8") if md.exists() else None,
            "file": str(store.dataset_path(d["sector"], dsid).relative_to(config.ROOT)).replace("\\", "/")}


def _ds_ref(ix, x: dict, dsid: str) -> dict:
    t, known = _title(ix, x, dsid)
    d = ix.datasets.get(dsid) or {}
    return {"id": dsid, "title": t, "known": known, "agency": (d.get("agency") or {}).get("name")}


def keys_list(ix, q: str = "") -> list[dict]:
    """키 전체 (knowledge/keys) — 쓰는 데이터 수 · 원장 · 매핑 · 코드표."""
    x = _derived(ix)
    maps = Counter(s["key"] for m in ix.mappings.values() for s in (m["left"], m["right"]))
    codes = Counter(c.get("key") for c in ix.codes.values() if c.get("key"))
    ql = (q or "").strip().lower()
    out = []
    for k in ix.keys.values():
        if ql and ql not in " ".join(str(v) for v in (k["id"], k.get("name"), k.get("notes"), k.get("issuer"), " ".join(k.get("shape_names") or []))).lower():
            continue
        out.append({"id": k["id"], "name": k.get("name"), "type": k.get("type"), "scope": k.get("scope"), "issuer": k.get("issuer"),
                    "agency": k.get("agency"), "datasets": len(x["by_key"].get(k["id"], ())), "masters": len(k.get("master_datasets") or []),
                    "mappings": maps.get(k["id"], 0), "codes": codes.get(k["id"], 0)})
    out.sort(key=lambda r: (-r["datasets"], r["id"]))
    return out


def key_page(ix, key: str, page_no: int = 1, size: int = 50) -> dict | None:
    x = _derived(ix)
    ids = x["by_key"].get(key)
    meta = ix.keys.get(key)
    if not ids and not meta:
        return None
    meta = meta or {"id": key, "name": key}
    ds = sorted((ix.datasets[i] for i in ids or ()), key=lambda d: (-x["measured"].get(d["id"], 0), d["title"]))
    rows = [{**_row(d, x), "fields": x["key_field"].get((key, d["id"]), [])} for d in ds[(page_no - 1) * size: page_no * size]]
    mappings = [{"id": m["id"], "left": m["left"], "right": m["right"], "method": m.get("method"), "rows": m.get("rows"),
                 "match_rate": m.get("match_rate"), "notes": m.get("notes")}
                for m in ix.mappings.values() if key in (m["left"]["key"], m["right"]["key"])]
    related = [{**r, "name": (ix.keys.get(r["key"]) or {}).get("name")} for r in meta.get("related_keys") or []]
    related += [{"key": k["id"], "relation": f"{r['relation']} (상대 쪽)", "note": r.get("note"), "name": k.get("name")}
                for k in ix.keys.values() for r in k.get("related_keys") or [] if r["key"] == key]
    return {"key": {k: v for k, v in meta.items() if k != "fields"}, "total": len(ds), "page": page_no, "size": size, "rows": rows,
            "masters": [_ds_ref(ix, x, i) for i in meta.get("master_datasets") or []],
            "composed_of": [{"key": k, "name": (ix.keys.get(k) or {}).get("name")} for k in meta.get("composed_of") or []],
            "related": related, "mappings": mappings,
            "codes": [{"id": c["id"], "name": c["name"], "rows": c["rows"]} for c in ix.codes.values() if c.get("key") == key],
            "file": f"knowledge/keys/{key}.yaml"}


COMPLETENESS = {"complete": "공식 원천 전체", "master_scan": "전수 원장에서 쓰이는 값 전부", "observed": "표본에서 본 값만"}


def codes_list(ix, q: str = "") -> list[dict]:
    x = _derived(ix)
    ql = (q or "").strip().lower()
    out = []
    for c in ix.codes.values():
        if ql and ql not in " ".join(str(v) for v in (c["id"], c["name"], c.get("notes"), " ".join(c.get("aliases") or []))).lower():
            continue
        out.append({"id": c["id"], "name": c["name"], "key": c.get("key"), "completeness": c["completeness"], "rows": c["rows"],
                    "aliases": c.get("aliases") or [], "datasets": len(x["code_users"].get(c["id"], {}))})
    out.sort(key=lambda r: (-r["datasets"], r["id"]))
    return out


def code_page(ix, cid: str, q: str | None = None, limit: int = 300) -> dict | None:
    c = ix.codes.get(cid)
    if not c:
        return None
    x = _derived(ix)
    users = x["code_users"].get(cid, {})
    used = sorted(({**_ds_ref(ix, x, i), "fields": f} for i, f in users.items()), key=lambda r: r["title"] or "")
    vals = ix.code_values(cid, q, limit)
    return {"code": {**c, "completeness_label": COMPLETENESS.get(c["completeness"], c["completeness"]),
                     "key_name": (ix.keys.get(c.get("key") or "") or {}).get("name")},
            "used_by": used, "values": vals, "values_shown": len(vals), "q": q,
            "file": f"knowledge/codes/{cid}.yaml"}


# ─────────── 제안·승인 (Postgres pds_wiki_proposal)
COLS = ["id", "dataset_id", "kind", "target", "current_value", "proposed_value", "reason", "author", "status", "reviewer",
        "review_note", "reviewed_at", "applied", "created_at"]


def _conn():
    from pds import db
    c = db.connect()
    db.migrate(c)
    return c


def _rec(row) -> dict:
    r = dict(zip(COLS, row))
    for k in ("reviewed_at", "created_at"):
        if r[k]:
            r[k] = r[k].isoformat(timespec="seconds")
    return r


def proposals(dataset_id: str | None = None, status: str | None = None, limit: int = 200) -> list[dict]:
    where, args = [], []
    if dataset_id:
        where.append("dataset_id = %s")
        args.append(dataset_id)
    if status:
        where.append("status = %s")
        args.append(status)
    q = f"select {', '.join(COLS)} from pds_wiki_proposal {'where ' + ' and '.join(where) if where else ''} order by created_at desc limit %s"
    with _conn() as c:
        return [_rec(r) for r in c.execute(q, (*args, limit)).fetchall()]


def counts() -> dict:
    with _conn() as c:
        return dict(c.execute("select status, count(*) from pds_wiki_proposal group by status").fetchall())


def propose(ix, dataset_id: str, kind: str, proposed: str, target: str | None, reason: str | None, author: str | None,
            client_hash: str | None) -> dict:
    d = ix.datasets.get(dataset_id)
    if not d:
        raise ValueError("지식 체계에 없는 데이터")
    if kind not in KINDS:
        raise ValueError(f"kind는 {', '.join(KINDS)} 중 하나")
    proposed = (proposed or "").strip()
    if not proposed:
        raise ValueError("제안 내용이 비었다")
    target = (target or "").strip() or None
    if kind == "field":
        names = {f["name"] for f in (d.get("schema") or {}).get("fields") or []}
        if target not in names:
            raise ValueError("필드 설명은 이 데이터의 필드 이름을 골라야 한다")
    if kind == "relation":
        if not target or not re.fullmatch(r"[\w.:-]+", target):
            raise ValueError("관계 제안은 상대 데이터 id가 필요하다")
        if target == dataset_id:
            raise ValueError("자기 자신과의 관계는 제안할 수 없다")
    current = {"summary": d.get("summary_user"), "limit": d.get("limits")}.get(kind)
    with _conn() as c:
        row = c.execute(
            f"insert into pds_wiki_proposal (dataset_id, kind, target, current_value, proposed_value, reason, author, client_hash) "
            f"values (%s, %s, %s, %s, %s, %s, %s, %s) returning {', '.join(COLS)}",
            (dataset_id, kind, target, current, proposed[:4000], (reason or "").strip()[:2000] or None,
             (author or "").strip()[:60] or None, client_hash)).fetchone()
        c.commit()
    return _rec(row)


def reviewer_of(token: str | None) -> str | None:
    """WIKI_ADMIN_TOKENS="이름:토큰,이름:토큰" — 토큰이 맞으면 그 이름. 승인자 이름은 사용자가 고를 수 없다."""
    if not token:
        return None
    for pair in (os.environ.get("WIKI_ADMIN_TOKENS") or "").split(","):
        name, _, tok = pair.strip().partition(":")
        if name and tok and hmac.compare_digest(tok.strip(), token.strip()):
            return name.strip()
    return None


def review(ix, pid: int, decision: str, reviewer: str, note: str | None) -> dict:
    if decision not in ("approve", "reject"):
        raise ValueError("decision은 approve 또는 reject")
    with _conn() as c:
        row = c.execute(f"select {', '.join(COLS)} from pds_wiki_proposal where id = %s for update", (pid,)).fetchone()
        if not row:
            raise LookupError("없는 제안")
        p = _rec(row)
        if p["status"] != "pending":
            raise ValueError(f"이미 {p['status']} 처리된 제안")
        applied = apply(ix, p, reviewer, note) if decision == "approve" else None
        row = c.execute(
            f"update pds_wiki_proposal set status = %s, reviewer = %s, review_note = %s, reviewed_at = now(), applied = %s "
            f"where id = %s returning {', '.join(COLS)}",
            ("approved" if decision == "approve" else "rejected", reviewer, (note or "").strip()[:2000] or None,
             json.dumps(applied, ensure_ascii=False) if applied else None, pid)).fetchone()
        c.commit()
    return _rec(row)


def apply(ix, p: dict, reviewer: str, note: str | None = None) -> dict:
    """승인된 제안을 데이터셋 yaml에 반영 — 사람 필드 또는 admin_review claim. 스키마 검사를 통과해야 쓴다."""
    from pds.schema import Dataset
    dsid = p["dataset_id"]
    d = ix.datasets.get(dsid)
    if not d:
        raise LookupError("지식 체계에 없는 데이터")
    path = store.dataset_path(d["sector"], dsid)
    today = dt.date.today().isoformat()
    ev = {"type": "admin_review", "source": f"wiki:proposal/{p['id']}", "by": reviewer, "at": today,
          "detail": "; ".join(x for x in [f"제안 {p.get('author') or '익명'}", p.get("reason"), note and f"승인 의견: {note}"] if x)[:500]}
    with _LOCK:
        y = store._yaml()
        text = path.read_text(encoding="utf-8")
        header = "".join(ln + "\n" for ln in text.splitlines() if ln.startswith("#"))
        data = y.load(text)
        out = {"file": str(path.relative_to(config.ROOT)).replace("\\", "/")}
        v = p["proposed_value"].strip()
        k = p["kind"]
        if k == "summary":
            data["summary_user"] = v
            data["review"] = {**(data.get("review") or {}), "summary": "approved", "by": reviewer, "at": today, "source": ev["source"]}
            out["field"] = "summary_user"
        elif k == "synonym":
            words = [w.strip() for w in re.split(r"[,\n]", v) if w.strip()]
            syn = list(data.get("synonyms") or [])
            for w in words:
                if w not in syn:
                    syn.append(w)
            data["synonyms"] = syn
            out["field"] = "synonyms"
        elif k == "limit":
            data["limits"] = (str(data["limits"]).rstrip() + "\n" + v) if data.get("limits") else v
            out["field"] = "limits"
        else:
            if k == "relation":
                hints = list(data.get("edges_hint") or [])
                if p["target"] not in hints:
                    hints.append(p["target"])
                data["edges_hint"] = hints
            prefix = {"field": f"필드 '{p['target']}': ", "relation": f"[[{p['target']}]]와의 관계: "}.get(k, "")
            claims = list(data.get("claims") or [])
            nums = [int(m.group(1)) for c in claims if (m := re.search(r"-(\d+)$", c.get("id") or ""))]
            cid = f"c-{dsid}-{max(nums, default=0) + 1:02d}"
            q = {"source": "wiki", "proposal": p["id"]}
            if k in ("field", "relation"):
                q[k] = p["target"]
            claims.append({"id": cid, "kind": "admin_note", "value": prefix + v, "evidence": [ev], "qualifiers": q, "rank": "normal"})
            data["claims"] = claims
            out["claim"] = cid
            if k == "relation":
                out["field"] = "edges_hint"
        Dataset.model_validate(json.loads(json.dumps(data, default=str)))
        store.dump(data, path)
        ix.datasets[dsid] = store.read(path)  # 화면이 바로 새 값을 보게 (검색 색인은 다음 재시작 때)
    return out
