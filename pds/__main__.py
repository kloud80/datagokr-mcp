"""python -m pds <command>

  download   벌크 메타 3종 다운로드 (data/raw)
  build      카탈로그 → 3축 분류 → prelim_score (data/processed/*.parquet)
  load-db    processed parquet → Postgres (PDS_DATABASE_URL)
  report     Phase 1 HTML 리포트 (reports/phase1_ranking.html)
  report-md  Phase 1 정리 문서 (reports/phase1_ranking.md)
  family-check <slug>  패밀리 yaml 검증
  family-ops <slug>    패밀리 operations.md 생성
  kg-build   지식 그래프 컴파일 (data/processed/kg/)
  kg-load    지식 그래프 → Postgres (미적용 마이그레이션 자동 적용)
  sector-docs 부문 설명서 자동 생성 (손으로 쓴 설명서는 보존)
  summary    결과 요약 출력
  validate [--strict]  지식 원본 스키마·상호 참조 검사 (KNOWLEDGE-SPEC §5). --strict면 승격 조건도 오류
  schema-export        pydantic 모델 → schemas/*.schema.json
  gen-dataset [id…]    targets.json + probe → knowledge/datasets/ (id 없으면 verified 전체)
  serve [--port 8765]  서비스 API + 웹 채팅 (http://127.0.0.1:8765)
  mcp [--http]         MCP 서버 (stdio 기본, --http면 streamable-http :8766)
"""
from __future__ import annotations

import argparse
import sys

from pathlib import Path

import pandas as pd

from pds import config


def cmd_download(_):
    from pds.ingest.download import download_all
    for p in download_all():
        print(p)


def cmd_build(_):
    from pds.ingest.load import build_catalog, read_std
    from pds.rank.classify import classify
    from pds.rank.score import score

    catalog, snap = build_catalog()
    cls = classify(catalog)
    scores = score(catalog, cls, snap)
    std_ds, std_items = read_std()

    out = config.PROCESSED
    out.mkdir(parents=True, exist_ok=True)
    catalog.to_parquet(out / "catalog.parquet", index=False)
    cls.to_parquet(out / "class.parquet", index=False)
    scores.to_parquet(out / "score.parquet", index=False)
    std_ds.to_parquet(out / "std_dataset.parquet", index=False)
    std_items.to_parquet(out / "std_item.parquet", index=False)
    print(f"snapshot {snap}: {len(catalog):,} datasets → {out}")


def _read_processed():
    p = config.PROCESSED
    return (pd.read_parquet(p / "catalog.parquet"), pd.read_parquet(p / "class.parquet"),
            pd.read_parquet(p / "score.parquet"), pd.read_parquet(p / "std_dataset.parquet"),
            pd.read_parquet(p / "std_item.parquet"))


def cmd_load_db(_):
    from pds.db import load_snapshot
    from pds.rank.score import WEIGHTS
    catalog, cls, scores, std_ds, std_items = _read_processed()
    snap = catalog["snapshot_date"].iloc[0]
    load_snapshot(catalog.drop(columns=["snapshot_date"]), cls, scores, std_ds, std_items, snap, WEIGHTS)
    print(f"loaded snapshot {snap}")


def cmd_report(_):
    from pds.rank.report import render
    out = render()
    print(f"{out} ({out.stat().st_size / 1e6:.1f} MB)")


def cmd_report_md(_):
    from pds.rank.report_md import render
    out = render()
    print(f"{out} ({out.stat().st_size / 1e3:.0f} KB)")


def cmd_family_check(args):
    from pds.knowledge.family import check
    errors = check(args.slug)
    for e in errors:
        print("✗", e)
    print(f"{args.slug}: {'OK' if not errors else f'{len(errors)}건 문제'}")
    return 1 if errors else 0


def cmd_family_ops(args):
    from pds.knowledge.family import render_operations
    print(render_operations(args.slug))


