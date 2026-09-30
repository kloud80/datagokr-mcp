"""코드표 (적용 메모 6)."""
import pytest
from pydantic import ValidationError

from pds.codes.build import SPEC_PAIR
from pds.codes.needs import classify_field
from pds.schema import CodeList

EV = [{"type": "law", "source": "law:011023#67"}]


def test_codelist_rules():
    CodeList.model_validate({"id": "x", "name": "n", "completeness": "complete", "evidence": EV, "rows": 2,
                             "values": [{"code": "01", "name": "전"}, {"code": "02", "name": "답"}]})
    with pytest.raises(ValidationError):  # 중복 코드
        CodeList.model_validate({"id": "x", "name": "n", "completeness": "complete", "evidence": EV, "rows": 2,
                                 "values": [{"code": "01", "name": "전"}, {"code": "01", "name": "답"}]})
    with pytest.raises(ValidationError):  # 값도 파일도 없음
        CodeList.model_validate({"id": "x", "name": "n", "completeness": "observed", "evidence": EV, "rows": 1})


def test_spec_enum_parse():
    assert SPEC_PAIR.findall("Y:가능,N:불가") == [("Y", "가능"), ("N", "불가")]
    assert [a for a, _ in SPEC_PAIR.findall("H:Html, T:Text")] == ["H", "T"]


@pytest.mark.parametrize("name,title,top,unique,cls", [
    ("clCd", "종별코드", ["01", "11", "21"], 12, "A"),               # 불투명 코드, 이름 컬럼 없음
    ("telNo", "전화번호", ["031-671-2283"], 30, None),                # 연락처는 코드 아님
    ("hvctayn", "CT가용", ["Y", "N1"], 2, "D"),                       # Y/N + 특수값
    ("sidoCd", None, ["11", "26"], 17, "C"),                           # 행정구역
    ("evalNo", "평가번호", ["E00199000010", "E00106000070"], 28, "C"),  # 개체 식별자
])
def test_classify_field(name, title, top, unique, cls):
    got, _ = classify_field(name, title, top, unique, "code", set(), None)
    assert got == cls
