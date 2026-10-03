"""4차 확대 검토 큐 — 검증 데이터 3,000 목표, 도시·부동산(회사 주력) 먼저 (PDS_WAVE=wave4 python -m pds.expand.wave4 [re|rest]).

키를 새로 받지 않는다 — 포털(계정 하나 + 활용신청)과 이미 키가 있는 사이트(브이월드·서울·법제처·나이스),
키가 필요 없는 사이트로 이어지는 링크형만 대상으로 한다.
범위
  re   도시·부동산: 국토관리 부문 전체 + 다른 부문의 부동산·토지·건축·도시계획·개발사업 데이터
  rest 나머지 부문 (re를 마친 뒤 3,000까지 채울 때)
대상: 지식 체계에 없고, 검증 대상(targets)에 없고, 제외 규칙에 안 걸린 것 — 아직 안 본 것 + 2·3차에서 미룬 것(defer)
판정: defer-noise(기관 운영 자료)는 규칙으로, 나머지는 review → 부문 검토(pds.expand.review, 이번 차수 기준 WAVE_RULES)
  도시·부동산은 통계라도 지역·기간 격자로 이을 수 있으면 다시 본다 — 그래서 2·3차의 '통계' 잡음 규칙을 쓰지 않는다.
자치단체 가족(같은 제목을 여러 시군구가 낸 것)은 대표 1건을 검토·검증한다 (members에 나머지).
"""
from __future__ import annotations

import json
import re
import sys

import pandas as pd

from pds import config
from pds.expand.wave2 import CENTRAL_LIKE, LOCAL_AGENCY, family, keys_of, tier

OUT = config.KNOWLEDGE / "expansion" / "wave4"
RE_TITLE = re.compile(r"부동산|토지|지가|공시가|공시지가|실거래|전월세|매매가|아파트|공동주택|주택|건축|건물|필지|지적|용도지역|용도지구|"
                      r"도시계획|도시관리|지구단위|재개발|재건축|정비사업|정비구역|분양|임대|택지|산업단지|도시재생|도시개발|상가|오피스텔|"
                      r"공유재산|국유재산|공매|경매|도로명주소|공간정보|개발행위|개발제한|토지이용|부지|빈집")
OPS_NOISE = re.compile(r"홈페이지|게시판|민원|예산|결산|채용|직원|교육자료|홍보|보도자료|연구보고서|업무추진비|회의록|인사|청렴|설문|만족도")
LINK_KINDS = ("API_LINK", "FILE_LINK")


def _seen() -> dict[str, str]:
    out = {}
    for w in ("wave2", "wave3"):
        q = pd.read_parquet(config.KNOWLEDGE / "expansion" / w / "queue.parquet")
        dec = q["final_decision"] if "final_decision" in q else q["verdict"]
        for ms, d in zip(q["members"], dec):
            for m in str(ms).split(","):
                if m:
                    out[m] = str(d)
    return out


