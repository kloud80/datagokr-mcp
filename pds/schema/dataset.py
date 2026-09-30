"""Dataset — knowledge/datasets/{정책분야}/{id}.yaml. KNOWLEDGE-SPEC §3.1.

어휘 차용: DCAT 3(services·distributions·accrual_periodicity), DCAT-AP 3(applicable_legislation),
Frictionless Table Schema(schema), ODCS v3(sla·team), OpenAPI 3.1(security), Snowflake Semantic View(synonyms·sample_values).
catalog 층은 파일이 없다 — tier는 verified | candidate만.
"""
from __future__ import annotations

import datetime as dt
from typing import Any, Literal

from pydantic import Field, model_validator

from pds.schema.common import Claim, Strict


class AgencyRef(Strict):
    id: str | None = None
    name: str


class Legislation(Strict):
    law: str = Field(description="법령명 (약칭 가능)")
    law_id: str | None = Field(None, description="법제처 법령ID — knowledge/laws/{law_id}.yaml")
    articles: list[str] = Field(default_factory=list)
    source: str | None = Field(None, description="어디서 이 근거를 읽었나 (portal_meta: 보유근거 등)")


class Sla(Strict):
    frequency: str | None = None
    latency_days: float | None = None
    time_of_availability: str | None = None


class Team(Strict):
    dept: str | None = None
    phone: str | None = None


class Security(Strict):
    scheme: Literal["apiKey", "none", "oauth2", "session"] = "apiKey"
    in_: Literal["query", "header", "path"] = Field("query", alias="in")
    name: str | None = None
    issuer: str = Field(description="key_issuers.yaml id 또는 data.go.kr")


class Param(Strict):
    name: str
    required: bool = False
    semantic_type: str | None = Field(None, description="Key id — 이 값을 다른 데이터에서 받아와야 하면 lookup Edge 후보")
    format: str | None = None
    example: str | None = None
    desc: str | None = None


class Paging(Strict):
    page: str | None = None
    size: str | None = None
    max_size: int | None = None


class Service(Strict):
    op: str
    name: str | None = None
    endpoint: str
    method: Literal["GET", "POST"] = "GET"
    security: Security
    params: list[Param] = Field(default_factory=list)
    paging: Paging | None = None
    approval: Literal["auto", "review", "external", "unknown"] = "unknown"
    traffic: dict[str, int] = Field(default_factory=dict)
    format: list[str] = Field(default_factory=list)
    error_style: Literal["http200_body_code", "http_status", "unknown"] = "unknown"
    verified_ok: bool | None = Field(None, description="Phase 2 실호출 성공 여부")


class Distribution(Strict):
    url: str | None = None
    format: str | None = None
    size: int | None = None
    updated: dt.date | None = None
    title: str | None = None


class FieldStats(Strict):
    min: Any = None
    p50: Any = None
    max: Any = None
    unique: int | None = None


class TableField(Strict):
    name: str
    title: str | None = Field(None, description="명세상 의미")
    type: Literal["string", "integer", "number", "date", "datetime", "boolean", "code", "geo", "any"] = "any"
    semantic_type: str | None = Field(None, description="Key id")
    unit: str | None = None
    null_rate: float | None = Field(None, ge=0, le=1)
    sample_values: list[str] = Field(default_factory=list)
    stats: FieldStats | None = None
    op: str | None = Field(None, description="여러 오퍼레이션이면 어느 응답의 컬럼인가")


class ForeignKeyRef(Strict):
    key: str


class ForeignKey(Strict):
    fields: list[str] = Field(min_length=1)
    reference: ForeignKeyRef
    evidence: Literal["measured", "portal_meta", "documented"] = "measured"


class TableSchema(Strict):
    primary_key: list[str] | None = None
    dedupe_rule: list[str] | None = None
    fields: list[TableField] = Field(default_factory=list)
    foreign_keys: list[ForeignKey] = Field(default_factory=list)


class Coverage(Strict):
    spatial: str | None = None
    admin_unit: str | None = None
    temporal: str | None = None


