import pytest

from pds import config
from pds.rank import report


def test_template_has_placeholder():
    assert "__PAYLOAD_B64__" in report.TEMPLATE.read_text(encoding="utf-8")


@pytest.mark.skipif(not (config.PROCESSED / "score.parquet").exists(), reason="build 산출물 없음")
def test_payload_shapes():
    df = report._load()
    sample = df.sort_values("rank_overall").head(500)
    p = report.build_payload(sample)
    n = len(sample)
    assert all(len(v) == n for v in p["cols"].values())
    assert set(p["dict"]["kind"]) >= {"REST", "API_LINK"}
    # API는 전부 상세가 있어야 한다
    api_ids = sample.loc[~sample["api_kind_label"].isin(["FILE", "FILE_LINK"]), "id"]
    assert set(api_ids) <= set(p["detail"])
