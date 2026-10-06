"""변환 규칙 (KNOWLEDGE-SPEC §9-2)."""
import pandas as pd
import yaml

from pds import config
from pds.rules import RULES, pnu_from_parts, pnu_from_rtms, road_key, sgg_from_bjd


def test_pnu_assembly():
    assert pnu_from_parts("1111010100", "1", "0001", "0000") == "1111010100100010000"
    assert pnu_from_parts("1111010100", 2, 12, 3) == "1111010100200120003"
    assert pnu_from_parts("111101010", "1", 1, 0) is None      # 법정동코드 자릿수
    assert pnu_from_parts("1111010100", "1", 0, 0) is None      # 본번 0은 없음


def test_pnu_from_rtms_row():
    df = pd.DataFrame({"sggCd": ["11110"], "umdCd": ["18700"], "landCd": ["1"], "bonbun": ["0088"], "bubun": ["0000"]})
    assert pnu_from_rtms(df).iloc[0] == "1111018700100880000"


def test_sgg_and_road_key():
    assert sgg_from_bjd("1111010100") == "11110" and sgg_from_bjd("abc") is None
    assert road_key("서울특별시 송파구 송이로 42 (가락동)") == "송이로42"
    assert road_key("전남광주통합특별시 북구 우치로 100-1") == "우치로100-1"


def test_rules_catalog_matches_code():
    cat = yaml.safe_load((config.KNOWLEDGE / "rules.yaml").read_text(encoding="utf-8"))
    assert {r["id"] for r in cat} == set(RULES)


def test_admin_name_to_code():
    import pytest
    from pds import config
    from pds.rules import admin_name_to_code
    if not (config.KNOWLEDGE / "codes" / "bjd_cd.parquet").exists():
        pytest.skip("법정동 코드표 없음")
    assert admin_name_to_code("종로구", "서울특별시") == "11110"
    assert admin_name_to_code("중구") is None            # 모호
    assert admin_name_to_code("수원시 장안구") == "41111"


def test_loose_join_rules():
    """R-20~R-23 — 느슨한 조인: 행정구역 앞자리 묶기, 시점 내림, 분류 앞자리."""
    from pds.rules import admin_rollup, category_prefix, time_floor
    assert admin_rollup("1111010100100010000", "bjd") == "1111010100"   # PNU → 법정동
    assert admin_rollup("1111010100", "sgg") == "11110"
    assert admin_rollup("111", "sgg") is None
    assert time_floor("20240815", "month") == "202408"
    assert time_floor("2024-08-15", "quarter") == "2024Q3"
    assert time_floor("20243", "quarter") == "2024Q3"                   # 서울 연도+분기 코드
    assert time_floor("20243", "year") == "2024"
    assert category_prefix("G47121", 3) == "G47"


def test_align_pair_and_grain():
    from pds.dossier.gen_dataset import _grain
    from pds.strategy.plan import align_pair
    seoul = _grain([{"name": "STDR_YYQU_CD"}, {"name": "ADSTRD_CD"}, {"name": "SVC_INDUTY_CD"}])
    assert seoul["space"] == "emd" and seoul["space_via"] == "code" and seoul["time"] == "quarter"
    assert seoul["category"] == ["seoul_svc"]                            # 서울 서비스업종은 KSIC가 아니다
    shop = {"space": "point", "space_via": "coord", "time": "day", "category": ["ksic"]}
    al = align_pair(seoul, shop)
    assert al["space"] == "emd" and al["time"] == "quarter" and "category" not in al
    assert "R-12" in al["rules"] and "R-22" in al["rules"]
    assert align_pair({"time": "month"}, {"time": "day"}) is None        # 시간만 맞는 쌍은 너무 느슨하다
    assert align_pair({"time": "month", "category": ["ksic"]}, {"time": "day", "category": ["ksic"]})["category"] == "ksic"
