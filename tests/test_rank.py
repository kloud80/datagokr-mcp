from datetime import date

import pandas as pd
import pytest

from pds.ingest.load import parse_approval, parse_traffic
from pds.rank.classify import admin_unit, agency_tier
from pds.rank.score import api_kind, designation, freshness, meta_fill, usage_scores


@pytest.mark.parametrize("code,name,tier", [
    ("1170000", "법제처", "중앙행정기관"),
    ("6110000", "서울특별시", "광역자치단체"),
    ("6520000", "제주특별자치도 서귀포시", "기초자치단체"),
    ("3780000", "경기도 성남시", "기초자치단체"),
    ("5870000", "전남광주통합특별시", "광역자치단체"),
    ("7430000", "인천광역시교육청", "교육청"),
    ("B551182", "건강보험심사평가원", "공공기관"),
    ("9760000", "중앙선거관리위원회", "중앙행정기관"),
])
def test_agency_tier(code, name, tier):
    assert agency_tier(code, name) == tier


def test_admin_unit_token_not_substring():
    # '페이지번호'에 '지번'이 들어 있지만 필지로 분류되면 안 된다
    unit, _, _ = admin_unit("특일 정보", "페이지번호,날짜,휴일여부", None, None)
    assert unit == "전국·비공간"


def test_admin_unit_address_is_point_not_parcel():
    unit, conf, ev = admin_unit("업소 현황", "업소명,소재지지번주소,전화번호", None, None)
    assert (unit, conf) == ("개별(주소·좌표)", "high")


def test_admin_unit_parcel():
    assert admin_unit("아파트 매매", "거래금액,단지명,법정동", None, None)[0] == "필지·건물"


def test_admin_unit_title_fallback():
    unit, conf, _ = admin_unit("시도별 인구", None, None, None)
    assert (unit, conf) == ("시도", "medium")


def test_admin_unit_unknown_is_low():
    assert admin_unit("환율 정보", None, None, None) == ("전국·비공간", "low", "no-columns")


def test_parsers():
    assert parse_traffic("개발계정 : 10000/ 운영계정 : 활용사례 등록시 신청") == 10000
    assert parse_traffic(None) is None
    assert parse_approval("개발단계 : 자동승인 / 운영단계 : 심의승인") == ("auto", "review")


def test_api_kind():
    assert api_kind("API", "REST", None) == "REST"
    assert api_kind("API", "LINK", None) == "API_LINK"
    from pds.rank.score import API_KIND_SCORE
    assert API_KIND_SCORE["API_LINK"] == API_KIND_SCORE["REST"]  # 외부 링크는 깎지 않는다
    assert api_kind("FILE", None, "기관자체에서 다운로드(제공데이터URL기재)") == "FILE_LINK"
    assert api_kind("STD", None, None) == "STD"


def test_designation_order():
    assert designation(True, True, True) == 1.0
    assert designation(False, True, True) == 0.8
    assert designation(False, True, False) == 0.6
    assert designation(False, False, False) == 0.0


def test_freshness():
    snap = date(2026, 7, 31)
    assert freshness(date(2026, 7, 1), "월간", None, snap) == 1.0
    assert freshness(date(2024, 1, 1), "월간", None, snap) == 0.0
    assert freshness(date(2025, 7, 31), "수시", None, snap) == pytest.approx(0.5, abs=0.01)
    # 차기 등록 예정일을 넘긴 경우 반감
    assert freshness(date(2026, 7, 1), "월간", date(2026, 5, 1), snap) == 0.5
    assert freshness(pd.NaT, "월간", None, snap) == 0.0


def test_meta_fill_request_vars_only_for_api():
    assert meta_fill("FILE", None, "a,b", "법", "한계") == 1.0
    assert meta_fill("REST", None, "a,b", "법", "한계") == 0.75


def test_usage_normalized_within_kind():
    usage = pd.Series([0, 10, 1000, 0, 5])
    views = pd.Series([0, 0, 0, 0, 5])
    kind = pd.Series(["REST", "REST", "REST", "FILE", "FILE"])
    s = usage_scores(usage, views, kind)
    assert s.between(0, 1).all()
    assert s[2] == 1.0 and s[0] < s[1] < s[2]
    assert s[4] == 1.0  # FILE 그룹 안에서 최댓값 (그룹끼리 섞지 않는다)


def test_weighted_mean_skips_not_applicable():
    from pds.rank.score import WEIGHTS, weighted_mean
    df = pd.DataFrame({f"s_{k}": [1.0, 1.0] for k in WEIGHTS})
    df.loc[0, ["s_freshness", "s_meta_fill"]] = 0.0
    df.loc[1, ["s_freshness", "s_meta_fill"]] = float("nan")
    s = weighted_mean(df)
    assert s[0] == pytest.approx(1 - WEIGHTS["freshness"] - WEIGHTS["meta_fill"])
    assert s[1] == pytest.approx(1.0)  # 판단 불가(NaN) 항목은 빼고 재정규화


def test_shape_rules():
    from pds.rank.shape import coverage, granularity, linkable
    assert granularity("조달청_나라장터 계약정보서비스", "통합계약번호,계약명,계약기관명,계약체결일자,총계약금액")[0] == 1.0
    assert granularity("조달청_공공조달통계정보서비스", "연계시스템명,실적합계건수,실적합계금액,일반경쟁실적건수,일반경쟁실적금액")[0] <= 0.3
    assert granularity("시도별 인구 통계", None)[0] <= 0.3
    assert coverage("국세청_사업자등록정보 진위확인 및 상태조회 서비스", "", "REST", None)[0] == 0.3
    assert linkable("x", "사업자등록번호,법정동코드,주소")[0] == 1.0
    assert linkable("x", "페이지번호,결과코드")[0] == 0.0  # 응답 껍데기는 키가 아니다
