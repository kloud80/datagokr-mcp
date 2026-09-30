import pandas as pd
import pytest

from pds import config
from pds.knowledge.compile import build, chunk
from pds.rank.exclude import assign_subsector, load_subsectors

needs_build = pytest.mark.skipif(not (config.PROCESSED / "score.parquet").exists(), reason="build 산출물 없음")


def test_chunk_overlap_and_limit():
    text = "가" * 2000
    parts = chunk(text)
    assert all(len(p) <= 800 for p in parts) and len(parts) >= 3
    assert chunk("짧다") == ["짧다"]


def test_subsector_assignment_first_match_and_default():
    defs = load_subsectors()
    df = pd.DataFrame({"id": ["1", "2", "3"], "sector": ["공공행정 - 국정운영"] * 3,
                       "agency_name": ["중앙선거관리위원회", "부산광역시 기장군", "강원특별자치도 삼척시"],
                       "title": ["중앙선거관리위원회_투표소 정보", "부산광역시 기장군_의회 조례", "삼척시_주정차신고정보"]})
    out = assign_subsector(df, defs)
    assert out["subsector"].tolist() == ["election", "local-council", "misc"]
    assert out.loc[0, "cycle_override"] == "event"


@needs_build
def test_graph_integrity():
    kg = build()
    nodes = set(kg["nodes"]["node_id"])
    e = kg["edges"]
    assert set(e["src"]) <= nodes and set(e["dst"]) <= nodes          # 끊어진 엣지 없음
    assert kg["docs"]["doc_id"].is_unique and kg["chunks"]["chunk_id"].is_unique
    assert set(kg["docs"]["node_id"]) <= nodes
    # 결정·공백·전역 키가 설명과 함께 들어 있다
    kinds = set(kg["docs"]["kind"])
    assert {"decision_reason", "gap_note", "key_note", "sector_doc", "family_doc"} <= kinds
    # 패밀리 키가 전역 키로 이어진다
    same = e[e["type"] == "same_as"]
    assert ("fkey:pps-procurement/bizno", "key:bizno") in set(zip(same["src"], same["dst"]))


@needs_build
def test_sector_tree_points_to_real_sectors():
    """sector_tree.yaml의 부문 이름이 실제 부문과 일치하고(오타 방지), domain 계층이 field까지 이어진다."""
    import yaml
    tree = yaml.safe_load((config.KNOWLEDGE / "sectors" / "sector_tree.yaml").read_text(encoding="utf-8"))
    ids = {d["id"] for d in tree}
    real = set(pd.read_parquet(config.PROCESSED / "class.parquet")["sector"])
    for d in tree:
        assert d.get("parent") is None or d["parent"] in ids
        for s in d.get("sectors", []) + d.get("related", []):
            assert s in real, s
    kg = build()
    e = kg["edges"]
    assert (e["type"] == "in_domain").sum() == sum(len(d.get("sectors", [])) for d in tree)
    assert set(e.loc[e["type"] == "domain_of", "src"]) == {f"domain:{i}" for i in ids}


def test_contexts_point_to_defined_subsectors():
    """contexts/ 멤버가 subsectors.yaml에 정의된 부문·세부 부문을 가리키고(오타 방지), 차원이 정해진 값이다 — pds validate가 검사."""
    from pds.schema.validate import run
    rep, objs = run()
    assert len(objs["context"]) >= 41
    assert not [e for e in rep.errors if e.startswith("contexts/")], rep.errors
