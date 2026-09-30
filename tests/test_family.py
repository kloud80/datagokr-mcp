import pytest

from pds.knowledge.family import FAMILIES, check, load


@pytest.mark.parametrize("slug", [p.name for p in FAMILIES.iterdir() if (p / "family.yaml").exists()])
def test_family_valid(slug):
    assert check(slug) == []


def test_pps_hub_reaches_all_stage_keys():
    fam = load("pps-procurement")
    hub = next(d for d in fam["datasets"] if d["role"] == "hub")
    # 허브는 입찰·사전규격·발주계획·조달요청 번호 어느 것으로도 조회 가능해야 한다
    assert {"bid_ntce_no", "bf_spec_rgst_no", "order_plan_no", "prcrmnt_req_no"} <= set(hub["lookup_by"])
