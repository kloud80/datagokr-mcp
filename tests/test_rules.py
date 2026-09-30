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
