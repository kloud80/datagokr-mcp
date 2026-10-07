"""실측 메타 적합도 — 검색 관련도(제목·포털 설명 위주)를 우리가 직접 확인한 메타로 보정한다.

제목이 비슷해도 실측 필드·요약이 질문과 어긋나면 내린다(예: 제목은 '실시간'인데 필드는 일평균, '시간대별'을 묻는데 시간 열이 없음,
'방문자 수'를 묻는데 필드는 관광지 순위). 판단 근거는 모두 실측: schema.fields(이름·제목), grain(단위), summary_user(필드로 쓴 요약).

  meta_weight(goal, d) → 0.7 ~ 1.3 배율
    · 용어 적합: 질문의 대상어가 실측 필드·요약에 얼마나 있나 (제목·포털 설명은 보지 않는다)
    · 단위 요구: 실시간 · 시간대별 · 일별 · 월 단위 · 분기 · 연도별 — 실측 시간 단위·시간 열과 대조
    · 원천 우선: 개별 행(점포·거래·기관 1건) 데이터를 집계보다 조금 앞으로
"""
from __future__ import annotations

import re

STOP = {"데이터", "정보", "현황", "목록", "조회", "서비스", "자료", "공공데이터", "알수", "있을까", "있나", "찾기", "확인", "분석", "비교",
        "추적", "변화", "알고", "싶다", "싶어", "보고", "위해", "있는", "하는", "되는", "같이", "함께", "얼마나", "어떤", "무엇", "어디",
        "지역", "전국", "단위", "월", "일", "시간", "기준", "관련", "대한", "통해", "미리", "실시간", "추이"}
ASK_TIME = [(re.compile(r"실시간|지금|현재\s*(상태|농도|위치)|라이브"), "realtime"),
            (re.compile(r"시간대|시간별|시각별|출퇴근"), "hour"),
            (re.compile(r"일별|매일|하루|일\s*단위|일자별"), "day"),
            (re.compile(r"월\s*단위|월별|매월|달마다"), "month"),
            (re.compile(r"분기"), "quarter"),
            (re.compile(r"연도별|연간|해마다|연\s*단위"), "year"),
            (re.compile(r"추이|변화|추세|시계열"), "series")]
HOUR_FIELD = re.compile(r"(시간대|시간|시각|hour|_hh|tmzon|time|\d{1,2}\s*시|\d{2}~\d{2})", re.I)
AVG_FIELD = re.compile(r"(일평균|평균|avg|_mean)", re.I)
TIME_ORDER = ("realtime", "day", "month", "quarter", "year")


def _bigrams(s: str) -> set[str]:
    s = re.sub(r"[^0-9a-zA-Z가-힣]", "", s.lower())
    return {s[i:i + 2] for i in range(len(s) - 1)} or ({s} if s else set())


def terms(goal: str) -> list[str]:
    """질문의 대상어 — 두 글자 이상, 서술·일반어 제외. '방문자 수'처럼 붙여 쓰는 경우를 위해 '수'는 앞말에 붙인다."""
    g = re.sub(r"([가-힣]+)\s+수\b", r"\1수", goal)
    ws = re.findall(r"[0-9a-zA-Z가-힣]+", g)
    out = []
    for w in ws:
        s = re.sub(r"(으로|에서|에게|까지|부터|별로|별|과|와|을|를|이|가|은|는|의|로|에)$", "", w)
        w = s if len(s) >= 2 else w  # '농도'의 '도'처럼 조사가 아닌 끝 글자는 남긴다
        if len(w) >= 2 and w not in STOP:
            out.append(w)
    return list(dict.fromkeys(out))


def meta_text(d: dict) -> str:
    fs = (d.get("schema") or {}).get("fields") or []
    return " ".join([d.get("summary_user") or ""] + [f"{f.get('title') or ''} {f.get('name') or ''}" for f in fs])


