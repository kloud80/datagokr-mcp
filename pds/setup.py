"""설치·백업 — 저장소를 받은 사람이 한 번에 돌려 볼 수 있게.

  python -m pds setup            지식(git) 확인 → 포털 목록 스냅샷 받기 → 설명서 → (DB 설정 시) 테이블·적재 → 색인
  python -m pds data-pack        data/processed 스냅샷을 dist/pds-data-<날짜>.zip 으로 (GitHub Release에 올릴 파일)
  python -m pds db-backup        DB의 pds_* 테이블만 backups/pds-<날짜>/ 에 parquet로 (같은 스키마의 다른 테이블은 건드리지 않는다)
  python -m pds db-restore DIR   그 백업을 되돌린다 (pds_* 테이블만, --yes 필요)

원칙: 원본은 파일(knowledge/ + data/processed/), DB는 파생 인덱스다. DB가 없어도 서비스는 돈다.
"""
from __future__ import annotations

import datetime as dt
import json
import shutil
import sys
import zipfile
from pathlib import Path

from pds import config

SNAPSHOT_FILES = ("catalog.parquet", "class.parquet", "score.parquet", "std_dataset.parquet", "std_item.parquet")
RELEASE_BASE = "https://github.com/kloud80/datagokr-mcp/releases/download"
SNAPSHOT_TAG = "data-20260731"  # 지식 체계가 만들어진 포털 목록 스냅샷 (catalog.snapshot_date)


def _step(n: int, msg: str) -> None:
    print(f"\n[{n}] {msg}")


def _have_snapshot() -> bool:
    return all((config.PROCESSED / f).exists() for f in SNAPSHOT_FILES)


def fetch_snapshot(url: str | None = None) -> bool:
    """GitHub Release의 포털 목록 스냅샷을 받아 data/processed 에 푼다."""
    import os

    import httpx
    url = url or os.getenv("PDS_DATA_URL") or f"{RELEASE_BASE}/{SNAPSHOT_TAG}/pds-{SNAPSHOT_TAG}.zip"
    if Path(url).exists():  # 로컬 파일(사내 공유 폴더 등)
        config.PROCESSED.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(url) as z:
            z.extractall(config.PROCESSED)
        print(f"    {url} → {config.PROCESSED}")
        return True
    tmp = config.ROOT / "dist" / Path(url).name
    tmp.parent.mkdir(parents=True, exist_ok=True)
    try:
        with httpx.stream("GET", url, follow_redirects=True, timeout=120) as r:
            if r.status_code != 200:
                print(f"    스냅샷을 받지 못함 (HTTP {r.status_code}) — {url}")
                return False
            with tmp.open("wb") as f:
                for chunk in r.iter_bytes():
                    f.write(chunk)
    except httpx.HTTPError as e:
        print(f"    스냅샷을 받지 못함 ({type(e).__name__}) — {url}")
        return False
    config.PROCESSED.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(tmp) as z:
        z.extractall(config.PROCESSED)
    print(f"    {tmp.name} → {config.PROCESSED}")
    return True


def data_pack() -> Path:
    if not _have_snapshot():
        raise SystemExit("data/processed 스냅샷이 없다 — python -m pds download && python -m pds build")
    import pandas as pd
    snap = pd.read_parquet(config.PROCESSED / "catalog.parquet", columns=["snapshot_date"])["snapshot_date"].iloc[0]
    tag = f"data-{str(snap).replace('-', '')}"
    out = config.ROOT / "dist" / f"pds-{tag}.zip"
    out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for f in SNAPSHOT_FILES:
            z.write(config.PROCESSED / f, f)
    print(f"{out} ({out.stat().st_size / 1e6:.1f} MB) — GitHub Release '{tag}'에 이 이름으로 올린다")
    return out


