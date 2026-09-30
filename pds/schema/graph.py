"""Key · Mapping · Edge · Context · Recipe · Gap · Law · Issuer · Target. KNOWLEDGE-SPEC §3.2~§3.7, §9."""
from __future__ import annotations

import datetime as dt
from typing import Any, Literal

from pydantic import Field, model_validator

from pds.schema.common import Strict

DIMENSIONS = ("life_context", "spatial_regulation", "admin_area", "shared_key", "shared_source", "same_concept", "economic")


# ─────────────────────────── Key — knowledge/keys/{id}.yaml
class RelatedKey(Strict):
    key: str
    relation: Literal["parent", "child", "prefix", "same_as", "maps_to", "composed_of"]
    note: str | None = None


class Key(Strict):
    id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    name: str
    type: Literal["primary", "foreign", "natural", "unique"] = "natural"
    scope: Literal["global", "family"] = "global"
    format: str | None = Field(None, description="사람용 형식 설명")
    pattern: str | None = Field(None, description="값 검증 정규식 (있으면)")
    master_datasets: list[str] = Field(default_factory=list, description="원장 데이터셋 id")
    composed_of: list[str] = Field(default_factory=list)
    issuer: str | None = Field(None, description="코드 부여 주체")
    related_keys: list[RelatedKey] = Field(default_factory=list)
    shape_names: list[str] = Field(default_factory=list, description="pds/rank/shape.py 연계 키 판정 이름")
    notes: str | None = None


# ─────────────────────────── Mapping — knowledge/mappings/{a}__{b}.yaml (+ parquet)
class MappingSide(Strict):
    key: str
    system: str


class Mapping(Strict):
    id: str = Field(pattern=r"^[a-z0-9_]+__[a-z0-9_]+$")
    left: MappingSide
    right: MappingSide
    method: Literal["exact", "name_address_match", "coord_nearest", "manual", "composite"]
    built_at: dt.date
    rows: int = Field(ge=0)
    match_rate: float = Field(ge=0, le=1)
    unmatched_policy: Literal["keep_left", "keep_right", "keep_both", "drop"]
    file: str
    sources: list[str] = Field(default_factory=list, description="매핑을 만든 데이터셋 id")
    notes: str | None = None

    @model_validator(mode="after")
    def _id_matches(self):
        if self.id != f"{self.left.key}__{self.right.key}":
            raise ValueError(f"id는 {self.left.key}__{self.right.key}")
        return self


# ─────────────────────────── Edge — knowledge/edges.yaml
class EdgeOn(Strict):
    left: list[str] = Field(default_factory=list)
    right: list[str] = Field(default_factory=list)
    via_mapping: str | None = None
    transform: str | None = Field(None, description="knowledge/rules/ 규칙 id 또는 설명")


class EdgeVerified(Strict):
    by: Literal["measured", "documented", "admin"]
    run: str | None = None
    match_rate: float | None = Field(None, ge=0, le=1)
    at: dt.date | None = None


class Edge(Strict):
    id: str = Field(pattern=r"^e-\d{4,}$")
    src: str
    dst: str
    rel: Literal["joinable", "lookup", "instance_of", "supersedes", "same_concept", "continues", "related_to"]
    on: EdgeOn | None = None
    relationship: Literal["one_to_one", "one_to_many", "many_to_one", "many_to_many"] | None = None
    direction: Literal["src_to_dst", "dst_to_src", "both"] = "src_to_dst"
    verified: EdgeVerified | None = None
    source: Literal["auto", "admin", "user"] = "auto"
    confidence: float = Field(0.5, ge=0, le=1)
    note: str | None = None

    @model_validator(mode="after")
    def _join_needs_on(self):
        if self.rel in ("joinable", "lookup") and (not self.on or not self.on.left or not self.on.right):
            raise ValueError(f"{self.rel}은 on.left·on.right가 있어야 한다")
        if self.rel in ("joinable", "lookup") and not self.relationship:
            raise ValueError(f"{self.rel}은 relationship(카디널리티)이 있어야 한다")
        if self.src == self.dst:
            raise ValueError("src == dst")
        return self


# ─────────────────────────── Context — knowledge/contexts/{id}.yaml
class ContextMember(Strict):
    """세부 부문 단위(sector+subsector, Phase 1 방식) 또는 데이터셋 단위(dataset, Phase 3~)."""
    sector: str | None = None
    subsector: str | None = None
    dataset: str | None = None
    role: str | None = None

    @model_validator(mode="after")
    def _one_target(self):
        if not self.sector and not self.dataset:
            raise ValueError("sector 또는 dataset 중 하나는 있어야 한다")
        if self.subsector and not self.sector:
            raise ValueError("subsector는 sector와 함께")
        return self


