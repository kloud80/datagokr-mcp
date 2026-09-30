"""벌크 메타 3종 → 정규화된 catalog DataFrame.

주 테이블은 목록개방현황(15062804, 목록키 유일). 목록 메타정보(15121937)에서 요청변수·출력결과를 붙인다.
15121937은 따옴표가 깨진 행이 소수 있어 컬럼이 밀린다 → 목록유형이 FILE/API/STD가 아닌 행은 버린다.
STD 목록은 15121937에서 제공기관별로 행이 반복되므로 목록키 단위로 합친다.
"""
from __future__ import annotations

import re
from datetime import date

import pandas as pd

from pds import config

OPEN_COLUMNS = {
    "목록키": "id",
    "목록유형": "list_type",
    "목록명": "title",
    "파일데이터명": "file_title",
    "분류체계": "brm",
    "제공기관코드": "agency_code",
    "제공기관": "agency_name",
    "관리 부서명": "dept",
    "보유근거": "legal_basis",
    "수집방법": "collect_method",
    "업데이트 주기": "update_cycle",
    "차기 등록 예정일": "next_reg_date",
    "매체유형": "media_type",
    "전체행": "row_count",
    "확장자(데이터포맷)": "formats",
    "키워드": "keywords",
    "다운로드_활용신청건수": "usage_count",
    "등록일": "registered_at",
    "수정일": "modified_at",
    "데이터 한계": "data_limit",
    "제공형태": "provide_form",
    "설명": "description",
    "기타 유의사항": "notes",
    "공간범위": "spatial_scope",
    "시간범위": "temporal_scope",
    "비용부과유무": "fee",
    "이용허락범위": "license",
    "API 유형": "api_type",
    "신청가능 트래픽": "traffic_raw",
    "심의 유형": "approval_raw",
    "조회수": "view_count",
    "목록 URL": "url",
    "국가중점여부": "national_key",
    "표준데이터여부": "standard",
}

VALID_LIST_TYPES = {"FILE", "API", "STD"}


def snapshot_date(path) -> date:
    m = re.search(r"_(\d{8})\.csv$", str(path))
    s = m.group(1)
    return date(int(s[:4]), int(s[4:6]), int(s[6:]))


def _clean_str(s: pd.Series) -> pd.Series:
    """앞뒤 공백 제거, 빈 문자열은 None. object dtype으로 두어 파서 함수가 NA 대신 None을 받게 한다."""
    return s.map(lambda v: (str(v).strip() or None) if isinstance(v, str) else None).astype(object)


def read_open() -> tuple[pd.DataFrame, date]:
    path = config.raw_file("15062804")
    df = pd.read_csv(path, encoding="utf-8-sig", dtype=str)
    missing = set(OPEN_COLUMNS) - set(df.columns)
    if missing:
        raise ValueError(f"15062804 컬럼 변경 감지: {missing}")
    df = df.rename(columns=OPEN_COLUMNS)[list(OPEN_COLUMNS.values())]
    for c in df.columns:
        df[c] = _clean_str(df[c])
    return df, snapshot_date(path)


def read_meta() -> pd.DataFrame:
    """목록키별 요청변수·출력결과(쉼표 구분 컬럼명 목록)와 서비스 유형."""
    path = config.raw_file("15121937")
    df = pd.read_csv(path, encoding="cp949", dtype=str)
    df = df[df["목록유형"].isin(VALID_LIST_TYPES)]
    df = df.rename(columns={"목록키": "id", "요청변수": "request_vars", "출력결과": "output_cols",
                            "서비스 유형": "service_type"})

    def union(values: pd.Series) -> str | None:
        seen: dict[str, None] = {}
        for v in values.dropna():
            for tok in str(v).split(","):
                tok = tok.strip()
                if tok:
                    seen.setdefault(tok, None)
        return ",".join(seen) or None

    agg = df.groupby("id").agg(
        request_vars=("request_vars", union),
        output_cols=("output_cols", union),
        service_type=("service_type", "first"),
    )
    return agg.reset_index()