def setup(rebuild: bool = False, with_kg: bool = False, skip_db: bool = False) -> None:
    n = 0
    n += 1
    _step(n, "환경")
    print(f"    Python {sys.version.split()[0]} · 저장소 {config.ROOT}")
    if sys.version_info < (3, 11):
        raise SystemExit("    Python 3.11 이상이 필요하다")
    from pds.schema.validate import run as validate
    rep, _ = validate()
    print(f"    지식 체계(knowledge/) 검증: 오류 {len(rep.errors)} · 경고 {len(rep.warnings)}")
    if not rep.ok:
        raise SystemExit("    knowledge/ 검증 실패 — 저장소를 다시 받아 보세요")

    n += 1
    _step(n, "포털 목록 스냅샷 (catalog 층 — 9.6만 건 단서 검색)")
    if _have_snapshot() and not rebuild:
        print("    이미 있음")
    elif rebuild or not fetch_snapshot():
        print("    포털에서 새로 받아 만든다 (수십 분) — python -m pds download && python -m pds build")
        from pds.__main__ import cmd_build, cmd_download
        cmd_download(None)
        cmd_build(None)

    n += 1
    _step(n, "데이터 설명서 (docs/dossiers)")
    from pds.dossier.render import render_all
    print(f"    {render_all()}")

    n += 1
    _step(n, "Postgres (선택)")
    if skip_db or not config.DATABASE_URL:
        print("    건너뜀 — .env에 POSTGRES_* 를 넣으면 테이블을 만들고 적재한다 (서비스는 DB 없이도 돈다)")
    else:
        from pds import db
        from pds.__main__ import cmd_load_db
        with db.connect() as conn:
            print(f"    스키마 {config.DB_SCHEMA} · 마이그레이션 {db.migrate(conn) or '최신'}")
            conn.commit()
        cmd_load_db(None)
        from pds.knowledge.kload import load
        print(f"    지식 적재 {load()['counts']}")
        if with_kg:
            from pds.__main__ import cmd_kg_build, cmd_kg_load
            cmd_kg_build(None)
            cmd_kg_load(None)

    n += 1
    _step(n, "검색 색인")
    from pds.service import index
    ix = index.reload()
    print(f"    데이터 {len(ix.datasets)} · 조인 {len(ix.edges)} · 포털 목록 {0 if ix.catalog is None else len(ix.catalog):,}")

    n += 1
    _step(n, "웹 화면")
    if (config.ROOT / "web" / "dist" / "index.html").exists():
        print("    빌드 있음")
    else:
        print("    빌드 없음 — cd frontend && npm install && npm run build  (API·MCP는 빌드 없이도 쓸 수 있다)")
    print("\n끝. 실행: python -m pds serve --port 8765  ·  MCP: python -m pds mcp")


# ───────────────────────── DB 백업·복원 (pds_* 테이블만)
def _pds_tables(conn) -> list[str]:
    return [r[0] for r in conn.execute(
        "select table_name from information_schema.tables where table_schema=%s and table_type='BASE TABLE' "
        "and table_name like 'pds\\_%%' order by table_name", (config.DB_SCHEMA,))]


def db_backup(out: Path | None = None) -> Path:
    import pandas as pd
    from pds import db
    out = out or config.ROOT / "backups" / f"pds-{dt.date.today():%Y%m%d}"
    out.mkdir(parents=True, exist_ok=True)
    manifest = {"schema": config.DB_SCHEMA, "created_at": dt.datetime.now().isoformat(timespec="seconds"), "tables": {}}
    with db.connect() as conn:
        manifest["migrations"] = [r[0] for r in conn.execute("select version from pds_schema_migrations order by version")]
        for t in _pds_tables(conn):
            with conn.cursor() as cur:
                cur.execute(f"select * from {t}")
                cols = [d.name for d in cur.description]
                df = pd.DataFrame(cur.fetchall(), columns=cols)
            for c in df.columns:  # json·배열 열은 문자열로 (parquet 호환)
                if df[c].map(lambda v: isinstance(v, (dict, list))).any():
                    df[c] = df[c].map(lambda v: json.dumps(v, ensure_ascii=False, default=str) if isinstance(v, (dict, list)) else v)
            df.to_parquet(out / f"{t}.parquet", index=False)
            manifest["tables"][t] = len(df)
            print(f"    {t:32s} {len(df):>9,}")
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{out} — pds_* {len(manifest['tables'])}개 테이블 {sum(manifest['tables'].values()):,}행")
    return out


def db_restore(src: Path, yes: bool = False) -> None:
    import pandas as pd
    from pds import db
    manifest = json.loads((src / "manifest.json").read_text(encoding="utf-8"))
    if not yes:
        raise SystemExit(f"스키마 {config.DB_SCHEMA}의 pds_* 테이블 {len(manifest['tables'])}개를 백업으로 덮어쓴다 — 확인했으면 --yes")
    with db.connect() as conn:
        db.migrate(conn)
        have = set(_pds_tables(conn))
        tables = [t for t in manifest["tables"] if t in have and t != "pds_schema_migrations"]
        conn.execute("truncate " + ", ".join(tables))
        for t in tables:
            df = pd.read_parquet(src / f"{t}.parquet")
            if len(df):
                db._copy(conn, t, df)
            print(f"    {t:32s} {len(df):>9,}")
        conn.commit()
    print(f"복원 끝 — {len(tables)}개 테이블")


def clean_dist() -> None:
    shutil.rmtree(config.ROOT / "dist", ignore_errors=True)
