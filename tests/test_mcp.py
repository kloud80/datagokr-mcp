"""MCP 도구 (pds/mcp/server.py) · 전략의 정직성 규칙 (조인 분리 집계·단위 불일치·요약 문장·신뢰도) — LLM 없이."""
import json

import pytest

from pds import config

needs_catalog = pytest.mark.skipif(not (config.PROCESSED / "catalog.parquet").exists(), reason="카탈로그 없음 (python -m pds build)")


def test_join_counts_split_hub():
    from pds.strategy.plan import join_counts
    joins = [{"left": "A", "right": "15123287"}, {"left": "B", "right": "15123899"}, {"left": "A", "right": "B"}]
    assert join_counts(joins) == {"dataset_to_dataset": 1, "via_hub": 2}


def test_summary_rule_no_template_on_empty():
    from pds.strategy.plan import _summary_rule
    s = _summary_rule({"datasets": [], "joins": [], "gaps": ["x"], "unverified_leads": [{}, {}], "candidates": []})
    assert "0개" not in s and "찾지 못했다" in s and "미검증 단서 2개" in s
    one = {"datasets": [{}], "joins": [{"left": "A", "right": "15123287"}], "gaps": [], "context": None}
    assert "직접 잇는 조인은 없고 코드표·지적도로 정규화하는 연결 1개" in _summary_rule(one)
    none = {"datasets": [{}, {}], "joins": [], "gaps": [], "context": None}
    assert _summary_rule(none).count("없다") == 1


def test_confidence_discriminates():
    from pds.strategy.plan import _confidence
    ds = [{}] * 4
    direct = [{"left": "A", "right": "B", "match_rate": 0.9, "confidence": None}]
    hub = [{"left": "A", "right": "15123287", "match_rate": 0.9, "confidence": None}]
    good = _confidence(ds, direct, {}, [], "ctx")
    only_hub = _confidence(ds, hub, {}, [], "ctx")
    gappy = _confidence(ds, direct, {}, ["a", "b"], "ctx")
    assert good > only_hub and good > gappy
    assert _confidence([], [], {}, [], None) == 0.0


@needs_catalog
def test_unit_gap_month_vs_quarter():
    from pds.service import index
    from pds.strategy.plan import unit_gaps
    ix = index.get()
    q = next(d for d in ix.datasets.values() if d["tier"] == "verified" and (d.get("grain") or {}).get("time") == "quarter")
    assert unit_gaps("월 단위로 보고 싶다", [{"id": q["id"], "title": q["title"]}])
    assert not unit_gaps("분기별 추이", [{"id": q["id"], "title": q["title"]}])
    assert not unit_gaps("추이를 보고 싶다", [{"id": q["id"], "title": q["title"]}])


@needs_catalog
def test_readme_example_seongsu_is_honest():
    """README 첫 예시 — 요약 문장이 join_counts·gaps와 같은 말을 하고, 월 단위 요청에 거친 데이터면 공백으로 밝힌다."""
    from pds.service import index
    from pds.strategy.plan import TIME_ORDER, plan
    p = plan("성수동 상권 변화를 월 단위로 추적하고 싶다", use_llm=False)
    jc = p["join_counts"]
    assert jc["dataset_to_dataset"] + jc["via_hub"] == len(p["joins"])
    assert (f"직접 조인 {jc['dataset_to_dataset']}개" in p["summary"]) == bool(jc["dataset_to_dataset"])
    ix = index.get()
    coarse = [d for d in p["datasets"] if ((ix.datasets[d["id"]].get("grain") or {}).get("time") in TIME_ORDER[3:])]
    assert all(any(d["id"] in g for g in p["gaps"]) for d in coarse)
    assert p["knowledge_version"]


# ─────────────────────────── MCP 도구

@needs_catalog
def test_mcp_get_dataset_exposes_measurements():
    from pds.mcp.server import get_dataset
    d = json.loads(get_dataset(id="15154916", max_fields=5))
    assert d["verification"]["rows"] and d["verification"]["probed_at"]
    assert d["fields_total"] >= len(d["fields"]) == 5
    assert any("null_rate" in f for f in d["fields"]) and any("samples" in f for f in d["fields"])


@needs_catalog
def test_mcp_errors_are_errors():
    from mcp.server.mcpserver.exceptions import ToolError

    from pds.mcp.server import get_dataset, lookup_code, plan_public_data_strategy
    with pytest.raises(ToolError):
        get_dataset(id="nope")
    with pytest.raises(ToolError):
        lookup_code(code_list="zzz", q="a")
    with pytest.raises(ToolError):
        plan_public_data_strategy(goal="  ")


@needs_catalog
def test_mcp_search_filters():
    from pds.mcp.server import search_datasets
    res = json.loads(search_datasets(query="음식점", limit=15, scope="national"))
    assert res and len(res) <= 15 and all(r["region"] == "전국" for r in res)
    loc = json.loads(search_datasets(query="음식점", limit=5, scope="regional"))
    assert all(r["region"] != "전국" for r in loc)
    cat = json.loads(search_datasets(query="음식점", tier="catalog", limit=3))
    assert all(r["tier"] == "catalog" and r.get("fields") != "nan" for r in cat)


@needs_catalog
def test_mcp_plan_summary_is_small():
    from pds.mcp.server import plan_public_data_strategy
    s = plan_public_data_strategy(goal="지금 가까운 응급실 병상")
    full = plan_public_data_strategy(goal="지금 가까운 응급실 병상", detail="full")
    assert len(s) < len(full) and "code" not in json.loads(s) and "code" in json.loads(full)
    assert "code" in json.loads(plan_public_data_strategy(goal="지금 가까운 응급실 병상", include_code=True))


def test_ratelimit():
    import os

    from pds.service import ratelimit
    os.environ["PDS_RATE_PER_HOUR"] = "2"
    try:
        assert ratelimit.check("t-ip") is None and ratelimit.check("t-ip") is None
        assert ratelimit.check("t-ip") and ratelimit.check("other-ip") is None
    finally:
        del os.environ["PDS_RATE_PER_HOUR"]
