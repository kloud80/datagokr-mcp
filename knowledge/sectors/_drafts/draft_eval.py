"""부문 검토 초안 평가 — 공유 규칙 파일을 건드리지 않고 초안(yaml)을 현재 규칙 뒤에 붙여 분류 결과를 본다.

사용: python knowledge/sectors/_drafts/draft_eval.py <draft.yaml> [<부문> ...] [--show N]
  초안 형식: {sector_map: [...], exclusions: [...], subsectors: [...], keys: [...], contexts: [...], review_log: "..."}
  부문을 주면 그 부문의 전체/생존/제외 규칙별 건수, 세부 부문별 건수, 표본을 출력한다.
출력 parquet: data/processed/_draft_eval.parquet (id, title, list_type, agency_name, brm, sector, sector_rule, subsector, excluded_by)
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from pds.rank import exclude as ex  # noqa: E402
from pds.rank.classify import classify  # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("draft")
    ap.add_argument("sectors", nargs="*")
    ap.add_argument("--show", type=int, default=12)
    a = ap.parse_args(argv)
    draft = yaml.safe_load(Path(a.draft).read_text(encoding="utf-8")) or {}
    base_map, base_rules, base_subs = ex.load_sector_map(), ex.load_rules(), ex.load_subsectors()
    ex.load_sector_map = lambda: base_map + (draft.get("sector_map") or [])
    ex.load_rules = lambda: base_rules + (draft.get("exclusions") or [])
    ex.load_subsectors = lambda: base_subs + (draft.get("subsectors") or [])
    cat = pd.read_parquet(ROOT / "data/processed/catalog.parquet")
    c = classify(cat)
    d = c.merge(cat[["id", "title", "list_type", "agency_name", "brm"]], on="id")
    d[["id", "title", "list_type", "agency_name", "brm", "sector", "sector_rule", "subsector", "excluded_by"]].to_parquet(
        ROOT / f"data/processed/_draft_eval_{Path(a.draft).stem}.parquet")  # 초안별 파일 (병렬 평가 충돌 방지)
    ids = {r["id"] for r in draft.get("sector_map") or []}
    if ids:
        print("remapped by draft:", d[d.sector_rule.isin(ids)].groupby(["sector_rule", "sector"]).size().to_dict())
    for s in a.sectors:
        F = d[d.sector == s]
        L = F[F.excluded_by.isna()]
        print(f"\n## {s}  total {len(F)}  live {len(L)}")
        print("  excluded_by:", F.excluded_by.value_counts().to_dict())
        print("  subsector:", L.subsector.value_counts(dropna=False).to_dict())
        for sub, g in L.groupby("subsector", dropna=False):
            for r in g.sample(min(a.show // 3 or 1, len(g)), random_state=1).itertuples():
                print(f"    [{sub}] {r.list_type} {r.title[:60]}")
        x = F[F.excluded_by.notna() & (F.list_type != "FILE")]
        for r in x.head(a.show).itertuples():
            print(f"    x({r.excluded_by}) API {r.title[:60]}")


if __name__ == "__main__":
    main()
