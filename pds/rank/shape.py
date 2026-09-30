"""데이터의 '모양' 판정: 입도(건별 원천 vs 집계), 전수성, 연계 키.

2026-09-28 구름 결정: 통계·집계보다 건별 원천(최소 단위) 데이터를, 전수가 나오는 데이터를, 다른 데이터와 붙일 키가 있는
데이터를 높게 친다. 모든 분야 공통. 메타(출력 컬럼명·제목·설명)만으로 판정하므로 Phase 2 실측으로 교정한다.
"""
from __future__ import annotations

import re

# 응답 껍데기 — 판단에서 뺀다
_ENVELOPE = re.compile(
    r"^(결과\s*코드|결과\s*메[세시]지|resultCode|resultMsg|item|items|header|body|head|row|RESULT|"
    r"페이지\s*번호|페이지\s*수|한\s*페이지\s*결과\s*수|전체\s*결과\s*수|데이터\s*총\s*개수|totalCount|numOfRows|pageNo|"
    r"연번|순번|번호|No|NO|비고|데이터\s*기준\s*일자?|기준\s*일자|데이터갱신구분|조회수)$")

# 건별 원천의 단서
_RECORD_NAME = re.compile(
    r"(시설|업소|업체|사업장|학교|의료기관|병원|약국|건물|단지|(?<!지)역|정류소|정류장|회사|공고|계약|사업|과제|제품|상품|품|선박|차량|기업집단|브랜드|가맹본부|"
    r"법인|단체|상|점포|매장|주차장|공원|도서관|어린이집|유치원|센터|기관)\s*명(칭)?$|^상호(명)?$|^명칭$|^제목$|^(성명|이름)$")
_RECORD_ID = re.compile(
    r"(관리|등록|일련|고유|허가|인허가|신고|사업자등록|법인등록|공고|계약|접수|요청|발급|인증|지정)\s*번호$|"
    r"(ID|Id|아이디|식별자|식별번호)$|^PNU$|(기업집단|브랜드|가맹본부|업체|회사|사업장|시설)\s*(코드|관리번호)$")
_LOCATION = re.compile(r"주소|소재지|위도|경도|좌표|WGS84|GRS80")
_RECORD_DATE = re.compile(r"(인허가|허가|지정|설치|계약|체결|등록|신고|개업|폐업|착공|준공|사용승인|거래|접수|발생|공고|개찰)\s*(일자|일시|일)$")

# 집계의 단서
_MEASURE = re.compile(
    r"(건수|개수|인원|명수|합계|총계|소계|누계|평균|비율|비중|점유율|증감|증감률|지수|현황수|실적|금액합계|총액)$|"
    r"^(계|합계|소계|총계)$|\((명|건|개|개소|천원|백만원|억원|%|천명|천건)\)$|(수|율|률)\s*\(.*\)$")
_DIMENSION = re.compile(r"^(연도|년도|기준\s*연도|기준\s*년도|연|월|분기|구분|성별|연령|연령대|시도|시도명|시군구|시군구명|지역|지역명|시군|시군명)$")
_AGG_TITLE = re.compile(
    r"통계|집계|실적|추이|지표|지수|분포|총괄|"
    r"(연도|년도|연|월|분기|일|시도|시군구|지역|기관|업종|연령|성|품목|유형|항목|국가|국적|규모|계층|원인|계약방법|기업구분|업무대상)별")

# 전수성
_LOOKUP_ONLY = re.compile(r"진위|확인\s*서비스|검증\s*서비스|계약과정통합")
_PARTIAL = re.compile(r"샘플|표본|예시\s*데이터|시범|일부\s*(데이터|자료|지역)")
_FULL = re.compile(r"전국|전체|목록|표준데이터|통합")