def cmd_kg_build(_):
    from pds.knowledge.compile import build, write
    kg = build()
    out = write(kg)
    print(f"{out}: nodes {len(kg['nodes']):,} · edges {len(kg['edges']):,} · docs {len(kg['docs']):,} · chunks {len(kg['chunks']):,}")
    print(kg["nodes"]["type"].value_counts().to_string())
    print(kg["edges"]["type"].value_counts().to_string())


def cmd_kg_load(_):
    from pds.knowledge.compile import load_db
    print(load_db())


def cmd_sector_docs(_):
    from pds.knowledge.sector_doc import write_all
    for path in write_all():
        print(path)


def cmd_summary(args):
    catalog, cls, scores, *_ = _read_processed()
    df = catalog.merge(cls, on="id").merge(scores, on="id")
    print(df["api_kind_label"].value_counts().to_string(), "\n")
    print(pd.crosstab(df["sector_field"], df["agency_tier"]).to_string(), "\n")
    print(pd.crosstab(df["admin_unit"], df["admin_unit_conf"]).to_string(), "\n")
    cols = ["rank_overall", "id", "title", "agency_name", "api_kind_label", "admin_unit", "prelim_score",
            "s_usage", "s_designation", "s_api_kind", "s_freshness", "s_meta_fill"]
    print(df.sort_values("rank_overall").head(args.top)[cols].to_string(index=False))


def cmd_probe_targets(_):
    from pds.probe.targets import write
    print(write())


def cmd_probe_specs(args):
    import json
    from pds.probe.spec import run
    t = json.loads((config.KNOWLEDGE / "targets.json").read_text(encoding="utf-8"))
    recs = run([(x["id"], x["url"]) for x in t if x["round"] == args.round])
    print(f"specs {len(recs)} swagger {sum(1 for r in recs if r.get('swagger'))}")


def cmd_probe_apply(args):
    import asyncio
    import json
    from pds.probe.apply import apply_many
    t = json.loads((config.KNOWLEDGE / "targets.json").read_text(encoding="utf-8"))
    ids = [x["id"] for x in t if x["round"] == args.round and x["kind"] in ("REST", "SOAP")
           and not (config.ROOT / "probe" / "apply" / f"{x['id']}.json").exists()]
    res = asyncio.run(apply_many(ids))
    print({r["id"]: r.get("result") for r in res})


def cmd_probe_run(args):
    from pds.probe.report import build_report, run_round
    run_round(args.round, max_rows=args.max_rows)
    print(build_report(args.round))


def cmd_probe_report(args):
    from pds.probe.report import build_report
    print(build_report(args.round))


def cmd_validate(args):
    from collections import Counter
    from pds.schema.validate import run
    rep, _ = run(strict=args.strict)
    for e in rep.errors[: args.limit]:
        print("✗", e)
    gate = Counter(w.split("[승격] ", 1)[1].split(" (")[0] for w in rep.warnings if "[승격]" in w)
    other = [w for w in rep.warnings if "[승격]" not in w]
    for w in other[: args.limit]:
        print("!", w)
    if gate:
        print("승격 조건 미충족 (경고):", " · ".join(f"{k} {v}" for k, v in gate.most_common()))
    print(" · ".join(f"{k} {v}" for k, v in sorted(rep.counts.items())),
          f"→ 오류 {len(rep.errors)} · 경고 {len(rep.warnings)}")
    return 0 if rep.ok else 1


def cmd_schema_export(_):
    from pds.schema.validate import export_json_schema
    for p in export_json_schema():
        print(p)


def cmd_gen_dataset(args):
    from pds.dossier.gen_dataset import write, write_all
    if args.ids:
        for i in args.ids:
            print(write(i)[0])
        return 0
    res = write_all(args.status)
    print(f"written {res['written']} · failed {len(res['failed'])}")
    for k, v in res["failed"].items():
        print("✗", k, v)
    return 1 if res["failed"] else 0


def cmd_serve(args):
    import uvicorn
    uvicorn.run("pds.service.app:app", host=args.host, port=args.port, reload=False)


def cmd_mcp(args):
    from pds.mcp.server import main as run
    run(http=args.http)


