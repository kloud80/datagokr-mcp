"""Dataset 생성기·자동 claim (KNOWLEDGE-SPEC §7-2·§7-3)."""
import pytest

from pds import config
from pds.dossier.claims import review_for
from pds.dossier.gen_dataset import parse_legislation

needs_probe = pytest.mark.skipif(not (config.PROCESSED / "catalog.parquet").exists() or
                                 not (config.ROOT / "probe" / "runs" / "15125467.json").exists(), reason="Phase 2 산출물 없음")


def test_parse_legislation_keeps_only_statutes():
    got = parse_legislation("- 독립유공자예우에 관한 법률- 제대군인지원에 관한 법률제13조~제18조의3")
    assert [x["law"] for x in got] == ["독립유공자예우에 관한 법률", "제대군인지원에 관한 법률"]
    assert got[1]["articles"] == ["13", "18의3"]
    assert parse_legislation("항공사업법 제48조, 제75조")[0]["articles"] == ["48", "75"]
    assert parse_legislation("내부보고") == [] and parse_legislation(None) == []


@pytest.mark.parametrize("sector,heading", [
    ("문화관광 - 관광", "문화관광 - 관광"),          # 두 글자 영역이 '문화관광 - 체육'에 새지 않는다
    ("문화관광 - 체육", "문화관광 - 체육"),
    ("과학기술 - 과학기술연구", "과학기술"),         # 분야 전체 절로 대체
    ("교통물류 - 항공·공항", "2026-09-28 교통물류 - 항공·공항"),  # 굵은 머리말 없는 형식
    ("공공행정 - 공정거래", "공정거래"),             # 제목에 ' - '가 없는 절
])
def test_review_matching(sector, heading):
    hits = review_for(sector)
    assert hits and hits[0][0]["heading"] == heading


def test_review_no_false_match():
    assert review_for("사회복지 - 보육·가족및여성") == []  # 검토 절이 없으면 남의 결정을 붙이지 않는다


@needs_probe
def test_generate_preserves_human_fields(tmp_path, monkeypatch):
    from pds.dossier import gen_dataset
    from pds.schema import Dataset, store
    monkeypatch.setitem(store.PATHS, "dataset", tmp_path)
    rel, _ = gen_dataset.write("15125467")
    path = tmp_path / "공공행정" / "15125467.yaml"
    d = store.read(path)
    ids = [c["id"] for c in d["claims"]]
    assert ids[:4] == ["c-15125467-01", "c-15125467-02", "c-15125467-03", "c-15125467-04"]  # kind별 고정 슬롯
    d["summary_user"] = "사람이 쓴 요약"
    d["claims"].append({"id": "c-15125467-50", "kind": "pitfall", "value": "사람이 적은 함정",
                        "evidence": [{"type": "admin_review", "source": "대화", "by": "구름"}]})
    store.dump(d, path)
    gen_dataset.write("15125467")
    d2 = Dataset.model_validate(store.read(path))
    assert d2.summary_user == "사람이 쓴 요약"
    assert [c.id for c in d2.claims].count("c-15125467-50") == 1
    assert d2.gate_problems() == []  # 근거 있는 access·cadence·key