# 연계 키: (이름, 패턴, 가중)
_KEYS = [
    ("사업자번호", re.compile(r"사업자\s*(등록)?\s*번호|법인\s*등록\s*번호|bizno", re.I), 0.4),
    ("행정구역코드", re.compile(r"(법정동|행정동|행정구역|시군구|시도|자치단체|행정표준|지역)\s*코드|법정동\s*번호|LAWD_CD", re.I), 0.4),
    ("PNU", re.compile(r"PNU|필지\s*고유\s*번호|토지\s*고유\s*번호|^고유\s*번호$"), 0.4),
    ("건물·도로명키", re.compile(r"건물\s*관리\s*번호|도로명\s*코드|도로명주소\s*관리\s*번호|건축물\s*대장"), 0.4),
    ("기관코드", re.compile(r"기관\s*코드"), 0.3),
    ("표준분류코드", re.compile(r"(물품\s*분류|세부\s*품명|품목|표준\s*산업\s*분류|업종|질병|상병|KCD|HS)\s*(코드|번호)"), 0.3),
    ("학교코드", re.compile(r"(학교|대학)\s*(코드|ID|번호)|학교ID|SD_SCHUL_CODE"), 0.3),
    ("교통노드코드", re.compile(r"(역|정류장|정류소|노선|호선)\s*(코드|번호|ID|아이디)|STATION_CD|stationId|STN_CD", re.I), 0.3),
    ("업무식별번호", re.compile(r"(공고|계약|허가|인허가|신고|관리|접수|등록)\s*번호"), 0.2),
    ("개체코드", re.compile(r"(기업집단|브랜드|가맹본부|선거구|투표구|정당|후보자?|선거)\s*(코드|ID|관리번호)|^sgId$|^huboid$", re.I), 0.2),
    ("주소", re.compile(r"주소|소재지"), 0.2),
    ("좌표", re.compile(r"위도|경도|좌표"), 0.2),
    ("우편번호", re.compile(r"우편\s*번호"), 0.1),
]


# "주소"지만 물리적 주소가 아닌 것 (URL·메일·홈페이지·IP) — 연계 키로 치지 않는다
_WEB_ADDR = re.compile(r"URL|url|Url|메일|이메일|홈페이지|웹|사이트|IP|아이피|링크|도메인")


def _tokens(*texts) -> list[str]:
    out = []
    for t in texts:
        if isinstance(t, str):
            out += [x.strip() for x in t.split(",") if x.strip()]
    return [t for t in out if not _ENVELOPE.match(t)]


def granularity(title, output_cols, keywords=None) -> tuple[float, str]:
    """1.0 건별 원천 · 0.5 판단 불가 · 0.1~0.3 집계. (점수, 근거)"""
    cols = _tokens(output_cols)
    agg_title = bool(_AGG_TITLE.search(title or ""))
    if cols:
        rec = [t for t in cols if _RECORD_NAME.search(t) or _RECORD_ID.search(t) or _LOCATION.search(t)]
        rec_date = any(_RECORD_DATE.search(t) for t in cols)
        meas = [t for t in cols if _MEASURE.search(t)]
        dims = [t for t in cols if _DIMENSION.match(t)]
        share = len(meas) / len(cols)
        if rec and not (agg_title and share >= 0.3):
            return (1.0 if (len(rec) >= 2 or rec_date) else 0.85), f"record:{rec[0]}"
        if share >= 0.3 or (dims and len(meas) >= 2 and not rec):
            return 0.1, f"measure {len(meas)}/{len(cols)}"
        if agg_title:
            return 0.3, "title-agg"
        return 0.5, "cols-unclear"
    if agg_title:
        return 0.25, "title-agg(no-cols)"
    return 0.5, "no-cols"


def coverage(title, description, kind, row_count) -> tuple[float, str]:
    """1.0 전수 · 0.8 기본 · 0.3 표본·일부 또는 번호를 알아야만 조회."""
    text = f"{title or ''} {description or ''}"
    if kind in ("REST", "SOAP", "API_LINK") and _LOOKUP_ONLY.search(title or ""):
        return 0.3, "lookup-only"
    if _PARTIAL.search(text):
        return 0.3, "partial"
    if _FULL.search(title or "") or (isinstance(row_count, (int, float)) and row_count == row_count and row_count >= 1000):
        return 1.0, "full"
    return 0.8, "default"


def linkable(title, output_cols, request_vars=None) -> tuple[float, str]:
    """연계 키 종류 합(가중) → 0~1. 컬럼이 없으면 제목만 본다."""
    cols = _tokens(output_cols, request_vars)
    found = []
    for name, pat, w in _KEYS:
        toks = [t for t in cols if not _WEB_ADDR.search(t)] if name == "주소" else cols
        if any(pat.search(t) for t in toks) or (not cols and name != "주소" and pat.search(title or "")):
            found.append((name, w))
    score = min(1.0, sum(w for _, w in found))
    return round(score, 3), ",".join(n for n, _ in found) or "none"
