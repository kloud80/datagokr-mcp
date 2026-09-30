"""지식 그래프 컴파일러 — L1 카탈로그 + L2 지식 원본(knowledge/) → L3 노드·엣지·문서·청크.

규약: knowledge/ARCHITECTURE.md. 결정적(같은 입력 → 같은 출력)이며 원본을 고치지 않는다.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import pandas as pd
import yaml

from pds import config

KG_DIR = config.PROCESSED / "kg"
CHUNK_SIZE = 800
CHUNK_OVERLAP = 100
DESC_MAX = 1500


def _sha1(s: str) -> str:
    return hashlib.sha1(s.encode("utf-8")).hexdigest()


def _yaml(path: Path):
    return yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else None


def _rel(path: Path) -> str:
    return path.relative_to(config.ROOT).as_posix()


def _sector_node(sector: str) -> str:
    f, a = (sector.split(" - ", 1) + [""])[:2]
    return f"sector:{f}/{a}"


def _slug(title: str) -> str:
    s = re.sub(r"[^\w가-힣]+", "-", title.strip().lower()).strip("-")
    return s or "section"


class Graph:
    def __init__(self):
        self.nodes: dict[str, dict] = {}
        self.edges: list[dict] = []
        self.docs: dict[str, dict] = {}

    def node(self, node_id: str, name: str | None = None, source: str | None = None, **props):
        typ, key = node_id.split(":", 1)
        n = self.nodes.setdefault(node_id, {"node_id": node_id, "type": typ, "key": key, "name": name,
                                             "props": {}, "source": source})
        if name and not n["name"]:
            n["name"] = name
        n["props"].update({k: v for k, v in props.items() if v is not None})
        return node_id

    def edge(self, src: str, dst: str, typ: str, status: str, source: str | None = None,
             evidence: list | None = None, **props):
        self.edges.append({"src": src, "dst": dst, "type": typ, "status": status, "source": source,
                           "evidence": evidence or [], "props": {k: v for k, v in props.items() if v is not None}})

    def doc(self, node_id: str, kind: str, title: str, body: str, source: str | None, section: str | None = None):
        if not body or not body.strip():
            return
        doc_id = f"{node_id}#{section or _slug(title)}"
        base, n = doc_id, 2
        while doc_id in self.docs:
            doc_id, n = f"{base}-{n}", n + 1
        self.docs[doc_id] = {"doc_id": doc_id, "node_id": node_id, "kind": kind, "title": title,
                             "body": body.strip(), "source": source, "hash": _sha1(body.strip())}


# ---------------------------------------------------------------- L1: 카탈로그

def _catalog() -> pd.DataFrame:
    p = config.PROCESSED
    return (pd.read_parquet(p / "catalog.parquet")
            .merge(pd.read_parquet(p / "class.parquet"), on="id")
            .merge(pd.read_parquet(p / "score.parquet"), on="id"))


def _val(v):
    if v is None or (isinstance(v, float) and pd.isna(v)) or v is pd.NA:
        return None
    if hasattr(v, "item"):
        v = v.item()
    return v if not isinstance(v, float) or v == v else None


def add_catalog(g: Graph, df: pd.DataFrame, keys: list[dict]) -> None:
    shape_to_key = {n: k["id"] for k in keys for n in k.get("shape_names", [])}
    for r in df.itertuples(index=False):
        ds = g.node(f"dataset:{r.id}", r.title, "catalog",
                    kind=r.api_kind_label, list_type=r.list_type, channel="external" if r.api_kind_label in ("API_LINK", "FILE_LINK") else "portal",
                    admin_unit=r.admin_unit, prelim_score=_val(r.prelim_score), rank_overall=_val(r.rank_overall),
                    rank_in_sector=_val(r.rank_in_sector), usage=_val(r.usage_count), national_key=bool(r.national_key),
                    granularity=_val(r.s_granularity), linkable=_val(r.s_linkable), coverage=_val(r.s_coverage),
                    excluded=isinstance(r.excluded_by, str), url=r.url)
        ag = g.node(f"agency:{r.agency_code}", r.agency_name, "catalog", tier=r.agency_tier)
        g.edge(ds, ag, "provided_by", "computed", "catalog")
        sec = g.node(_sector_node(r.sector), r.sector, "catalog", field=r.sector_field, area=r.sector_area)
        g.edge(ds, sec, "in_sector", "computed", "catalog", brm=r.brm, rank_in_sector=_val(r.rank_in_sector))
        if isinstance(r.subsector, str):
            f, a = _sector_node(r.sector).split(":", 1)[1].split("/", 1)
            sub = g.node(f"subsector:{f}/{a}/{r.subsector}", r.subsector_name, "knowledge/sectors/subsectors.yaml")
            g.edge(ds, sub, "in_subsector", "decided", "knowledge/sectors/subsectors.yaml", depth=r.subsector_depth)
        if isinstance(r.excluded_by, str):
            g.edge(ds, f"decision:{r.excluded_by}", "excluded_by", "decided", "knowledge/sectors/exclusions.yaml")
        if isinstance(r.sector_rule, str):
            g.edge(ds, f"decision:{r.sector_rule}", "remapped_by", "decided", "knowledge/sectors/sector_map.yaml",
                   from_brm=r.brm)
        # 연계 키 (shape 판정). 외부 링크의 대입값은 실측이 아니므로 엣지를 만들지 않는다
        imputed = isinstance(r.imputed, str) and "linkable" in r.imputed
        if isinstance(r.linkable_ev, str) and r.linkable_ev != "none" and not imputed:
            for name in r.linkable_ev.split(","):
                k = shape_to_key.get(name)
                if k:
                    g.edge(ds, f"key:{k}", "has_key", "computed", "pds/rank/shape.py", evidence=["meta:output_cols"])
        # 데이터 설명 (벡터화 대상). 제외 데이터는 설명을 넣지 않는다
        if not isinstance(r.excluded_by, str):
            body = f"{r.title}\n{(r.description or '')[:DESC_MAX]}"
            if isinstance(r.output_cols, str):
                body += f"\n출력 항목: {r.output_cols[:500]}"
            g.doc(ds, "dataset_desc", r.title, body, "catalog", section="desc")
    for sec in {n for n in g.nodes if n.startswith("sector:")}:
        g.edge(sec, g.node(f"field:{sec.split(':', 1)[1].split('/')[0]}"), "in_field", "computed", "catalog")


SERIES_RE = re.compile(r"^(?P<base>.+?)[_\s(]*(?P<year>(19|20)\d{2})(년|년도)?[)]?$")


def add_series(g: Graph, df: pd.DataFrame) -> None:
    """제목 끝의 연도만 다른 같은 기관 데이터 → series 노드 + part_of_series(연도). 포털이 연도마다 새 목록키로 등록하는 관행 대응.
    같은 스키마의 연도 분할이므로 관계는 continues(대체가 아니라 이어짐)."""
    rows = []
    for r in df[["id", "title", "agency_code", "agency_name"]].itertuples(index=False):
        m = SERIES_RE.match(r.title.strip())
        if m:
            rows.append((r.agency_code, m.group("base").strip(" _-"), int(m.group("year")), r.id, r.agency_name))
    s = pd.DataFrame(rows, columns=["agency", "base", "year", "id", "agency_name"])
    for (agency, base), grp in s.groupby(["agency", "base"]):
        if len(grp) < 2:
            continue
        grp = grp.sort_values("year")
        sid = g.node(f"series:{agency}/{_slug(base)}", base, "catalog", years=grp["year"].tolist(),
                     latest=f"dataset:{grp.iloc[-1]['id']}", agency=grp.iloc[0]["agency_name"])
        prev = None
        for r in grp.itertuples():
            ds = f"dataset:{r.id}"
            g.edge(ds, sid, "part_of_series", "computed", "catalog", year=int(r.year))
            if prev:
                g.edge(prev, ds, "continues", "computed", "catalog")
            prev = ds


# ---------------------------------------------------------------- L2: 지식 원본

def add_keys(g: Graph, keys: list[dict]) -> None:
    """knowledge/keys/{id}.yaml (KNOWLEDGE-SPEC §3.2). related_keys의 parent는 key_parent, 나머지는 key_related 엣지."""
    for k in keys:
        src = f"knowledge/keys/{k['id']}.yaml"
        kid = g.node(f"key:{k['id']}", k["name"], src, format=k.get("format"), pattern=k.get("pattern"),
                     scope=k.get("scope"), key_type=k.get("type"))
        g.doc(kid, "key_note", k["name"], f"{k['name']} ({k['id']}) 형식: {k.get('format')}\n{k.get('notes', '')}", src,
              section="note")
        for m in k.get("master_datasets", []):
            g.edge(f"dataset:{m}", kid, "defines_key", "decided", src)
        for r in k.get("related_keys", []):
            if r["relation"] == "parent":
                g.edge(kid, f"key:{r['key']}", "key_parent", "decided", src)
            elif r["relation"] != "child":  # child는 상대 파일의 parent로 이미 들어간다
                g.edge(kid, f"key:{r['key']}", "key_related", "decided", src, relation=r["relation"], note=r.get("note"))


def add_key_issuers(g: Graph, df: pd.DataFrame) -> None:
    """외부 키 발급처 → issuer 노드, dataset --key_issued_by--> issuer. 계정 값은 다루지 않고 .env 변수 이름만 속성으로."""
    from pds.rank.exclude import _selector
    path = config.KNOWLEDGE / "key_issuers.yaml"
    issuers = _yaml(path) or []
    base = pd.DataFrame({"id": df["id"], "agency_name": df["agency_name"], "title": df["title"],
                         "kind": df["api_kind_label"]})
    done = pd.Series(False, index=base.index)
    for iss in issuers:
        nid = g.node(f"issuer:{iss['id']}", iss["name"], _rel(path), site=iss.get("site"), key_param=iss.get("key_param"),
                     env_vars=sorted((iss.get("env") or {}).values()))
        g.doc(nid, "issuer_note", iss["name"], f"{iss['name']} ({iss.get('site')}) 키 파라미터 {iss.get('key_param')}\n"
              f"발급 절차: {iss.get('issuance', '')}", _rel(path), section="issuance")
        hit = _selector(base, iss, "match", "match_any", False) & ~done
        for dsid in base.loc[hit, "id"]:
            g.edge(f"dataset:{dsid}", nid, "key_issued_by", "decided", _rel(path))
        done |= hit


def add_decisions(g: Graph) -> None:
    for fname in ("exclusions.yaml", "sector_map.yaml"):
        path = config.KNOWLEDGE / "sectors" / fname
        for r in _yaml(path) or []:
            did = g.node(f"decision:{r['id']}", r["id"], _rel(path), kind=fname.split(".")[0],
                         decided_at=str(r.get("decided_at")), decided_by=r.get("decided_by"),
                         set_sector=r.get("set_sector"))
            g.doc(did, "decision_reason", r["id"], str(r.get("reason", "")), _rel(path), section="reason")
            if r.get("set_sector"):
                g.edge(did, _sector_node(r["set_sector"]), "decides_for", "decided", _rel(path))


def add_subsectors(g: Graph) -> None:
    path = config.KNOWLEDGE / "sectors" / "subsectors.yaml"
    for sdef in _yaml(path) or []:
        sec = _sector_node(sdef["sector"])
        fa = sec.split(":", 1)[1]
        g.node(sec, sdef["sector"], _rel(path), doc=sdef.get("doc"))
        if sdef.get("note"):
            g.doc(sec, "sector_note", sdef["sector"], sdef["note"], _rel(path), section="note")
        for sub in sdef["subsectors"] + ([sdef["default"]] if sdef.get("default") else []):
            sid = g.node(f"subsector:{fa}/{sub['slug']}", sub["name"], _rel(path), depth=sub.get("depth"),
                         cycle=sub.get("cycle"), cross_cutting=sub.get("cross_cutting"))
            g.edge(sid, sec, "subsector_of", "decided", _rel(path), depth=sub.get("depth"), cycle=sub.get("cycle"),
                   cross_cutting=sub.get("cross_cutting"))


def add_gaps(g: Graph) -> None:
    """knowledge/gaps.yaml (KNOWLEDGE-SPEC §9-1) → gap 노드 + gap_of 엣지."""
    from pds.schema import store
    src = store.rel(store.PATHS["gap"])
    for gap in store.load("gap"):
        gid = g.node(f"gap:{gap['id']}", gap["name"], src, status=gap.get("status"),
                     external_candidate=gap.get("external_candidate"), resolved_by=gap.get("resolved_by"))
        g.edge(gid, _sector_node(gap["sector"]), "gap_of", "decided", src, note=gap.get("reason"))
        g.doc(gid, "gap_note", gap["name"], "\n".join(x for x in (gap.get("question"), gap.get("reason"),
                                                                    gap.get("external_candidate")) if x), src, section="note")


def add_sector_tree(g: Graph) -> None:
    """knowledge/sectors/sector_tree.yaml → 부문 위의 법 체계 계층(domain). parent가 없으면 정책분야(field) 바로 아래."""
    path = config.KNOWLEDGE / "sectors" / "sector_tree.yaml"
    for d in _yaml(path) or []:
        nid = g.node(f"domain:{d['id']}", d["name"], _rel(path), law=d.get("law"))
        g.doc(nid, "domain_note", d["name"], "\n".join(x for x in (d.get("law"), d.get("note")) if x), _rel(path),
              section="note")
        parent = f"domain:{d['parent']}" if d.get("parent") else g.node(f"field:{d['id'].split('/')[0]}")
        g.edge(nid, parent, "domain_of", "decided", _rel(path))
        for sec in d.get("sectors", []):
            g.edge(g.node(_sector_node(sec), sec, _rel(path)), nid, "in_domain", "decided", _rel(path), law=d.get("law"))
        for sec in d.get("related", []):
            g.edge(nid, g.node(_sector_node(sec), sec, _rel(path)), "related_sector", "decided", _rel(path))


def add_contexts(g: Graph) -> None:
    """knowledge/contexts/{id}.yaml → 부처가 달라 부문은 다르지만 같은 맥락인 데이터 묶음. context 노드 + in_context 엣지(차원별).
    멤버는 세부 부문(sector+subsector) 또는 데이터셋(dataset)."""
    from pds.schema import store
    for c, path in store.iter_raw("context"):
        src = _rel(path)
        nid = g.node(f"context:{c['id']}", c["name"], src, dimension=c["dimension"], key=c.get("key"),
                     question=c.get("question"), recipe=c.get("recipe"))
        g.doc(nid, "context_note", c["name"],
              "\n".join(x for x in (c.get("question"), c.get("note")) if x) or c["name"], src, section="note")
        for m in c["members"]:
            if m.get("dataset"):
                member = f"dataset:{m['dataset']}"
            else:
                sec = _sector_node(m["sector"])
                member = f"subsector:{sec.split(':', 1)[1]}/{m['subsector']}" if m.get("subsector") else sec
            g.edge(g.node(member), nid, "in_context", "decided", src, dimension=c["dimension"], role=m.get("role"),
                   key=c.get("key"))
        if c.get("key"):
            g.edge(nid, f"key:{c['key']}", "context_key", "decided", src)


def add_sector_docs(g: Graph) -> None:
    """knowledge/sectors/<분야>/<영역>.md → 섹션(##)별 문서. frontmatter의 sector로 노드를 정한다."""
    for path in sorted((config.KNOWLEDGE / "sectors").rglob("*.md")):
        if path.name.startswith("_"):
            continue
        text = path.read_text(encoding="utf-8")
        m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
        if not m:
            continue
        meta = yaml.safe_load(m.group(1))
        if not meta.get("sector"):  # contexts.md 같은 부문 밖 생성 문서 (원본 yaml이 따로 컴파일된다)
            continue
        node = g.node(_sector_node(meta["sector"]), meta["sector"], _rel(path), slug=meta.get("slug"),
                      doc=_rel(path))
        _split_md(g, node, "sector_doc", text[m.end():], _rel(path))


def _split_md(g: Graph, node: str, kind: str, text: str, source: str) -> None:
    parts = re.split(r"^(##\s+.+)$", text, flags=re.M)
    head = parts[0].strip()
    if head:
        g.doc(node, kind, "개요", head, source, section="intro")
    for i in range(1, len(parts), 2):
        title = parts[i].lstrip("#").strip()
        g.doc(node, kind, title, f"{title}\n{parts[i + 1]}", source, section=_slug(title))


def add_families(g: Graph) -> None:
    fam_root = config.KNOWLEDGE / "families"
    for fdir in sorted(p for p in fam_root.iterdir() if (p / "family.yaml").exists()):
        fam = _yaml(fdir / "family.yaml")
        src = _rel(fdir / "family.yaml")
        slug = fam["family"]
        fid = g.node(f"family:{slug}", fam["title"], src, version=fam.get("version"), updated=str(fam.get("updated")))
        g.doc(fid, "family_note", "요약", fam.get("summary", ""), src, section="summary")
        if (fdir / "family.md").exists():
            _split_md(g, fid, "family_doc", (fdir / "family.md").read_text(encoding="utf-8"), _rel(fdir / "family.md"))
        for e in fam["entities"]:
            g.node(f"entity:{slug}/{e['id']}", e["name"], src, stage=e.get("stage"), note=e.get("note"))
        for k in fam["keys"]:
            kid = g.node(f"fkey:{slug}/{k['id']}", k["name"], src, format=k.get("format"))
            if k.get("global_key"):
                g.edge(kid, f"key:{k['global_key']}", "same_as", "decided", src)
            for a in k["aliases"]:
                g.edge(f"dataset:{a['dataset']}", kid, "has_key", a.get("status", "documented"), src,
                       field=a["field"], io=a.get("io"), transform=a.get("transform"))
        for d in fam["datasets"]:
            ds = f"dataset:{d['id']}"
            g.edge(ds, fid, "member_of", "documented", src, role=d["role"], short=d["short"])
            ents = d.get("entity") or []
            for en in ([ents] if isinstance(ents, str) else ents):
                g.edge(ds, f"entity:{slug}/{en}", "provides", "documented", src)
            text = "\n".join(x for x in (d.get("does"), d.get("use_when"), "; ".join(d.get("caveats", []))) if x)
            g.doc(ds, "family_role", f"{fam['title']} — {d['short']}", f"[{d['role']}] {text}", src, section=f"family-{slug}")

        def ref(x: str, typ: str) -> str:
            if typ == "lifecycle":
                return f"entity:{slug}/{x}"
            if typ == "hierarchy":
                return f"fkey:{slug}/{x}"
            if x.startswith("*."):
                return f"fkey:{slug}/{x[2:]}"
            return f"dataset:{x}"

        for e in fam["edges"]:
            props = {k: v for k, v in e.items() if k not in ("type", "from", "to", "status", "evidence")}
            for to in (e["to"] if isinstance(e["to"], list) else [e["to"]]):
                g.edge(ref(e["from"], e["type"]), ref(to, e["type"]), e["type"], e["status"], src,
                       evidence=e["evidence"], **props)
        for r in fam.get("recipes", []):
            rid = g.node(f"recipe:{slug}/{r['id']}", r["goal"], src, status=r["status"], steps=r["steps"])
            g.doc(rid, "recipe", r["goal"], r["goal"] + "\n" + json.dumps(r["steps"], ensure_ascii=False), src,
                  section="steps")
            for i, st in enumerate(r["steps"], 1):
                if isinstance(st, dict) and st.get("dataset"):
                    g.edge(rid, f"dataset:{st['dataset']}", "uses", r["status"], src, step=i)


# ---------------------------------------------------------------- 청크·출력

def chunk(text: str) -> list[str]:
    if len(text) <= CHUNK_SIZE:
        return [text]
    out, start = [], 0
    while start < len(text):
        end = min(len(text), start + CHUNK_SIZE)
        cut = text.rfind("\n", start + CHUNK_SIZE // 2, end)
        end = cut if cut > start and end < len(text) else end
        out.append(text[start:end].strip())
        if end >= len(text):
            break
        start = max(end - CHUNK_OVERLAP, start + 1)
    return [c for c in out if c]


def build() -> dict[str, pd.DataFrame]:
    from pds.schema import store
    keys = store.load("key")
    g = Graph()
    df = _catalog()
    add_keys(g, keys)
    add_decisions(g)
    add_subsectors(g)
    add_gaps(g)
    add_sector_tree(g)
    add_contexts(g)
    add_catalog(g, df, keys)
    add_key_issuers(g, df)
    add_series(g, df)
    add_sector_docs(g)
    add_families(g)

    # 엣지가 가리키는데 노드가 없는 것(예: 패밀리가 참조한 데이터셋이 카탈로그에 없음)은 자리표시 노드로
    for e in g.edges:
        for nid in (e["src"], e["dst"]):
            if nid not in g.nodes:
                g.node(nid, None, "placeholder", placeholder=True)

    nodes = pd.DataFrame(g.nodes.values())
    edges = pd.DataFrame(g.edges)
    docs = pd.DataFrame(g.docs.values())
    chunks = pd.DataFrame([{"chunk_id": f"{d['doc_id']}~{i}", "doc_id": d["doc_id"], "seq": i, "text": c,
                            "hash": _sha1(c)} for d in g.docs.values() for i, c in enumerate(chunk(d["body"]))])
    return {"nodes": nodes, "edges": edges, "docs": docs, "chunks": chunks,
            "snapshot": str(df["snapshot_date"].iloc[0])}


def source_hash() -> str:
    h = hashlib.sha1()
    for p in sorted(config.KNOWLEDGE.rglob("*")):
        if p.is_file() and p.suffix in (".yaml", ".md", ".json"):
            h.update(p.read_bytes())
    for p in ("class.parquet", "score.parquet"):
        h.update((config.PROCESSED / p).read_bytes())
    return h.hexdigest()


def write(kg: dict) -> Path:
    KG_DIR.mkdir(parents=True, exist_ok=True)
    for name in ("nodes", "edges", "docs", "chunks"):
        t = kg[name].copy()
        for c in ("props", "evidence"):
            if c in t:
                t[c] = t[c].map(lambda v: json.dumps(v, ensure_ascii=False, default=str))
        t.to_parquet(KG_DIR / f"{name}.parquet", index=False)
        t.to_json(KG_DIR / f"{name}.jsonl", orient="records", lines=True, force_ascii=False)
    meta = {"snapshot": kg["snapshot"], "source_hash": source_hash(),
            **{n: len(kg[n]) for n in ("nodes", "edges", "docs", "chunks")}}
    (KG_DIR / "build.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return KG_DIR


def load_db() -> dict:
    from pds import db
    p = KG_DIR
    meta = json.loads((p / "build.json").read_text(encoding="utf-8"))
    tables = {"pds_kg_node": ("nodes", ["node_id", "type", "key", "name", "props", "source"]),
              "pds_kg_edge": ("edges", ["src", "dst", "type", "status", "props", "evidence", "source"]),
              "pds_kg_doc": ("docs", ["doc_id", "node_id", "kind", "title", "body", "source", "hash"]),
              "pds_kg_chunk": ("chunks", ["chunk_id", "doc_id", "seq", "text", "hash"])}
    with db.connect() as conn:
        db.migrate(conn)
        conn.execute("truncate pds_kg_node, pds_kg_edge, pds_kg_doc, pds_kg_chunk")
        for table, (name, cols) in tables.items():
            t = pd.read_parquet(p / f"{name}.parquet")[cols]
            db._copy(conn, table, t)
        conn.execute("insert into pds_kg_build (snapshot, source_hash, nodes, edges, docs, chunks) values (%s,%s,%s,%s,%s,%s)",
                     (meta["snapshot"], meta["source_hash"], meta["nodes"], meta["edges"], meta["docs"], meta["chunks"]))
        conn.commit()
    return meta
