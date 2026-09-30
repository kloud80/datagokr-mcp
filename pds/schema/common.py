"""공통 조각 — 근거(Evidence)와 사실 진술(Claim). KNOWLEDGE-SPEC §3.5 (Wikibase statement 구조)."""
from __future__ import annotations

import datetime as dt
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Strict(BaseModel):
    """지식 파일 공통: 모르는 필드는 오류 (오타를 조용히 넘기지 않는다)."""
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


EvidenceType = Literal["measured", "law", "portal_meta", "admin_review", "inferred", "user"]
# 프로토콜에 나갈 수 있는 근거 (원칙 §10-2). portal_meta·inferred·user만으로는 사실이 아니다.
GROUNDED: frozenset[str] = frozenset({"measured", "law", "admin_review"})

ClaimKind = Literal["cadence", "publish_lag", "legal_basis", "key", "coverage", "health", "pitfall",
                    "join_verified", "admin_note", "access"]


class Evidence(Strict):
    type: EvidenceType
    source: str = Field(description="근거 위치: 파일 경로#앵커, law:{id}#{조}, 포털 URL 등")
    observed_at: dt.date | None = Field(None, description="측정·관측일 (measured)")
    by: str | None = Field(None, description="결정·검토한 사람 (admin_review·user)")
    at: dt.date | None = Field(None, description="결정·검토일")
    detail: str | None = None


class Claim(Strict):
    id: str = Field(pattern=r"^c-[\w:.-]+-\d{2,}$", description="c-{dataset id}-{두 자리 이상 번호}")
    kind: ClaimKind
    value: str
    evidence: list[Evidence] = Field(min_length=1)
    qualifiers: dict[str, Any] = Field(default_factory=dict)
    rank: Literal["preferred", "normal", "deprecated"] = "normal"
    valid_until: dt.date | None = None

    @property
    def grounded(self) -> bool:
        return any(e.type in GROUNDED for e in self.evidence)

    @field_validator("value")
    @classmethod
    def _non_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("빈 값")
        return v
