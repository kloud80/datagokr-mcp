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


# ─────────────────────────── 2차 리뷰 (2026-10-10)
def test_grounded_excludes_portal_meta():
    from pds.mcp import server
    from pds.schema import GROUNDED
    assert server.GROUNDED is GROUNDED and "portal_meta" not in GROUNDED


@needs_catalog
def test_mcp_claims_portal_meta_not_grounded():
    from pds.mcp.server import get_dataset
    from pds.service import index
    ix = index.get()
    did = next(i for i, d in ix.datasets.items()
               if any(c["evidence"] and all(e["type"] == "portal_meta" for e in c["evidence"]) for c in d.get("claims") or []))
    d = json.loads(get_dataset(id=did, max_fields=1))
    raw = {c["value"][:240]: c for c in ix.datasets[did]["claims"]}
    for c in d["claims"]:
        src = raw[c["value"]]
        if all(e["type"] == "portal_meta" for e in src["evidence"]):
            assert c["grounded"] is False


def test_tools_return_text_only():
    """문자열 응답이 structuredContent로 한 번 더 실리지 않게."""
    import asyncio

    from pds.mcp.server import server
    tools = asyncio.run(server.list_tools())
    assert all(not getattr(t, "output_schema", None) and not getattr(t, "outputSchema", None) for t in tools)


def test_forwarded_for_not_trusted_by_default():
    from pds.service import app
    assert app._client_ip("1.2.3.4", "9.9.9.9") == "9.9.9.9"
    app.TRUST_PROXY = True
    try:
        assert app._client_ip("6.6.6.6, 1.2.3.4", "10.0.0.1") == "1.2.3.4"
    finally:
        app.TRUST_PROXY = False


@needs_catalog
def test_search_national_first_without_region():
    from pds.mcp.server import search_datasets
    res = json.loads(search_datasets(query="일반음식점 인허가", limit=10))
    regions = [r["region"] for r in res]
    assert regions[0] == "전국" and regions == sorted(regions, key=lambda x: x != "전국")
    loc = json.loads(search_datasets(query="경기도 일반음식점", limit=5))
    assert any(r["region"] == "경기도" for r in loc)


@needs_catalog
def test_exclude_recomputes_gaps_and_confidence():
    from pds.strategy.plan import exclude, plan
    p = plan("성수동 상권 변화를 월 단위로 추적하고 싶다", use_llm=False)
    unit = [g for g in p["gaps"] if g.startswith("단위 불일치")]
    if not unit:
        pytest.skip("단위 불일치 공백 없음")
    dsid = unit[0].rsplit("(", 1)[1].split(")")[0]
    q = exclude(json.loads(json.dumps(p)), dsid, "테스트")
    assert not any(f"({dsid})" in g for g in q["gaps"])
    assert q["confidence"] != p["confidence"] or len(q["gaps"]) < len(p["gaps"])


def test_heads_cache_key_stable(tmp_path, monkeypatch):
    from pds.strategy import multihead
    region = {"names": ["성수동"], "sido": {"서울특별시"}}
    a = multihead._cache_file("성수동  상권 변화", region, ["1", "2"])
    b = multihead._cache_file("성수동 상권 변화", region, ["1", "2"])
    c = multihead._cache_file("성수동 상권 추이", region, ["1", "2"])
    assert a == b and a != c
    monkeypatch.setattr(multihead, "CACHE", tmp_path)
    calls = []
    monkeypatch.setattr(multihead, "_run", lambda *a, **k: calls.append(1) or {"heads": [{"name": "x"}], "links": []})
    assert multihead.run("목표", region) == multihead.run("목표", region) and len(calls) == 1


# ─────────────────────────── 키 규약 (2026-10-10)
def test_credentials_env_sample():
    from pds.strategy.signup import credentials, env_name
    p = {"datasets": [{"id": "A", "access": {"channel": "portal", "scheme": "apiKey:query:serviceKey"}},
                      {"id": "B", "access": {"channel": "portal", "scheme": "file"}},
                      {"id": "C", "access": {"channel": "external", "signup": {"required": True, "site": "서울", "host": "data.seoul.go.kr", "how": "가입"}}}],
         "joins": [{"on": {"transform": "R-12"}}]}
    c = credentials(p)
    assert c["required"] and c["agent_protocol"]
    assert {e["name"]: e["datasets"] for e in c["env"]} == {"DATA_GO_KR_SERVICE_KEY": ["A"], "DATA_SEOUL_API_KEY": ["C"], "VWORLD_API_KEY": []}
    assert "DATA_GO_KR_SERVICE_KEY=\n" in c["env_sample"] and "VWORLD_DOMAIN=" in c["env_sample"]
    assert credentials({"datasets": [p["datasets"][1]], "joins": []}) == {"required": False, "env": [], "env_sample": "", "agent_protocol": []}
    assert env_name("apihub.kma.go.kr") == "APIHUB_KMA_GO_KR_API_KEY"


def test_mcp_instructions_mention_key_protocol():
    from pds.mcp.server import plan_with_public_data, server
    assert "credentials" in server.instructions and ".env" in server.instructions
    assert "env_sample" in plan_with_public_data("x")