class Context(Strict):
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]*$")
    name: str
    dimension: Literal[DIMENSIONS]  # type: ignore[valid-type]
    question: str | None = None
    note: str | None = None
    key: str | None = Field(None, description="shared_key 차원의 Key id")
    members: list[ContextMember] = Field(min_length=2)
    requires_mappings: list[str] = Field(default_factory=list)
    recipe: str | None = None
    decided_at: dt.date | None = None
    decided_by: str | None = None


# ─────────────────────────── Recipe — knowledge/recipes/{slug}.yaml
class RecipeDataset(Strict):
    id: str
    role: Literal["primary", "join", "context", "lookup"]


class Step(Strict):
    step: int = Field(ge=1)
    do: Literal["fetch", "join", "aggregate", "filter", "derive", "map"]
    dataset: str | None = None
    edge: str | None = None
    mapping: str | None = None
    params: dict[str, Any] = Field(default_factory=dict)
    by: list[str] = Field(default_factory=list)
    measures: list[str] = Field(default_factory=list)
    produces: str | None = None
    note: str | None = None

    @model_validator(mode="after")
    def _shape(self):
        if self.do == "fetch" and not self.dataset:
            raise ValueError("fetch는 dataset")
        if self.do == "join" and not self.edge:
            raise ValueError("join은 edge — 레시피에서 새 조인을 만들지 않는다")
        return self


class Schedule(Strict):
    cron: str
    reason: str
    evidence: list[str] = Field(default_factory=list, description="claim id")


class RecipeVerified(Strict):
    code_run: str
    at: dt.date
    ok: bool


class Recipe(Strict):
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]*$")
    goal_examples: list[str] = Field(min_length=1)
    context: str | None = None
    datasets: list[RecipeDataset] = Field(min_length=1)
    joins: list[str] = Field(default_factory=list)
    pipeline: list[Step] = Field(min_length=1)
    schedule: Schedule | None = None
    verified: RecipeVerified | None = None
    author: str
    status: Literal["draft", "approved"] = "draft"

    @model_validator(mode="after")
    def _joins_declared(self):
        used = {s.edge for s in self.pipeline if s.edge}
        if not used <= set(self.joins):
            raise ValueError(f"pipeline의 edge {sorted(used - set(self.joins))}가 joins에 없음")
        steps = [s.step for s in self.pipeline]
        if steps != sorted(steps) or len(set(steps)) != len(steps):
            raise ValueError("step 번호는 증가하는 고유값")
        return self


# ─────────────────────────── Gap — knowledge/gaps.yaml (§9-1)
class Gap(Strict):
    id: str = Field(description="{정책분야}/{부문}/{slug}")
    sector: str
    name: str
    question: str | None = Field(None, description="이 공백 때문에 답할 수 없는 질문")
    reason: str
    external_candidate: str | None = Field(None, description="포털 밖 대안 (시스템·사이트)")
    status: Literal["open", "resolved"] = "open"
    resolved_by: str | None = Field(None, description="해소한 세부 부문·데이터")
    decided_at: dt.date | None = None
    decided_by: str | None = None


# ─────────────────────────── Law — knowledge/laws/{law_id}.yaml (§7-6)
class Article(Strict):
    no: str
    title: str | None = None
    text: str


class Law(Strict):
    law_id: str
    name: str
    short_names: list[str] = Field(default_factory=list)
    promulgated: dt.date | None = None
    effective: dt.date | None = None
    articles: list[Article] = Field(default_factory=list)
    source: str = Field(description="open.law.go.kr 조회 URL")
    fetched_at: dt.date


# ─────────────────────────── Issuer — knowledge/key_issuers.yaml
class Issuer(Strict):
    id: str
    name: str
    site: str | None = None
    key_param: str | None = None
    env: dict[str, str] = Field(default_factory=dict, description=".env 변수 이름만 (값 금지)")
    issuance: str | None = None
    match: dict[str, Any] | None = None
    match_any: list[dict[str, Any]] | None = None


# ─────────────────────────── Target — knowledge/targets.json (Phase 1 선정·Phase 2 결과)
class Target(Strict):
    id: str
    title: str
    agency: str
    sector: str
    subsector: str
    subsector_name: str
    kind: Literal["REST", "SOAP", "STD", "FILE", "API_LINK", "FILE_LINK"]
    prelim_score: float
    usage: int
    url: str
    round: Literal["1", "2", "3", "external"]
    why: str
    status: Literal["pending", "verified", "failed"]
    probe: dict[str, Any] | None = None
    note: str | None = None
    substitute_for: str | None = None
    substituted_by: str | None = None
