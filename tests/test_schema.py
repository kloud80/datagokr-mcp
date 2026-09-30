"""지식 스키마 (KNOWLEDGE-SPEC §3) — 모델 규칙과 저장소 전체 검증."""
import pytest
from pydantic import ValidationError

from pds.schema import Claim, Context, Dataset, Edge, Recipe
from pds.schema.validate import export_json_schema, run

EV = {"type": "measured", "source": "probe/runs/1.json"}


def _ds(**kw):
    base = {"id": "1", "tier": "verified", "title": "t", "sector": "교육/유아및초·중등교육/school-daily",
            "agency": {"name": "교육부"}, "kind": "API", "channel": "portal",
            "services": [{"op": "/x", "endpoint": "https://e", "security": {"issuer": "data.go.kr"}}],
            "verification": {"verdict": "성공"}}
    return Dataset.model_validate(base | kw)


def test_claim_grounding_and_id():
    c = Claim.model_validate({"id": "c-1-01", "kind": "cadence", "value": "일", "evidence": [EV]})
    assert c.grounded
    c2 = Claim.model_validate({"id": "c-1-02", "kind": "cadence", "value": "일",
                               "evidence": [{"type": "inferred", "source": "llm"}]})
    assert not c2.grounded
    with pytest.raises(ValidationError):
        Claim.model_validate({"id": "x", "kind": "cadence", "value": "일", "evidence": [EV]})
    with pytest.raises(ValidationError):  # 근거 없는 claim 금지
        Claim.model_validate({"id": "c-1-03", "kind": "cadence", "value": "일", "evidence": []})


def test_dataset_tier_rules_and_gate():
    d = _ds()
    assert "claim[cadence] 없음" in d.gate_problems()
    with pytest.raises(ValidationError):  # verified인데 검증 실패
        _ds(verification={"verdict": "응답0행"})
    with pytest.raises(ValidationError):  # 모르는 필드
        _ds(unknown=1)
    claims = [{"id": f"c-1-0{i}", "kind": k, "value": "v", "evidence": [EV]} for i, k in enumerate(("cadence", "key", "access"), 1)]
    assert _ds(claims=claims).gate_problems() == []


def test_edge_join_needs_on_and_cardinality():
    with pytest.raises(ValidationError):
        Edge.model_validate({"id": "e-0001", "src": "1", "dst": "2", "rel": "joinable"})
    e = Edge.model_validate({"id": "e-0001", "src": "1", "dst": "2", "rel": "joinable", "relationship": "many_to_one",
                             "on": {"left": ["a"], "right": ["b"]}})
    assert e.confidence == 0.5
    assert Edge.model_validate({"id": "e-0002", "src": "1", "dst": "2", "rel": "related_to"}).on is None


def test_recipe_uses_only_declared_edges():
    base = {"id": "r", "goal_examples": ["g"], "datasets": [{"id": "1", "role": "primary"}], "author": "구름",
            "pipeline": [{"step": 1, "do": "fetch", "dataset": "1"}, {"step": 2, "do": "join", "edge": "e-0001"}]}
    with pytest.raises(ValidationError):
        Recipe.model_validate(base)
    assert Recipe.model_validate(base | {"joins": ["e-0001"]}).pipeline[1].edge == "e-0001"


def test_context_member_forms():
    Context.model_validate({"id": "c", "name": "n", "dimension": "life_context",
                            "members": [{"sector": "a - b", "subsector": "x"}, {"dataset": "1"}]})
    with pytest.raises(ValidationError):
        Context.model_validate({"id": "c", "name": "n", "dimension": "nope", "members": [{"dataset": "1"}, {"dataset": "2"}]})


def test_repository_validates():
    """저장소의 지식 파일 전체가 스키마·상호 참조 검사를 통과한다 (승격 조건은 경고)."""
    rep, objs = run()
    assert rep.ok, rep.errors[:20]
    assert len(objs["key"]) >= 58 and len(objs["context"]) >= 41 and len(objs["gap"]) >= 5 and len(objs["target"]) >= 295


def test_json_schema_export(tmp_path):
    paths = export_json_schema(tmp_path)
    assert {p.stem for p in paths} >= {"dataset.schema", "edge.schema", "claim.schema"}
