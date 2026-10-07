"""실측 메타 적합도 (pds/strategy/fit.py) — 제목이 아니라 실측 필드·단위로 순위를 보정한다."""
from pds.strategy.fit import contrast_fit, meta_weight, term_fit, terms, time_asks, time_fit


def _d(fields, time=None, summary="", title=""):
    return {"title": title, "summary_user": summary, "grain": {"time": time} if time else {},
            "schema": {"fields": [{"name": f} for f in fields]}}


def test_terms_and_asks():
    assert terms("관광지 방문자 수 추이") == ["관광지", "방문자수"]
    assert "농도" in terms("측정소별 미세먼지 실시간 농도")          # '도'는 조사가 아니다
    assert time_asks("지하철역 시간대별 승하차 인원") == {"hour"}
    assert "realtime" in time_asks("측정소별 미세먼지 실시간 농도")


def test_time_fit_uses_measured_fields():
    q = "측정소별 미세먼지 실시간 농도"
    avg = _d(["MSRMT_DAY", "PM10_AVG_DNST", "O3_AVG_DNST"], time="day")
    assert time_fit(q, avg) < 1.0                                     # 제목이 '실시간'이어도 값이 일평균이면 내린다
    hourly = _d(["운행일자", "시간대구분", "승차인원수"], time="day")
    daily = _d(["운행일자", "정차역", "승차인원수"], time="day")
    assert time_fit("시간대별 승하차", hourly) > 1.0 > time_fit("시간대별 승하차", daily)
    assert time_fit("월 단위로 추적", _d(["기준년분기"], time="quarter")) < 1.0   # 요구보다 거친 집계
    assert time_fit("월 단위로 추적", _d(["거래일"], time="day")) > 1.0           # 내려서 맞출 수 있다 (R-22)


def test_term_fit_whole_word_beats_partial():
    q = "관광지 방문자 수 추이"
    visitors = _d(["시군구명", "방문자수"], summary="시군구별 관광 방문자수를 월별로 집계")
    hubs = _d(["중심 관광지명", "중심지 순위"], summary="다른 관광지와 연계 방문이 많은 중심 관광지 순위")
    assert term_fit(q, visitors) > term_fit(q, hubs)
    assert term_fit(q, _d([])) is None                                # 실측 메타가 없으면 판단하지 않는다


def test_contrast_and_pinned():
    assert contrast_fit("공공 입찰 공고와 낙찰", {"title": "조달청_누리장터 민간낙찰정보"}) < 1.0
    assert contrast_fit("공공 입찰 공고와 낙찰", {"title": "조달청_나라장터 낙찰정보"}) == 1.0
    weak = _d(["a", "b"], summary="국민연금 가입 사업장의 가입자 수와 신규·상실 인원을 매월 담는다")
    assert meta_weight("거래처 회사가 망할지 신호", weak) < 1.0
    assert meta_weight("거래처 회사가 망할지 신호", weak, pinned=True) == 1.0   # 맥락이 고른 신호 데이터는 내리지 않는다