def cmd_setup(args):
    from pds.setup import setup
    setup(rebuild=args.rebuild, with_kg=args.kg, skip_db=args.no_db)


def cmd_data_pack(_):
    from pds.setup import data_pack
    data_pack()


def cmd_db_backup(args):
    from pds.setup import db_backup
    db_backup(Path(args.out) if args.out else None)


def cmd_db_restore(args):
    from pds.setup import db_restore
    db_restore(Path(args.src), yes=args.yes)


def main(argv=None):
    for s in (sys.stdout, sys.stderr):  # 윈도 콘솔(cp949)에서 한글·기호 출력이 깨지지 않게
        if hasattr(s, "reconfigure"):
            s.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(prog="pds")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("download").set_defaults(fn=cmd_download)
    sub.add_parser("build").set_defaults(fn=cmd_build)
    sub.add_parser("load-db").set_defaults(fn=cmd_load_db)
    sub.add_parser("report").set_defaults(fn=cmd_report)
    sub.add_parser("report-md").set_defaults(fn=cmd_report_md)
    sub.add_parser("kg-build").set_defaults(fn=cmd_kg_build)
    sub.add_parser("sector-docs").set_defaults(fn=cmd_sector_docs)
    sub.add_parser("kg-load").set_defaults(fn=cmd_kg_load)
    sub.add_parser("probe-targets").set_defaults(fn=cmd_probe_targets)
    for name, fn in (("probe-specs", cmd_probe_specs), ("probe-apply", cmd_probe_apply), ("probe-run", cmd_probe_run),
                     ("probe-report", cmd_probe_report)):
        pp = sub.add_parser(name)
        pp.add_argument("round", nargs="?", default="1")
        pp.add_argument("--max-rows", type=int, default=1000)
        pp.set_defaults(fn=fn)
    for name, fn in (("family-check", cmd_family_check), ("family-ops", cmd_family_ops)):
        fp = sub.add_parser(name)
        fp.add_argument("slug")
        fp.set_defaults(fn=fn)
    v = sub.add_parser("validate")
    v.add_argument("--strict", action="store_true")
    v.add_argument("--limit", type=int, default=40)
    v.set_defaults(fn=cmd_validate)
    sub.add_parser("schema-export").set_defaults(fn=cmd_schema_export)
    gd = sub.add_parser("gen-dataset")
    gd.add_argument("ids", nargs="*")
    gd.add_argument("--status", default="verified")
    gd.set_defaults(fn=cmd_gen_dataset)
    sv = sub.add_parser("serve")
    sv.add_argument("--host", default="127.0.0.1")
    sv.add_argument("--port", type=int, default=8765)
    sv.set_defaults(fn=cmd_serve)
    mc = sub.add_parser("mcp")
    mc.add_argument("--http", action="store_true")
    mc.set_defaults(fn=cmd_mcp)
    st = sub.add_parser("setup", help="처음 받은 저장소를 한 번에 세팅 (스냅샷·설명서·DB·색인)")
    st.add_argument("--rebuild", action="store_true", help="스냅샷을 받지 않고 포털에서 새로 만든다")
    st.add_argument("--kg", action="store_true", help="지식 그래프(kg)도 DB에 적재")
    st.add_argument("--no-db", action="store_true", help="DB 단계를 건너뛴다")
    st.set_defaults(fn=cmd_setup)
    sub.add_parser("data-pack").set_defaults(fn=cmd_data_pack)
    bk = sub.add_parser("db-backup", help="DB의 pds_* 테이블만 parquet로 백업")
    bk.add_argument("--out")
    bk.set_defaults(fn=cmd_db_backup)
    rs = sub.add_parser("db-restore", help="db-backup 결과를 되돌린다 (pds_* 테이블만)")
    rs.add_argument("src")
    rs.add_argument("--yes", action="store_true")
    rs.set_defaults(fn=cmd_db_restore)
    s = sub.add_parser("summary")
    s.add_argument("--top", type=int, default=40)
    s.set_defaults(fn=cmd_summary)
    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
