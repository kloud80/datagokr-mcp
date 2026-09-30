import pandas as pd

from pds.rank.exclude import excluded_by, load_rules


def test_keep_overrides_match():
    rules = [{"id": "r1", "match": {"sector": "공공행정 - 정부조달"}, "keep": {"agency_name": ["조달청"]}}]
    df = pd.DataFrame({"sector": ["공공행정 - 정부조달", "공공행정 - 정부조달", "국토관리 - 주택"],
                       "agency_name": ["조달청", "대전광역시", "대전광역시"]})
    s = excluded_by(df, rules)
    assert s.isna().tolist() == [True, False, True] and s[1] == "r1"


def test_rules_file_loads():
    assert any(r["id"] == "gov-procurement-non-pps" for r in load_rules())


def test_ftc_rule_keeps_only_core_chains():
    rules = [r for r in load_rules() if r["id"] == "ftc-non-core"]
    df = pd.DataFrame({
        "sector": ["공공행정 - 공정거래", "공공행정 - 공정거래", "산업고용 - 산업·중소기업일반", "재정금융 - 산업금융", "공공행정 - 일반행정"],
        "agency_name": ["공정거래위원회", "전남광주통합특별시", "공정거래위원회", "공정거래위원회", "공정거래위원회"],
        "title": ["공정거래위원회_기업집단포털_지정된 대규모기업집단 조회 서비스", "전남광주통합특별시_착한가격업소 현황",
                  "공정거래위원회_가맹정보_브랜드 목록 정보 제공 서비스", "공정거래위원회_1372 소비자상담 지역별 접수통계 서비스",
                  "공정거래위원회_자동차 리콜정보"],
    })
    assert excluded_by(df, rules).notna().tolist() == [False, True, False, True, True]


def test_sector_remap():
    from pds.rank.exclude import load_sector_map, remap_sector
    df = pd.DataFrame({"sector": ["산업고용 - 산업·중소기업일반", "공공행정 - 일반행정"],
                       "agency_name": ["공정거래위원회", "조달청"], "title": ["a", "b"], "id": ["1", "2"]})
    sector, rule = remap_sector(df, load_sector_map())
    assert sector.tolist() == ["공공행정 - 공정거래", "공공행정 - 정부조달"]
