"""pds validate — 지식 원본 전체를 스키마와 상호 참조로 검사한다. KNOWLEDGE-SPEC §5 (CI에서 PR마다).

단계
  1. 파일별 pydantic 검증 (형식·필수 필드·엔티티 내부 규칙)
  2. 상호 참조: Key·Dataset·Mapping·Edge·Context·Recipe·Law·세부 부문 id가 실제로 있는가, id 중복
  3. 승격 조건(§2.2): verified Dataset의 근거 있는 claim ≥ 3(cadence·key·access) · Edge ≥ 1
     기본은 경고, --strict면 오류 (적용 메모 5)
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd
import yaml
from pydantic import ValidationError

from pds import config
from pds.schema import MODELS
from pds.schema import store

LIST_KINDS = ("edge", "gap", "issuer", "target")


@dataclass
class Report:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    counts: Counter = field(default_factory=Counter)

    def err(self, where, msg):
        self.errors.append(f"{where}: {msg}")

    def warn(self, where, msg):
        self.warnings.append(f"{where}: {msg}")

    @property
    def ok(self) -> bool:
        return not self.errors


def _fmt(e: ValidationError) -> str:
    return "; ".join(f"{'.'.join(map(str, x['loc'])) or '(root)'} {x['msg']}" for x in e.errors()[:6])


def _catalog_ids() -> set[str]:
    p = config.PROCESSED / "catalog.parquet"
    return set(pd.read_parquet(p, columns=["id"])["id"].astype(str)) if p.exists() else set()


def _subsectors() -> dict[str, set[str]]:
    path = config.KNOWLEDGE / "sectors" / "subsectors.yaml"
    out = {}
    for s in yaml.safe_load(path.read_text(encoding="utf-8")) or []:
        out[s["sector"]] = {x["slug"] for x in s["subsectors"]} | ({s["default"]["slug"]} if s.get("default") else set())
    return out


def run(strict: bool = False) -> tuple[Report, dict[str, list]]:
    rep = Report()
    objs: dict[str, list] = defaultdict(list)
    where: dict[tuple[str, str], str] = {}

    # 1) 파일별
    for kind, model in MODELS.items():
        if kind == "claim":
            continue
        for i, (raw, path) in enumerate(store.iter_raw(kind)):
            loc = store.rel(path) + (f"[{i}]" if kind in LIST_KINDS else "")
            try:
                obj = model.model_validate(raw)
            except ValidationError as e:
                rep.err(loc, _fmt(e))
                continue
            objs[kind].append(obj)
            oid = getattr(obj, "id", None) or getattr(obj, "law_id", None)
            if oid is not None:
                if (kind, oid) in where:
                    rep.err(loc, f"{kind} id {oid} 중복 ({where[(kind, oid)]})")
                where[(kind, oid)] = loc
            # 디렉터리형은 파일명 = id
            if kind in ("key", "context", "recipe", "mapping", "code") and path.stem != oid:
                rep.err(loc, f"파일명 {path.stem} ≠ id {oid}")
            if kind == "law" and path.stem != obj.law_id:
                rep.err(loc, f"파일명 {path.stem} ≠ law_id {obj.law_id}")
            if kind == "dataset" and path != store.dataset_path(obj.sector, obj.id):
                rep.err(loc, f"경로는 {store.rel(store.dataset_path(obj.sector, obj.id))}")
            rep.counts[kind] += 1

    keys = {k.id for k in objs["key"]}
    datasets = {d.id: d for d in objs["dataset"]}
    catalog = _catalog_ids()
    known_ds = catalog | set(datasets)
    mappings = {m.id for m in objs["mapping"]}
    edges = {e.id: e for e in objs["edge"]}
    contexts = {c.id for c in objs["context"]}
    laws = {law.law_id for law in objs["law"]}
    subs = _subsectors()

    def ds_ref(loc, dsid, what):
        if catalog and dsid not in known_ds:
            rep.err(loc, f"{what} {dsid}: 카탈로그·datasets에 없음")

    # 2) 상호 참조
    for k in objs["key"]:
        loc = f"keys/{k.id}"
        for r in k.related_keys:
            if r.key not in keys:
                rep.err(loc, f"related_keys.{r.key} 없음")
        for m in k.master_datasets:
            if catalog and m not in known_ds:
                rep.warn(loc, f"master {m}: 카탈로그에 없음")

    for m in objs["mapping"]:
        loc = f"mappings/{m.id}"
        for side in (m.left, m.right):
            if side.key not in keys:
                rep.err(loc, f"key {side.key} 없음")
        if not (config.KNOWLEDGE / m.file).exists():
            rep.err(loc, f"file {m.file} 없음")

    claim_ids = Counter()
    for d in objs["dataset"]:
        loc = store.rel(store.dataset_path(d.sector, d.id))
        f, a, s = d.sector.split("/")
        sec = f"{f} - {a}"
        if sec not in subs:
            rep.err(loc, f"부문 {sec} 없음 (subsectors.yaml)")
        elif s not in subs[sec]:
            rep.err(loc, f"세부 부문 {s} 없음 ({sec})")
        if catalog and d.channel == "portal" and d.id not in catalog:
            rep.err(loc, "포털 목록키가 카탈로그에 없음")
        for fk in d.schema_.foreign_keys:
            if fk.reference.key not in keys:
                rep.err(loc, f"foreign_keys → {fk.reference.key} 없음")
        for fld in d.schema_.fields:
            if fld.semantic_type and fld.semantic_type not in keys:
                rep.err(loc, f"field {fld.name}.semantic_type {fld.semantic_type} 없음")
        for svc in d.services:
            for p in svc.params:
                if p.semantic_type and p.semantic_type not in keys:
                    rep.err(loc, f"param {svc.op}.{p.name}.semantic_type {p.semantic_type} 없음")
        for lg in d.applicable_legislation:
            if lg.law_id and lg.law_id not in laws:
                rep.warn(loc, f"법령 {lg.law_id}({lg.law}) 원문 미확보 (knowledge/laws/)")
        for c in d.claims:
            claim_ids[c.id] += 1
            if not c.id.startswith(f"c-{d.id}-"):
                rep.err(loc, f"claim {c.id}는 c-{d.id}-NN 형식")
        for h in d.edges_hint:
            ds_ref(loc, h, "edges_hint")
    for cid, n in claim_ids.items():
        if n > 1:
            rep.err("claims", f"{cid} 중복 {n}회")

    deg = Counter()
    for e in objs["edge"]:
        loc = f"edges.yaml:{e.id}"
        for end in (e.src, e.dst):
            ds_ref(loc, end, "끝점")
            deg[end] += 1
        if e.on and e.on.via_mapping and e.on.via_mapping not in mappings:
            rep.err(loc, f"via_mapping {e.on.via_mapping} 없음")
        for end in (e.src, e.dst):
            d = datasets.get(end)
            if d is not None and d.tier == "candidate" and e.rel == "joinable":
                rep.err(loc, f"{end}는 candidate — 조인 참여 불가 (§4)")

    for c in objs["context"]:
        loc = f"contexts/{c.id}"
        if c.key and c.key not in keys:
            rep.err(loc, f"key {c.key} 없음")
        for m in c.members:
            if m.sector:
                if m.sector not in subs:
                    rep.err(loc, f"멤버 부문 {m.sector} 없음")
                elif m.subsector and m.subsector not in subs[m.sector]:
                    rep.err(loc, f"멤버 세부 부문 {m.sector}/{m.subsector} 없음")
            if m.dataset:
                ds_ref(loc, m.dataset, "멤버")
        for mp in c.requires_mappings:
            if mp not in mappings:
                rep.warn(loc, f"requires_mappings {mp} 아직 없음")
        if c.recipe and not (config.KNOWLEDGE / c.recipe).exists():
            rep.err(loc, f"recipe {c.recipe} 없음")

    for r in objs["recipe"]:
        loc = f"recipes/{r.id}"
        if r.context and r.context not in contexts:
            rep.err(loc, f"context {r.context} 없음")
        for j in r.joins:
            if j not in edges:
                rep.err(loc, f"edge {j} 없음 — 레시피는 선언된 Edge만 쓴다")
        for x in r.datasets:
            ds_ref(loc, x.id, "dataset")
            d = datasets.get(x.id)
            if d is None or d.tier != "verified":
                rep.err(loc, f"{x.id}는 verified Dataset이 아님 — 레시피에 쓸 수 없다")

    codes = {c.id for c in objs["code"]}
    for c in objs["code"]:
        loc = f"codes/{c.id}"
        if c.key and c.key not in keys:
            rep.err(loc, f"key {c.key} 없음")
        if c.file and not (config.KNOWLEDGE / c.file).exists():
            rep.err(loc, f"file {c.file} 없음")
        for u in c.used_by:
            ds_ref(loc, u.dataset, "used_by")
    for d in objs["dataset"]:
        for fld in d.schema_.fields:
            if fld.code_list and fld.code_list not in codes:
                rep.err(store.rel(store.dataset_path(d.sector, d.id)), f"field {fld.name}.code_list {fld.code_list} 없음")

    for g in objs["gap"]:
        if g.sector not in subs:
            rep.err(f"gaps.yaml:{g.id}", f"부문 {g.sector} 없음")

    for t in objs["target"]:
        if catalog and t.id not in catalog:
            rep.err(f"targets.json:{t.id}", "카탈로그에 없음")

    # 3) 승격 조건
    gate = rep.err if strict else rep.warn
    for d in objs["dataset"]:
        loc = store.rel(store.dataset_path(d.sector, d.id))
        for p in d.gate_problems():
            gate(loc, f"[승격] {p}")
        if d.tier == "verified" and deg[d.id] == 0:
            gate(loc, "[승격] Edge 0개 (≥ 1)")
    return rep, objs


def export_json_schema(out_dir: Path | None = None) -> list[Path]:
    out_dir = out_dir or (config.ROOT / "schemas")
    out_dir.mkdir(exist_ok=True)
    paths = []
    for kind, model in MODELS.items():
        p = out_dir / f"{kind}.schema.json"
        s = model.model_json_schema(by_alias=True)
        s["$id"] = f"https://pds.local/schemas/{kind}.schema.json"
        s["title"] = model.__name__
        p.write_text(json.dumps(s, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        paths.append(p)
    return paths
