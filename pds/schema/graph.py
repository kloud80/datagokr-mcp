"""Key · Mapping · Edge · Context · Recipe · Gap · Law · Issuer · Target. KNOWLEDGE-SPEC §3.2~§3.7, §9."""
from __future__ import annotations

import datetime as dt
from typing import Any, Literal

from pydantic import Field, model_validator

from pds.schema.common import Evidence, Strict  # noqa: F401 — CodeList.evidence

DIMENSIONS = ("life_context", "spatial_regulation", "admin_area", "shared_key", "shared_source", "same_concept", "economic")


# ─────────────────────────── Key — knowledge/keys/{id}.yaml
class RelatedKey(Strict):
    key: str
    relation: Literal["parent", "child", "prefix", "same_as", "maps_to", "composed_of"]
    note: str | None = None


class KeyField(Strict):
    """이 키를 담은 필드 — 기관 고유 키처럼 필드명이 데이터마다 다를 때 (pds.knowledge.agency_review가 제안, 실측 컬럼으로 확인)."""
    names: list[str] = Field(min_length=1, description="실측 컬럼명")
    datasets: list[str] = Field(default_factory=list, description="이 필드명이 이 키인 데이터 id (비우면 모든 데이터)")


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
    fields: list[KeyField] = Field(default_factory=list, description="이 키를 담은 필드 (데이터별) — gen_dataset이 semantic_type으로 붙인다")
    agency: str | None = Field(None, description="고유 키를 부여·운영하는 기관 코드")
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


# ─────────────────────────── CodeList — knowledge/codes/{id}.yaml (+ .parquet) — 적용 메모 6 (2026-09-30 구름 제안)
class CodeValue(Strict):
    code: str
    name: str
    count: int | None = Field(None, description="관측·스캔 빈도")
    valid: bool = True
    note: str | None = None


class CodeUse(Strict):
    dataset: str
    field: str
    name_field: str | None = Field(None, description="같은 응답에 이름 컬럼이 같이 오면")


class CodeList(Strict):
    """코드값 → 이름표. AI가 필터 파라미터를 정확히 넣고 결과를 사람 말로 풀려면 전수가 필요하다."""
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9_.\-]*$")
    name: str
    key: str | None = Field(None, description="이 코드가 조인 키이기도 하면 Key id (예: bjd_cd)")
    completeness: Literal["complete", "master_scan", "observed"] = Field(
        description="complete=공식 원천 전체 · master_scan=전수 원장을 훑어 쓰이는 값 전부 · observed=표본에서 본 값만")
    evidence: list["Evidence"] = Field(min_length=1)
    aliases: list[str] = Field(default_factory=list, description="이 코드를 싣는 컬럼 이름들 (예: lndcgrCode, jimok)")
    values: list[CodeValue] = Field(default_factory=list)
    file: str | None = Field(None, description="값이 많으면 parquet (code, name, valid, …)")
    rows: int = Field(ge=1)
    used_by: list[CodeUse] = Field(default_factory=list)
    notes: str | None = None

    @model_validator(mode="after")
    def _values_or_file(self):
        if not self.values and not self.file:
            raise ValueError("values 또는 file")
        if self.values and len(self.values) != self.rows:
            raise ValueError(f"rows {self.rows} ≠ values {len(self.values)}")
        codes = [v.code for v in self.values]
        if len(codes) != len(set(codes)):
            raise ValueError("code 중복")
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
    round: Literal["1", "2", "3", "4", "5", "6", "7", "8", "9", "external"]  # 4·5·6·7 = 2·3·4·5차 확대 (knowledge/expansion/wave2·3·4·5)
    why: str
    status: Literal["pending", "verified", "failed"]
    probe: dict[str, Any] | None = None
    note: str | None = None
    substitute_for: str | None = None
    substituted_by: str | None = None


# ─────────────────────────── Agency — knowledge/agencies/{agency_code}.yaml (기관별 핵심 데이터·관계)
class AgencySystem(Strict):
    """기관이 운영하는 원천 시스템 하나 (예: 나라장터, 건축HUB, 가맹사업거래) — 그 시스템에서 나온 데이터 묶음."""
    name: str
    description: str | None = None
    datasets: list[str] = Field(default_factory=list, description="이 시스템에서 나온 데이터 id (층 무관)")
    core: list[str] = Field(default_factory=list, description="시스템의 핵심 원장 (개체 단위·전수) — 검증 대상 우선")
    native_keys: list[str] = Field(default_factory=list, description="시스템 고유 식별자 (Key id 또는 필드명)")


class AgencyRelation(Strict):
    """기관 안(시스템 사이) 또는 기관 밖(다른 기관)과의 관계 — 조인은 Edge로만 선언·실측한다. 여기는 지도."""
    to: str = Field(description="상대 기관 코드 또는 'self:<시스템>'")
    via: str = Field(description="잇는 키 (Key id 또는 필드명)")
    datasets: list[str] = Field(default_factory=list)
    status: Literal["proposed", "declared", "measured", "failed"] = "proposed"
    edges: list[str] = Field(default_factory=list, description="이 관계를 실현한 Edge id")
    note: str | None = None


class Agency(Strict):
    id: str = Field(pattern=r"^[0-9A-Z]{7}$", description="행정표준 기관코드 (포털 제공기관코드)")
    name: str
    type: Literal["central", "public", "metro", "local", "education", "other"]
    parent: str | None = Field(None, description="상위 기관 코드 (instt_cd 비고)")
    tier: Literal["A", "B", "C", "D"] = Field(description="A 중앙·공공 정밀 · B 광역 · C 기초 · D 소규모")
    counts: dict[str, int] = Field(default_factory=dict, description="catalog · verified · core · edges_within · edges_across")
    systems: list[AgencySystem] = Field(default_factory=list)
    core_missing: list[str] = Field(default_factory=list, description="핵심인데 아직 검증 안 된 데이터 id")
    native_keys: list[str] = Field(default_factory=list)
    relations: list[AgencyRelation] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list, description="이 기관 데이터로 답할 수 없는 것·접근 막힘")
    external_portal: str | None = Field(None, description="기관 자체 개방 사이트 (예: data.gg.go.kr)")
    analyzed_by: str | None = None
    analyzed_at: dt.date | None = None
    note: str | None = None
