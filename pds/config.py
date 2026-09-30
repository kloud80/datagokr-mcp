"""경로·환경설정. 모든 모듈은 여기서 경로를 가져간다."""
from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import quote

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

DATA = ROOT / "data"
RAW = DATA / "raw"
PROCESSED = DATA / "processed"
REF = DATA / "ref"
REPORTS = ROOT / "reports"
KNOWLEDGE = ROOT / "knowledge"
SQL = ROOT / "sql"

def _database_url() -> str | None:
    """PDS_DATABASE_URL이 있으면 그대로, 없으면 POSTGRES_* 변수로 조립 (사용자명에 @가 있어 인코딩 필요)."""
    if os.getenv("PDS_DATABASE_URL"):
        return os.getenv("PDS_DATABASE_URL")
    host = os.getenv("POSTGRES_HOST")
    if not host:
        return None
    user = quote(os.getenv("POSTGRES_USER", ""), safe="")
    pw = quote(os.getenv("POSTGRES_PASSWORD", ""), safe="")
    return f"postgresql://{user}:{pw}@{host}:{os.getenv('POSTGRES_PORT', '5432')}/{os.getenv('POSTGRES_DB', '')}"


DATABASE_URL = _database_url()
DB_SCHEMA = os.getenv("POSTGRES_SCHEME") or os.getenv("POSTGRES_SCHEMA") or "pds"
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY") or os.getenv("CLAUDE_API_KEY") or None

# 벌크 메타 원천. key = 포털 목록키, value = (로컬 파일 접두어, 파일 인코딩)
BULK_SOURCES: dict[str, tuple[str, str]] = {
    "15062804": ("open", "utf-8-sig"),   # 목록개방현황: 주 테이블
    "15121937": ("meta", "cp949"),       # 목록 메타정보: 요청변수·출력결과
    "15156444": ("std", "utf-8-sig"),    # 제공 표준: 표준데이터셋 항목 정의
}


def raw_file(dataset_id: str) -> Path:
    """가장 최근에 받은 원천 파일 경로. 파일명 형식: {prefix}_{id}_{yyyymmdd}.csv"""
    prefix, _ = BULK_SOURCES[dataset_id]
    files = sorted(RAW.glob(f"{prefix}_{dataset_id}_*.csv"))
    if not files:
        raise FileNotFoundError(f"{dataset_id} 원천 파일이 없음. `python -m pds download` 먼저 실행")
    return files[-1]