def build(scope: str = "re") -> pd.DataFrame:
    P = config.PROCESSED
    c = pd.read_parquet(P / "catalog.parquet")
    k = pd.read_parquet(P / "class.parquet")
    s = pd.read_parquet(P / "score.parquet", columns=["id", "prelim_score", "rank_overall", "api_kind_label"])
    c = c.merge(k[["id", "sector", "subsector", "subsector_name", "admin_unit", "excluded_by"]], on="id", how="left").merge(s, on="id")
    known = {f.stem.split("_")[0].split(".")[0] for f in (config.KNOWLEDGE / "datasets").rglob("*.yaml")}
    targets = {t["id"] for t in json.loads((config.KNOWLEDGE / "targets.json").read_text(encoding="utf-8"))}
    seen = _seen()
    passed = c["excluded_by"].isna() | c["excluded_by"].eq(False)  # noqa: E712
    state = c["id"].map(lambda i: seen.get(i, "unseen"))
    fresh = state.isin(["unseen", "defer"]) | state.str.startswith("defer")
    pool = c[passed & fresh & ~c["id"].isin(known | targets)].copy()
    pool["prev"] = state[pool.index]

    # 링크형은 키 없이(또는 가진 키로) 갈 수 있는 사이트만
    links = pd.read_parquet(config.KNOWLEDGE / "expansion" / "site_links.parquet", columns=["id", "host"])
    cov = json.loads((config.KNOWLEDGE / "expansion" / "site_coverage.json").read_text(encoding="utf-8"))
    ok_hosts = {x["host"] for x in cov["sites"] if x["key"] in ("보유·검증", "키 불필요")}
    pool = pool.merge(links, on="id", how="left")
    is_link = pool["api_kind_label"].isin(LINK_KINDS)
    pool = pool[~is_link | pool["host"].isin(ok_hosts)]

    is_re = pool["sector"].fillna("").str.startswith("국토관리") | pool["title"].fillna("").str.contains(RE_TITLE)
    pool = pool[is_re] if scope == "re" else pool[~is_re]

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
        if OPS_NOISE.search(t):
            return "defer-noise", f"기관 운영 자료 ({OPS_NOISE.search(t).group(0)})"
        src = f"{r['host']} 링크" if r["api_kind_label"] in LINK_KINDS else r["api_kind_label"]
        prev = " · 이전 차수 미룸" if str(r["prev"]).startswith("defer") else ""
        fam = f" · 자치단체 {r['family_n']}곳" if r["local"] and r["family_n"] > 1 else ""
        return "review", f"{src}{prev}{fam} · 키 {','.join(r['keys']) or '열 정보로 안 보임'}"

    vv = pool.apply(verdict, axis=1, result_type="expand")
    pool["verdict"], pool["reason"] = vv[0], vv[1]
    pool["unit"] = pool.apply(lambda r: f"fam:{r['family']}" if r["local"] else r["id"], axis=1)
    rep = pool.sort_values(["unit", "prelim_score"], ascending=[True, False]).drop_duplicates("unit")
    members = pool.groupby("unit")["id"].apply(list)
    rep = rep.assign(members=rep["unit"].map(members), sector_top=rep["sector"].fillna("?").str.split(" - ").str[0])
    cols = ["unit", "id", "title", "agency_name", "list_type", "api_kind_label", "host", "prev", "sector", "sector_top", "subsector",
            "subsector_name", "tier", "keys", "local", "family_n", "members", "std_match", "sibling_of", "row_count", "update_cycle",
            "modified_at", "usage_count", "prelim_score", "verdict", "reason", "url"]
    return rep[cols].sort_values("prelim_score", ascending=False).reset_index(drop=True)


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    scope = sys.argv[1] if len(sys.argv) > 1 else "re"
    q = build(scope)
    OUT.mkdir(parents=True, exist_ok=True)
    name = "queue.parquet" if scope == "re" else f"queue_{scope}.parquet"
    q.assign(keys=q["keys"].map(",".join), members=q["members"].map(",".join)).to_parquet(OUT / name, index=False)
    t = pd.crosstab(q["sector_top"], q["api_kind_label"].fillna("?")).assign(합계=lambda d: d.sum(axis=1)).sort_values("합계", ascending=False)
    md = [f"# 4차 확대 검토 큐 (wave 4 · {'도시·부동산' if scope == 're' else '나머지 부문'})", "",
          f"후보 {sum(len(m) for m in q['members']):,}건 → 검토 단위 {len(q):,} (자치단체 가족은 대표 1건) · "
          f"이전 차수 미룸 {int(q['prev'].astype(str).str.startswith('defer').sum()):,} · 규칙 미룸 {int(q['verdict'].ne('review').sum()):,}", "",
          "| 부문 | " + " | ".join(t.columns) + " |", "|---|" + "---:|" * len(t.columns)]
    md += [f"| {s} | " + " | ".join(f"{int(x):,}" for x in r) + " |" for s, r in t.iterrows()]
    (OUT / ("README.md" if scope == "re" else f"README_{scope}.md")).write_text("\n".join(md) + "\n", encoding="utf-8")
    print("\n".join(md))


if __name__ == "__main__":
    main()
