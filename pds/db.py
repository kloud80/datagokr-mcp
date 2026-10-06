"""Postgres 적재. 원본은 data/processed/*.parquet, DB는 파생 인덱스."""
from __future__ import annotations

import json
from datetime import date

import pandas as pd
import psycopg
from psycopg import sql

from pds import config


def connect() -> psycopg.Connection:
    if not config.DATABASE_URL:
        raise RuntimeError("DB 접속 정보 없음. .env에 POSTGRES_* 또는 PDS_DATABASE_URL 설정")
    conn = psycopg.connect(config.DATABASE_URL, connect_timeout=10)
    schema = sql.Identifier(config.DB_SCHEMA)
    exists = conn.execute("select 1 from pg_namespace where nspname = %s", (config.DB_SCHEMA,)).fetchone()
    if not exists:  # 공용 DB에선 스키마 생성 권한이 없을 수 있으므로 없을 때만 만든다
        conn.execute(sql.SQL("create schema {}").format(schema))
    conn.execute(sql.SQL("set search_path to {}").format(schema))
    return conn


MIGRATIONS_TABLE = """
create table if not exists pds_schema_migrations (
    version    text primary key,
    name       text not null,
    checksum   text not null,
    applied_at timestamptz not null default now()
)"""


def migrate(conn: psycopg.Connection) -> list[str]:
    """sql/NNN_*.sql 중 아직 적용 안 된 것을 번호 순으로 적용. 적용된 파일이 바뀌었으면 멈춘다 (ARCHITECTURE.md §5)."""
    import hashlib
    conn.execute(MIGRATIONS_TABLE)
    done = {v: c for v, c in conn.execute("select version, checksum from pds_schema_migrations")}
    applied = []
    for f in sorted(config.SQL.glob("[0-9][0-9][0-9]_*.sql")):
        version = f.name[:3]
        body = f.read_text(encoding="utf-8")
        checksum = hashlib.sha1(body.encode("utf-8")).hexdigest()
        if version in done:
            if done[version] != checksum:
                raise RuntimeError(f"적용된 마이그레이션 {f.name}이 바뀌었다. 고치지 말고 새 번호 파일로 ALTER 할 것")
            continue
        conn.execute(body)
        conn.execute("insert into pds_schema_migrations (version, name, checksum) values (%s, %s, %s)",
                     (version, f.stem, checksum))
        applied.append(f.name)
    conn.commit()
    return applied


def _clean(v):
    # Postgres text·jsonb는 NUL(\u0000)을 못 담는다 — 이진 파일 샘플값 등에서 들어온다
    return v.replace("\x00", "").replace("\\u0000", "") if isinstance(v, str) else v


def _rows(df: pd.DataFrame):
    for rec in df.itertuples(index=False, name=None):
        yield tuple(None if (v is None or (not isinstance(v, (str, list, dict)) and pd.isna(v))) else _clean(v)
                    for v in rec)


def _copy(conn: psycopg.Connection, table: str, df: pd.DataFrame) -> None:
    cols = ", ".join(df.columns)
    with conn.cursor() as cur, cur.copy(f"copy {table} ({cols}) from stdin") as cp:
        for row in _rows(df):
            cp.write_row(row)


def load_snapshot(catalog: pd.DataFrame, cls: pd.DataFrame, scores: pd.DataFrame,
                  std_ds: pd.DataFrame, std_items: pd.DataFrame, snapshot: date,
                  weights: dict) -> None:
    with connect() as conn:
        migrate(conn)
        for t in ("pds_catalog_dataset", "pds_dataset_class", "pds_dataset_score"):
            conn.execute(f"delete from {t} where snapshot_date = %s", (snapshot,))
        conn.execute("truncate pds_std_item, pds_std_dataset")

        cat_cols = [r[0] for r in conn.execute(
            "select column_name from information_schema.columns "
            "where table_schema=%s and table_name='pds_catalog_dataset' order by ordinal_position", (config.DB_SCHEMA,))]
        _copy(conn, "pds_catalog_dataset", catalog.assign(snapshot_date=snapshot)[cat_cols])
        _copy(conn, "pds_dataset_class", cls.assign(snapshot_date=snapshot))
        sc = scores.assign(snapshot_date=snapshot, weights=json.dumps(weights))
        _copy(conn, "pds_dataset_score", sc)
        _copy(conn, "pds_std_dataset", std_ds)
        items = std_items.assign(item_no=pd.to_numeric(std_items["item_no"], errors="coerce"))
        _copy(conn, "pds_std_item", items.dropna(subset=["item_no"]).astype({"item_no": int}))
        conn.commit()
