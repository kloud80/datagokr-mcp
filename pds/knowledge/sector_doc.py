"""부문 설명서 자동 생성 — subsectors.yaml(정의·가치 원천) + 결정 규칙(이유) + 실제 데이터(건수·대표 데이터).

손으로 쓴 설명서가 이미 있으면 건드리지 않는다(generated: true 표시가 있는 파일만 다시 쓴다).
대화로 정한 판단이 원본(yaml)에 있으므로, 설명서는 언제든 재생성 가능한 파생물이다.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import yaml

from pds import config

DEPTH_KO = {"front": "앞", "back": "뒤", "hold": "보류", "system": "시스템 자체 문서"}


def _load_catalog() -> pd.DataFrame:
    p = config.PROCESSED
    return (pd.read_parquet(p / "catalog.parquet").merge(pd.read_parquet(p / "class.parquet"), on="id")
            .merge(pd.read_parquet(p / "score.parquet"), on="id"))


def _rules(sector: str) -> list[dict]:
    out = []
    for fname in ("sector_map.yaml", "exclusions.yaml"):
        for r in yaml.safe_load((config.KNOWLEDGE / "sectors" / fname).read_text(encoding="utf-8")) or []:
            text = yaml.safe_dump(r, allow_unicode=True)
            if sector in text or r.get("set_sector") == sector:
                out.append({**r, "_file": fname})
    return out


def render(sdef: dict, df: pd.DataFrame) -> str:
    sector = sdef["sector"]
    g = df[df["sector"] == sector]
    live = g[g["excluded_by"].isna()]
    rules = _rules(sector)
    field, area = sector.split(" - ", 1)
    L = ["---", f"sector: {sector}", f"subsectors: [{', '.join(s['slug'] for s in sdef['subsectors'])}]",
         f"decided_at: {sdef.get('decided_at')}", f"decided_by: {sdef.get('decided_by')}",
         f"decisions: [{', '.join(r['id'] for r in rules)}]", "generated: true   # python -m pds sector-docs 로 재생성. 손으로 고치려면 이 줄을 지울 것",
         "---", "", f"# {area}", "", "## 한 줄", str(sdef.get("note", "")).strip(), "",
         "## 규모", f"- 이 부문으로 분류된 데이터 {len(g):,}건 → 대상 {len(live):,}건 · 제외 {len(g) - len(live):,}건",
         f"- 대상 유형: " + " · ".join(f"{k} {v}" for k, v in live["api_kind_label"].value_counts().items()), "",
         "## 세부 부문", "", "| 세부 부문 | 판정 | 시의성 | 건수 | 가치의 원천 | 대표 데이터 |", "| --- | --- | --- | ---: | --- | --- |"]
    for sub in sdef["subsectors"]:
        x = live[live["subsector"] == sub["slug"]].sort_values("rank_in_sector")
        top = " · ".join(f"{t} ({i})" for t, i in zip(x["title"].head(3), x["id"].head(3)))
        flags = []
        if sub.get("cross_cutting"):
            flags.append("cross-cutting")
        if sub.get("cycle"):
            flags.append(f"cycle: {sub['cycle']}")
        L.append(f"| `{sub['slug']}` {sub['name']} | {DEPTH_KO.get(sub.get('depth'), sub.get('depth'))}"
                 f"{' · ' + ', '.join(flags) if flags else ''} | {sub.get('novelty', '—')} | {len(x):,} | "
                 f"{str(sub.get('value_source', '')).strip()} | {top} |")
    from pds.schema import store
    gaps = [gp for gp in store.load("gap") if gp["sector"] == sector]
    if gaps:
        L += ["", "## 공백 (포털에 데이터 없음)"] + [f"- `{gp['id'].rsplit('/', 1)[-1]}` {gp['name']}"
                                                  f"{' (해소)' if gp.get('status') == 'resolved' else ''}: {gp['reason']}" for gp in gaps]
    if rules:
        L += ["", "## 결정 (이관·제외)"]
        for r in rules:
            n = int((g["excluded_by"] == r["id"]).sum()) if r["_file"] == "exclusions.yaml" else int((g["sector_rule"] == r["id"]).sum())
            kind = "제외" if r["_file"] == "exclusions.yaml" else "이관"
            L.append(f"- **{kind}** `{r['id']}` ({n:,}건): {' '.join(str(r.get('reason', '')).split())}")
    L += ["", "## 대표 데이터 (부문 내 상위 15)", "", "| # | 목록키 | 데이터 | 유형 | 세부 부문 | 점수 |", "| ---: | --- | --- | --- | --- | ---: |"]
    for k, r in enumerate(live.sort_values("rank_in_sector").head(15).itertuples(), 1):
        L.append(f"| {k} | {r.id} | {r.title} | {r.api_kind_label} | {r.subsector} | {r.prelim_score:.3f} |")
    return "\n".join(L) + "\n"


def write_all(force: bool = False) -> list[Path]:
    defs = yaml.safe_load((config.KNOWLEDGE / "sectors" / "subsectors.yaml").read_text(encoding="utf-8"))
    df = _load_catalog()
    written = []
    for sdef in defs:
        if not sdef.get("doc") or not sdef.get("subsectors"):
            continue
        path = config.ROOT / sdef["doc"]
        if path.exists() and "generated: true" not in path.read_text(encoding="utf-8") and not force:
            continue  # 손으로 쓴 설명서는 보존
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(render(sdef, df), encoding="utf-8")
        written.append(path)
    return written
