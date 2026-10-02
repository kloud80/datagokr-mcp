"""3차 확대 검토 큐 — 아직 안 본 데이터 중 1단계 점수(prelim_score) 상위 N건 (PDS_WAVE=wave3 python -m pds.expand.wave3 [N]).

2차는 '열 정보로 조인 키가 보이는 것'만 골랐다. 3차는 키가 열 정보에 안 드러난 것(열 정보 없음 3.7만 건 포함)까지
점수(활용·최신성·세부 단위·연결 가능성·새로움)로 고른다 — 키는 검증 때 실데이터 값으로 다시 판정된다(synth).
제외: 지식 체계에 있는 것 · 기존 제외 규칙 · 2차 큐에서 이미 판정한 것(가족 구성원 포함).
판정: defer-noise · defer-single(한 자치단체만)은 규칙으로, 나머지는 review → 부문 검토(pds.expand.review)
"""
from __future__ import annotations

import sys

import pandas as pd

from pds import config
from pds.expand.wave2 import LOCAL_AGENCY, CENTRAL_LIKE, NOISE, family, keys_of, tier

OUT = config.KNOWLEDGE / "expansion" / "wave3"


def build(n: int = 5000) -> pd.DataFrame:
    P = config.PROCESSED
    c = pd.read_parquet(P / "catalog.parquet")
    k = pd.read_parquet(P / "class.parquet")
    s = pd.read_parquet(P / "score.parquet", columns=["id", "prelim_score", "rank_overall"])
    c = c.merge(k[["id", "sector", "subsector", "subsector_name", "admin_unit", "excluded_by"]], on="id", how="left").merge(s, on="id")
    known = {f.stem.split("_")[0].split(".")[0] for f in (config.KNOWLEDGE / "datasets").rglob("*.yaml")}
    w2 = pd.read_parquet(config.KNOWLEDGE / "expansion" / "wave2" / "queue.parquet", columns=["members"])
    seen = {m for ms in w2["members"] for m in str(ms).split(",") if m}
    passed = c["excluded_by"].isna() | c["excluded_by"].eq(False)  # noqa: E712
    pool = c[passed & ~c["id"].isin(known | seen)].sort_values("prelim_score", ascending=False).head(n).copy()

    si = pd.read_parquet(P / "std_item.parquet")
    std_cols = si.groupby("std_id")["item_name"].apply(lambda x: ",".join(map(str, x)))
    pool["cols"] = pool["output_cols"].fillna("")
    m = pool["list_type"].eq("STD") & pool["std_id"].notna()
    pool.loc[m, "cols"] = pool.loc[m, "std_id"].astype(str).map(std_cols).fillna("")
    pool["keys"] = (pool["cols"] + "," + pool["request_vars"].fillna("")).map(keys_of)
    pool["tier"] = pool["keys"].map(tier)
    ag = pool["agency_name"].fillna("")
    pool["local"] = ag.str.contains(LOCAL_AGENCY) & ~ag.str.contains(CENTRAL_LIKE)
    pool["family"] = pool["title"].map(family)
    pool["family_n"] = pool[pool["local"]].groupby("family")["id"].transform("size").reindex(pool.index).fillna(1).astype(int)
    pool["std_match"] = None
    pool["sibling_of"] = None

    def verdict(r) -> tuple[str, str]:
        t = str(r["title"])
        if NOISE.search(t):
            return "defer-noise", f"운영·통계성 제목 ({NOISE.search(t).group(0)})"
        if r["local"] and r["family_n"] == 1 and not str(r["agency_name"]).startswith("서울특별시"):
            return "defer-single", "한 자치단체만 낸다 — 전국 전략에 쓰기 어렵다"
        return "review", f"점수 상위 (순위 {int(r['rank_overall'])}) · 키 {','.join(r['keys']) or '열 정보로 안 보임'}"

    vv = pool.apply(verdict, axis=1, result_type="expand")
    pool["verdict"], pool["reason"] = vv[0], vv[1]
    pool["unit"] = pool.apply(lambda r: f"fam:{r['family']}" if r["local"] else r["id"], axis=1)
    rep = pool.sort_values(["unit", "prelim_score"], ascending=[True, False]).drop_duplicates("unit")
    members = pool.groupby("unit")["id"].apply(list)
    rep = rep.assign(members=rep["unit"].map(members), sector_top=rep["sector"].fillna("?").str.split(" - ").str[0])
    cols = ["unit", "id", "title", "agency_name", "list_type", "sector", "sector_top", "subsector", "subsector_name", "tier", "keys",
            "local", "family_n", "members", "std_match", "sibling_of", "row_count", "update_cycle", "modified_at", "usage_count",
            "prelim_score", "verdict", "reason", "url"]
    return rep[cols].sort_values("prelim_score", ascending=False).reset_index(drop=True)


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 5000
    q = build(n)
    OUT.mkdir(parents=True, exist_ok=True)
    q.assign(keys=q["keys"].map(",".join), members=q["members"].map(",".join)).to_parquet(OUT / "queue.parquet", index=False)
    t = pd.crosstab(q["sector_top"], q["verdict"]).assign(합계=lambda d: d.sum(axis=1)).sort_values("합계", ascending=False)
    md = [f"# 3차 확대 검토 큐 (wave 3)", "", f"점수 상위 {n:,}건 → 검토 단위 {len(q):,} · 키 등급 " +
          " · ".join(f"{k} {v:,}" for k, v in q["tier"].value_counts().sort_index().items()), "",
          "| 부문 | " + " | ".join(t.columns) + " |", "|---|" + "---:|" * len(t.columns)]
    md += [f"| {s} | " + " | ".join(f"{int(x):,}" for x in r) + " |" for s, r in t.iterrows()]
    (OUT / "README.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print("\n".join(md))


if __name__ == "__main__":
    main()