class Verification(Strict):
    verdict: str
    probed_at: dt.date | None = None
    channel: Literal["portal", "external"] = "portal"
    rows: int | None = None
    total_count: int | None = None
    ops_ok: str | None = Field(None, description="성공 오퍼레이션/전체")
    latency_ms: float | None = None
    latest: str | None = None
    lag_days: int | None = None
    run: str | None = None
    stats: str | None = None
    data: str | None = None

    @property
    def success(self) -> bool:
        return self.verdict.startswith("성공")


class Classification(Strict):
    """Phase 1 분류·점수 (파생값의 스냅샷 — 원본은 class/score parquet)."""
    subsector_name: str | None = None
    depth: Literal["front", "back", "hold", "system"] | None = None
    novelty: Literal["high", "medium", "low"] | None = None
    cross_cutting: bool = False
    prelim_score: float | None = None
    rank_in_sector: int | None = None
    brm: str | None = Field(None, description="포털 원래 BRM (재배치 전)")
    sector_rule: str | None = Field(None, description="재배치 규칙 id")
    why: str | None = Field(None, description="Phase 1 선정 이유 (targets.json)")


class Dataset(Strict):
    id: str = Field(pattern=r"^([a-z0-9.\-]+:)?[\w.-]+$")
    tier: Literal["verified", "candidate"]
    title: str
    family: str | None = None
    sector: str = Field(pattern=r"^[^/]+/[^/]+/[^/]+$", description="정책분야/부문/세부 부문 slug")
    domain: str | None = Field(None, description="sector_tree.yaml domain id")
    agency: AgencyRef
    kind: Literal["API", "FILE", "STD", "EXTERNAL_API", "EXTERNAL_FILE"]
    channel: Literal["portal", "external"]
    portal_url: str | None = None
    synonyms: list[str] = Field(default_factory=list)
    summary_user: str | None = None
    description_portal: str | None = Field(None, description="포털 등록 설명 원문 (LLM 재작성 전)")
    applicable_legislation: list[Legislation] = Field(default_factory=list)
    legal_basis_portal: str | None = Field(None, description="포털 보유근거 원문 (법령명이 아닌 문구 포함)")
    accrual_periodicity: str | None = None
    sla: Sla | None = None
    team: Team | None = None
    services: list[Service] = Field(default_factory=list)
    distributions: list[Distribution] = Field(default_factory=list)
    schema_: TableSchema = Field(default_factory=TableSchema, alias="schema")
    facets: dict[str, list[str]] = Field(default_factory=dict)
    coverage: Coverage | None = None
    cycle: Literal["default", "event", "annual-batch", "realtime", "ended"] = "default"
    classification: Classification | None = None
    claims: list[Claim] = Field(default_factory=list)
    edges_hint: list[str] = Field(default_factory=list)
    verification: Verification | None = None
    limits: str | None = None
    status: Literal["active", "suspect_dead", "hidden", "ended"] = "active"

    @model_validator(mode="after")
    def _tier_rules(self):
        if self.tier == "verified":
            if not self.verification or not self.verification.success:
                raise ValueError("verified는 성공한 verification이 있어야 한다")
        ids = [c.id for c in self.claims]
        if len(ids) != len(set(ids)):
            raise ValueError("claim id 중복")
        if self.kind in ("API", "EXTERNAL_API") and self.tier == "verified" and not self.services:
            raise ValueError("verified API는 services가 있어야 한다")
        return self

    # ── 승격 조건 (§2.2) — 파일 하나로 판단 가능한 부분. Edge ≥ 1은 validate가 edges.yaml과 대조
    def gate_problems(self) -> list[str]:
        out = []
        if self.tier != "verified":
            return out
        grounded = [c for c in self.claims if c.grounded]
        if len(grounded) < 3:
            out.append(f"근거 있는 claim {len(grounded)}개 (< 3)")
        kinds = {c.kind for c in grounded}
        for need in ("cadence", "key", "access"):
            if need not in kinds:
                out.append(f"claim[{need}] 없음")
        return out