def term_fit(goal: str, d: dict) -> float | None:
    """대상어마다 실측 메타에 글자 둘씩(바이그램) 얼마나 들어 있나의 평균 (0~1). 실측 메타가 없으면 None — 판단하지 않는다."""
    ts = terms(goal)
    mt = meta_text(d)
    if not ts or len(mt) < 20:
        return None
    mb, ml = _bigrams(mt), re.sub(r"\s", "", mt.lower())
    # 대상어가 통째로 있으면 1, 글자 일부만 겹치면 절반만 ('방문자수'와 '연계 방문이'는 다르다)
    sc = [1.0 if t.lower() in ml else 0.5 * len(_bigrams(t) & mb) / len(_bigrams(t)) for t in ts]
    return sum(sc) / len(sc)


def time_asks(goal: str) -> set[str]:
    return {k for rx, k in ASK_TIME if rx.search(goal)}


def time_fit(goal: str, d: dict) -> float:
    """질문이 요구한 시간 단위와 실측 시간 단위·시간 열 대조 → 배율."""
    asks = time_asks(goal)
    if not asks:
        return 1.0
    g = d.get("grain") or {}
    t = g.get("time")
    fs = (d.get("schema") or {}).get("fields") or []
    names = [f"{f.get('name') or ''} {f.get('title') or ''}" for f in fs]
    if not fs:
        return 1.0  # 실측 필드가 없으면 판단하지 않는다
    w = 1.0
    if "realtime" in asks:
        avg = sum(1 for n in names if AVG_FIELD.search(n))
        if t == "realtime":
            w *= 1.15
        elif avg and avg >= len(names) / 3:  # 값 열 대부분이 평균 — 실시간이 아니다
            w *= 0.7
    if "hour" in asks:
        w *= 1.15 if t == "realtime" or any(HOUR_FIELD.search(n) for n in names) else 0.7
    for k in ("day", "month", "quarter", "year"):
        if k in asks:
            if t and TIME_ORDER.index(t) <= TIME_ORDER.index(k):
                w *= 1.1   # 요구보다 세밀하거나 같으면 내려서 맞출 수 있다 (R-22)
            elif t:
                w *= 0.8   # 요구보다 거칠다 — 월 단위를 묻는데 분기·연 집계
    if "series" in asks and not t:
        w *= 0.9
    return w


def raw_fit(d: dict) -> float:
    """원천(개별 행) 우선 — 점포·거래·기관 1건이 한 행이면 조금 앞으로 (집계보다 원천, 사용자 원칙)."""
    unit = (d.get("coverage") or {}).get("admin_unit")
    sp = (d.get("grain") or {}).get("space")
    return 1.05 if unit == "개별" or sp in ("point", "parcel") else 1.0


CONTRAST = [("공공", "민간"), ("국내", "해외"), ("국내", "국외"), ("내국인", "외국인"), ("개인", "법인")]


def contrast_fit(goal: str, d: dict) -> float:
    """질문은 한쪽(공공)을 묻는데 데이터 제목은 반대쪽(민간)이면 내린다 — 글자가 대부분 겹쳐도 대상이 다르다."""
    t = d.get("title") or ""
    for a, b in CONTRAST:
        for x, y in ((a, b), (b, a)):
            if x in goal and y not in goal and y in t and x not in t:
                return 0.75
    return 1.0


def meta_weight(goal: str, d: dict, pinned: bool = False) -> float:
    """pinned: 맥락이 데이터 단위로 지정한 멤버(사람 검토로 고른 신호 데이터) — 용어가 안 겹쳐도 내리지 않는다."""
    tf = term_fit(goal, d)
    w = (0.75 + 0.5 * tf) if tf is not None else 1.0
    w *= time_fit(goal, d) * raw_fit(d) * contrast_fit(goal, d)
    if pinned:
        w = max(w, 1.0)
    return max(0.6, min(1.35, w))