def read_std() -> tuple[pd.DataFrame, pd.DataFrame]:
    """제공 표준: (표준데이터셋 300행, 항목 정의 행)."""
    path = config.raw_file("15156444")
    df = pd.read_csv(path, encoding="utf-8-sig", dtype=str)
    for c in df.columns:
        df[c] = _clean_str(df[c])
    ds = (df[["데이터셋일련번호", "데이터셋명", "제공범위내용", "관계법령내용", "소관기관명", "제공기관명", "제공시스템명", "갱신주기"]]
          .drop_duplicates("데이터셋일련번호")
          .rename(columns={"데이터셋일련번호": "std_id", "데이터셋명": "name", "제공범위내용": "scope",
                           "관계법령내용": "laws", "소관기관명": "owner", "제공기관명": "provider",
                           "제공시스템명": "system", "갱신주기": "update_cycle"}))
    items = df.rename(columns={"데이터셋일련번호": "std_id", "항목번호": "item_no", "항목명": "item_name",
                               "필수여부": "required", "항목설명": "item_desc", "허용값": "allowed",
                               "단위설명": "unit", "예시값": "example"})[
        ["std_id", "item_no", "item_name", "required", "item_desc", "allowed", "unit", "example"]]
    return ds, items


_TRAFFIC_RE = re.compile(r"개발계정\s*:\s*([\d,]+)")
_APPROVAL_RE = re.compile(r"개발단계\s*:\s*(\S+)\s*/\s*운영단계\s*:\s*(\S+)")


def parse_traffic(s: str | None) -> int | None:
    if not isinstance(s, str):
        return None
    m = _TRAFFIC_RE.search(s)
    return int(m.group(1).replace(",", "")) if m else None


def parse_approval(s: str | None) -> tuple[str | None, str | None]:
    """'개발단계 : 자동승인 / 운영단계 : 심의승인' → ('auto', 'review')"""
    if not isinstance(s, str):
        return None, None
    m = _APPROVAL_RE.search(s)
    if not m:
        return None, None
    conv = {"자동승인": "auto", "심의승인": "review"}
    return conv.get(m.group(1)), conv.get(m.group(2))


# 이름 정규화로 안 맞는 표준데이터 목록 → 제공 표준 데이터셋명
_STD_NAME_OVERRIDES = {"전국향토유산표준데이터": "향토문화유적", "전국초등학교시간표정보표준데이터": "초중등학교시간표정보"}


def _std_key(name: str) -> str:
    return re.sub(r"\s|전국|표준데이터|정보|현황", "", name)


def link_std(df: pd.DataFrame, std_ds: pd.DataFrame, std_items: pd.DataFrame) -> pd.DataFrame:
    """목록유형=STD 행에 std_id를 붙이고, 비어 있는 출력결과를 표준 항목명으로 채운다."""
    by_key = dict(zip(std_ds["name"].map(_std_key), std_ds["std_id"]))
    by_name = dict(zip(std_ds["name"], std_ds["std_id"]))
    is_std = df["list_type"].eq("STD")
    df["std_id"] = None
    df.loc[is_std, "std_id"] = [
        by_name.get(_STD_NAME_OVERRIDES.get(t, "")) or by_key.get(_std_key(t)) for t in df.loc[is_std, "title"]
    ]
    cols = std_items.groupby("std_id")["item_name"].agg(lambda s: ",".join(s.dropna()))
    fill = is_std & df["output_cols"].isna()
    df.loc[fill, "output_cols"] = df.loc[fill, "std_id"].map(cols)
    return df


def build_catalog() -> tuple[pd.DataFrame, date]:
    df, snap = read_open()
    meta = read_meta()
    df = df.merge(meta, on="id", how="left")
    std_ds, std_items = read_std()
    df = link_std(df, std_ds, std_items)

    split = df["brm"].str.split(" - ", n=1, expand=True)
    df["brm_field"] = split[0].str.strip()
    df["brm_area"] = split[1].str.strip()

    for c in ("row_count", "usage_count", "view_count"):
        df[c] = pd.to_numeric(df[c].str.replace(",", ""), errors="coerce").astype("Int64")
    for c in ("registered_at", "modified_at", "next_reg_date"):
        df[c] = pd.to_datetime(df[c], errors="coerce").dt.date
    df["national_key"] = df["national_key"].eq("Y")
    df["standard"] = df["standard"].eq("Y") | df["list_type"].eq("STD")
    df["daily_traffic_dev"] = df["traffic_raw"].map(parse_traffic).astype("Int64")
    appr = df["approval_raw"].map(parse_approval)
    df["approval_dev"] = appr.str[0]
    df["approval_ops"] = appr.str[1]
    df["snapshot_date"] = snap
    return df, snap
