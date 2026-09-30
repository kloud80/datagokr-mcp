"""데이터 패밀리 (knowledge/families/<slug>/) — 검증과 오퍼레이션 목록 생성. 표준: knowledge/families/README.md"""
from __future__ import annotations

import json
import re
from pathlib import Path

import jsonschema
import yaml

from pds import config

FAMILIES = config.KNOWLEDGE / "families"
SCHEMA = FAMILIES / "_schema.json"


def family_dir(slug: str) -> Path:
    return FAMILIES / slug


def load(slug: str) -> dict:
    return yaml.safe_load((family_dir(slug) / "family.yaml").read_text(encoding="utf-8"))


def load_reference_docs(slug: str) -> dict | None:
    p = config.REF / "families" / slug / "reference_docs.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def check(slug: str) -> list[str]:
    """스키마 + 참조 무결성 검사. 문제 목록을 돌려준다 (빈 목록 = 통과)."""
    fam = load(slug)
    errors: list[str] = []
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    as_json = json.loads(json.dumps(fam, default=str))  # YAML 날짜(date) → 문자열
    for e in jsonschema.Draft202012Validator(schema).iter_errors(as_json):
        errors.append(f"schema: {'/'.join(map(str, e.path))}: {e.message}")

    ds_ids = {d["id"] for d in fam.get("datasets", [])}
    key_ids = {k["id"] for k in fam.get("keys", [])}
    ent_ids = {e["id"] for e in fam.get("entities", [])}

    for dup_src, ids in (("datasets", [d["id"] for d in fam["datasets"]]),
                         ("keys", [k["id"] for k in fam["keys"]]),
                         ("entities", [e["id"] for e in fam["entities"]])):
        dups = {x for x in ids if ids.count(x) > 1}
        if dups:
            errors.append(f"{dup_src}: 중복 id {sorted(dups)}")

    for e in fam["entities"]:
        for k in e["keys"]:
            if k not in key_ids:
                errors.append(f"entity {e['id']}: 없는 키 {k}")
    for k in fam["keys"]:
        for a in k["aliases"]:
            if a["dataset"] not in ds_ids:
                errors.append(f"key {k['id']}: 패밀리에 없는 데이터셋 {a['dataset']}")
    for d in fam["datasets"]:
        for k in d.get("provides_keys", []) + d.get("lookup_by", []):
            if k not in key_ids:
                errors.append(f"dataset {d['id']}: 없는 키 {k}")
        ents = d.get("entity") or []
        for en in ([ents] if isinstance(ents, str) else ents):
            if en not in ent_ids:
                errors.append(f"dataset {d['id']}: 없는 엔티티 {en}")

    def node_ok(x: str, typ: str) -> bool:
        if typ == "lifecycle":
            return x in ent_ids
        if typ == "hierarchy":
            return x in key_ids
        if x.startswith("*."):
            return x[2:] in key_ids
        return x in ds_ids

    for i, e in enumerate(fam["edges"]):
        tos = e["to"] if isinstance(e["to"], list) else [e["to"]]
        for x in [e["from"], *tos]:
            if not node_ok(x, e["type"]):
                errors.append(f"edge[{i}] {e['type']}: 알 수 없는 노드 {x}")
        for k in ("via", "key"):
            if k in e and e[k] not in key_ids:
                errors.append(f"edge[{i}]: 없는 키 {e[k]}")

    # evidence 'doc:<id>#<operation>'이 실제 참고자료에 있는지
    docs = load_reference_docs(slug)
    if docs:
        ops = {i: {o["name_en"] for o in s["ops"]} for i, s in docs.items()}
        for i, e in enumerate(fam["edges"]):
            for ev in e["evidence"]:
                m = re.match(r"doc:(\d+)#(get\w+)$", ev)
                if m and m.group(2) not in ops.get(m.group(1), set()):
                    errors.append(f"edge[{i}] evidence: {ev} — 참고자료에 없는 오퍼레이션")
    return errors


def render_operations(slug: str) -> Path:
    """참고자료 파싱본 → operations.md (손으로 고치지 않는다)."""
    fam = load(slug)
    docs = load_reference_docs(slug)
    if docs is None:
        raise FileNotFoundError(f"data/ref/families/{slug}/reference_docs.json 없음")
    skip = {"numOfRows", "pageNo", "ServiceKey", "serviceKey", "type", "Type"}
    order = [d["id"] for d in fam["datasets"]]
    short = {d["id"]: d["short"] for d in fam["datasets"]}
    L = [f"# {fam['title']} — 오퍼레이션 전체 목록",
         "",
         "> 자동 생성 (`python -m pds family-ops " + slug + "`). 원천: 조달청 OpenAPI 참고자료 docx. 손으로 고치지 말 것.",
         "> 요청 파라미터의 `*`는 필수. 공통(serviceKey·pageNo·numOfRows·type)은 생략.",
         ""]
    total = 0
    for ds in order:
        s = docs.get(ds)
        if not s:
            continue
        L += [f"## {short[ds]} — {s.get('서비스명(국문)', '')} ({ds})", "",
              f"- 서비스 ID `{s.get('서비스 ID', '')}` · 오퍼레이션 {len(s['ops'])}개 · 갱신 {s.get('갱신주기', '')}",
              "", "| # | 오퍼레이션 | 이름 | 요청 파라미터 | 응답 항목 수 | 설명 |", "| ---: | --- | --- | --- | ---: | --- |"]
        for n, o in enumerate(s["ops"], 1):
            params = ", ".join(f"`{r['name']}`{'*' if r['req'] == '1' else ''}" for r in o["req"] if r["name"] not in skip)
            desc = (o.get("desc") or "").replace("|", "／").replace("\n", " ")
            L.append(f"| {n} | `{o['name_en']}` | {o['name_ko']} | {params} | {len(o['resp'])} | {desc[:220]} |")
            total += 1
        L.append("")
    L.insert(4, f"총 {len(order)}개 서비스, {total}개 오퍼레이션.")
    out = family_dir(slug) / "operations.md"
    out.write_text("\n".join(L), encoding="utf-8")
    return out
