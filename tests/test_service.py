"""전략 플래너·서비스 API (KNOWLEDGE-SPEC §4·§6) — LLM 없이 도는 부분."""
import pytest

from pds import config

needs_catalog = pytest.mark.skipif(not (config.PROCESSED / "catalog.parquet").exists(), reason="카탈로그 없음 (python -m pds build)")


def test_clean_goal_strips_intent():
    from pds.strategy.plan import clean_goal
    assert clean_goal("성수동 상권 변화를 월 단위로 추적하고 싶다").startswith("성수동 상권")
    assert "싶" not in clean_goal("가맹본부 확인하고 싶어")


def test_validate_rejects_undeclared_join():
    from pds.strategy.plan import ProtocolError, validate
    bad = {"datasets": [], "joins": [{"edge": "e-9999", "left": "1", "right": "2"}], "unverified_leads": [], "candidates": []}
    with pytest.raises(ProtocolError):
        validate(bad)
    with pytest.raises(ProtocolError):
        validate({"datasets": [], "joins": [], "candidates": [], "unverified_leads": [{"tier": "verified"}]})


@needs_catalog
def test_plan_follows_protocol_rules():
    from pds.service import index
    from pds.strategy.plan import plan
    p = plan("아파트 실거래가와 공시지가 비교", use_llm=False)
    ix = index.get()
    edge_ids = {e["id"] for e in ix.edges}
    assert p["datasets"] and all(d["tier"] == "verified" for d in p["datasets"])
    assert all(j["edge"] in edge_ids for j in p["joins"])
    assert len(p["unverified_leads"]) <= 10 and all(x["tier"] == "catalog" for x in p["unverified_leads"])
    assert "def fetch" in p["code"]


@needs_catalog
def test_api_endpoints():
    from fastapi.testclient import TestClient
    from pds.service.app import app
    c = TestClient(app)
    s = c.get("/api/stats").json()
    assert s["datasets"]["verified"] > 200 and s["code_lists"] > 100
    assert c.get("/api/codes/land_category", params={"q": "대"}).json()["values"]
    assert c.get("/api/search", params={"q": "응급실"}).json()[0]["id"] == "15000563"
    p = c.post("/api/plan", json={"goal": "지금 가까운 응급실 병상", "use_llm": False}).json()
    assert p["datasets"][0]["id"] == "15000563"


def test_goal_regions():
    from pds.strategy.region import goal_regions
    assert goal_regions("성수동 상권 변화를 월 단위로 추적하고 싶어")["sido"] == {"서울특별시"}
    assert goal_regions("부산 해운대구 카페")["sido"] == {"부산광역시"}
    assert goal_regions("지금 가까운 응급실과 병상 현황")["sido"] == set()


@needs_catalog
def test_plan_excludes_other_region():
    from pds.strategy.plan import exclude, plan
    p = plan("성수동 상권 변화를 월 단위로 추적하고 싶어", use_llm=False)
    assert "15095253" not in {d["id"] for d in p["datasets"]}  # 부산 점포이력
    assert any(x["id"] == "15095253" and x["kind"] == "region" for x in p["not_recommended"])
    assert len({d["id"] for d in p["datasets"]}) == len(p["datasets"])
    gone = p["datasets"][1]["id"]
    q = exclude(p, gone, "테스트")
    assert gone not in {d["id"] for d in q["datasets"]} and all(gone not in (j["left"], j["right"]) for j in q["joins"])
