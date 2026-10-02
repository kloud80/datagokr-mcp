"""2차 확대 검토 큐 — 포털 목록에서 조인 키를 가진 데이터를 골라 1차 판정까지 (python -m pds.expand.wave2).

깔때기
  1 열 정보(출력 항목·요청 변수·표준 항목)에서 키를 찾는다 — 열 이름 규칙, 표본 정밀도 A 15/15 · B 9/10
       A 공간 강키(PNU·건물·법정동·좌표) · B 개체 키(사업자·법인·기관·단지) · C 주소만(지오코딩으로 변환)
  2 아직 지식 체계에 없고 · 기존 제외 규칙 통과 · 최근 2년 내 갱신 · 개체 단위 원장이거나 API
  3 자치단체 인스턴스는 '가족'으로 접는다 (기관 머리 뗀 제목이 같은 것). 검토 단위 = 중앙 개별 + 자치단체 가족
1차 판정 (규칙 — 부문 검토에서 사람이 고친다)
  keep-variant  이미 검증된 데이터의 형제 (같은 기관·같은 제목 줄기) — 형식이 같아 검증이 싸다
  keep-core     A·B 키 + 개체 단위 + (중앙 · 표준데이터 · 5곳 이상 자치단체 가족)
  absorb-std    표준데이터(STD)와 이름이 겹치는 자치단체 가족 — 전국 표준데이터 쪽을 검토한다
  review        C(주소만) 중앙 · 2~4곳 자치단체 가족 — 부문 검토에서 판단
  defer-single  한 자치단체만 내는 목록 — 전국 전략에 쓰기 어렵다 (서울특별시는 review로)
  defer-noise   기관 운영·홍보·통계성 제목 — 부문 검토 원칙에서 미룬다
결과: knowledge/expansion/wave2/queue.parquet (+ README.md 요약)
"""
from __future__ import annotations

import datetime as dt
import re
import sys

import pandas as pd

from pds import config

OUT = config.KNOWLEDGE / "expansion" / "wave2"
FRESH_SINCE = "2024-10-01"

KEYS = {  # 이름 — 열 이름 정규식
    "pnu": r"pnu|필지고유번호|토지고유번호|^고유번호$",
    "bldg": r"건물관리번호|관리건축물대장|건축물대장\s*pk|mgm_bldrgst|bld_?mgt",
    "bjd_cd": r"법정동\s*코드|법정동코드|bjdong|ldong_?cd|legaldong",
    "coord": r"위도|경도|x\s*좌표|y\s*좌표|좌표\s*[xy]|^lat|^lon|latitude|longitude|wgs84",
    "bizno": r"사업자\s*등록\s*번호|사업자번호|bizno|brno",
    "corpno": r"법인\s*등록\s*번호|법인번호|jurirno|crno",
    "inst_id": r"요양기관기호|ykiho|hpid|기관\s*id",
    "apt": r"단지\s*코드|kapt|단지고유번호",
    "adm_cd": r"행정동\s*코드|행정구역\s*코드|시군구\s*코드|행정기관\s*코드|adm_?cd|sgg_?cd|signgu",
    "address": r"도로명\s*주소|지번\s*주소|소재지.*주소|^주소$|주소$|address|addr",
}
KRE = {n: re.compile(p, re.I) for n, p in KEYS.items()}
SPATIAL = {"pnu", "bldg", "bjd_cd", "coord"}
ENTITY = {"bizno", "corpno", "inst_id", "apt"}
NOISE = re.compile(r"홈페이지|게시판|민원|예산|결산|채용|직원|교육자료|홍보|보도자료|연구보고서|업무추진비|회의록|인사|청렴|"
                   r"설문|만족도|통계|연보|실적|건수|월별|연도별|분기별|현황\s*통계", re.I)
LOCAL_AGENCY = re.compile(r"(?:시|군|구|도)$|특별자치|광역시|특별시")
CENTRAL_LIKE = re.compile(r"부$|청$|처$|원$|공단|공사|위원회|진흥|센터")


def keys_of(cols: str) -> list[str]:
    parts = [x.strip() for x in cols.split(",") if x.strip()]
    return [n for n, r in KRE.items() if any(r.search(p) for p in parts)]


def tier(ks: list[str]) -> str:
    s = set(ks)
    if s & SPATIAL:
        return "A"
    if s & ENTITY:
        return "B"
    if "address" in s:
        return "C"
    if "adm_cd" in s:
        return "D"
    return "E"


def family(title: str) -> str:
    t = re.sub(r"^[^_]*_", "", str(title))
    t = re.sub(r"\(\d{4}.*?\)|\d{4}년|\d{6,8}", "", t)
    return re.sub(r"\s+", "", t)


def _stem(t: str) -> str:
    """기관 이름을 뗀 제목 줄기 — '국토교통부_아파트 매매 실거래가 자료' → '아파트실거래가'."""
    t = re.sub(r"^[^_]*_", "", str(t))
    return re.sub(r"(매매|전월세|임대|상세|조회서비스|서비스|정보|자료|현황|목록|조회|_|\s)", "", t)[:8]


# 행정안전부 인허가(LOCALDATA) 업종별 API — 형식이 모두 같다 (검증: 일반음식점 15154916 · 체력단련장 15155077)
LOCALDATA = re.compile(r"^행정안전부_[^_]+_.+조회\s*서비스$")


def _std_like(fam: str, std: str) -> bool:
    """자치단체 가족 이름이 표준데이터 이름과 사실상 같은가 (현황·목록·정보·위치 꼬리만 다름)."""
    if not std or std not in fam:
        return False
    rest = fam.replace(std, "", 1)
    return len(rest) <= 4 and re.fullmatch(r"(현황|목록|정보|위치|현황정보|위치현황|목록현황)?", rest) is not None


def build() -> pd.DataFrame:
    P = config.PROCESSED
    c = pd.read_parquet(P / "catalog.parquet")
    k = pd.read_parquet(P / "class.parquet")
    c = c.merge(k[["id", "sector", "subsector", "subsector_name", "admin_unit", "excluded_by"]], on="id", how="left")
    si = pd.read_parquet(P / "std_item.parquet")
    std_cols = si.groupby("std_id")["item_name"].apply(lambda s: ",".join(map(str, s)))
    c["cols"] = c["output_cols"].fillna("")
    m = c["list_type"].eq("STD") & c["std_id"].notna()
    c.loc[m, "cols"] = c.loc[m, "std_id"].astype(str).map(std_cols).fillna("")
    c["cols"] = c["cols"] + "," + c["request_vars"].fillna("")
    c["keys"] = c["cols"].map(keys_of)
    c["tier"] = c["keys"].map(tier)

    known = {f.stem.split("_")[0].split(".")[0] for f in (config.KNOWLEDGE / "datasets").rglob("*.yaml")}
    fresh = pd.to_datetime(c["modified_at"], errors="coerce") >= pd.Timestamp(FRESH_SINCE)
    raw = c["admin_unit"].fillna("").str.contains("개별")
    passed = c["excluded_by"].isna() | c["excluded_by"].eq(False)  # noqa: E712
    b = c[c["tier"].isin(list("ABC")) & ~c["id"].isin(known) & passed & fresh & (raw | c["list_type"].eq("API"))].copy()

    ag = b["agency_name"].fillna("")
    b["local"] = ag.str.contains(LOCAL_AGENCY) & ~ag.str.contains(CENTRAL_LIKE)
    b["family"] = b["title"].map(family)
    fam_n = b[b["local"]].groupby("family")["id"].transform("size")
    b["family_n"] = fam_n.reindex(b.index).fillna(1).astype(int)

    std = c[c["list_type"] == "STD"]
    std_names = {re.sub(r"\s+|표준데이터|전국", "", t): i for t, i in zip(std["title"], std["id"])}
    b["std_match"] = b.apply(lambda r: next((i for s, i in std_names.items() if r["local"] and _std_like(r["family"], s)), None), axis=1)

    ver = c[c["id"].isin(known)]
    vs = {(a, _stem(t)): i for a, t, i in zip(ver["agency_name"], ver["title"], ver["id"])}
    b["sibling_of"] = [vs.get((a, _stem(t))) if len(_stem(t)) >= 4 else None for a, t in zip(b["agency_name"], b["title"])]
    b.loc[b["title"].str.match(LOCALDATA) & b["sibling_of"].isna(), "sibling_of"] = "LOCALDATA"

    def verdict(r) -> tuple[str, str]:
        t = str(r["title"])
        if pd.notna(r["sibling_of"]):
            if r["sibling_of"] == "LOCALDATA":
                return "keep-variant", "행정안전부 인허가(LOCALDATA) 업종 API — 검증된 일반음식점·체력단련장과 같은 형식"
            return "keep-variant", f"검증된 {r['sibling_of']}의 형제 — 같은 형식"
        if NOISE.search(t):
            return "defer-noise", f"운영·통계성 제목 ({NOISE.search(t).group(0)})"
        if r["local"] and pd.notna(r["std_match"]):
            return "absorb-std", f"표준데이터 {r['std_match']}로 대체 (전국)"
        if r["local"] and r["family_n"] == 1:
            if str(r["agency_name"]).startswith("서울특별시"):
                return "review", "서울특별시 단독 — 규모가 커서 개별 검토"
            return "defer-single", "한 자치단체만 낸다 — 전국 전략에 쓰기 어렵다"
        if r["tier"] in ("A", "B") and (not r["local"] or r["family_n"] >= 5 or r["list_type"] == "STD"):
            return "keep-core", f"{r['tier']}등급 키({','.join(r['keys'])}) · 개체 단위"
        return "review", ("주소만 — 지오코딩 경로 필요" if r["tier"] == "C" else f"{r['family_n']}곳 자치단체 가족")

    vv = b.apply(verdict, axis=1, result_type="expand")
    b["verdict"], b["reason"] = vv[0], vv[1]
    # 자치단체 가족은 대표 1행으로 (검토 단위)
    b["unit"] = b.apply(lambda r: f"fam:{r['family']}" if r["local"] else r["id"], axis=1)
    rep = b.sort_values(["unit", "usage_count"], ascending=[True, False]).drop_duplicates("unit")
    members = b.groupby("unit")["id"].apply(list)
    rep = rep.assign(members=rep["unit"].map(members), sector_top=rep["sector"].fillna("?").str.split(" - ").str[0])
    cols = ["unit", "id", "title", "agency_name", "list_type", "sector", "sector_top", "subsector", "subsector_name", "tier", "keys",
            "local", "family_n", "members", "std_match", "sibling_of", "row_count", "update_cycle", "modified_at", "usage_count",
            "verdict", "reason", "url"]
    return rep[cols].reset_index(drop=True)


def summary(q: pd.DataFrame) -> str:
    t = pd.crosstab(q["sector_top"], q["verdict"]).assign(합계=lambda d: d.sum(axis=1)).sort_values("합계", ascending=False)
    lines = [f"# 2차 확대 검토 큐 (wave 2)", "",
             f"생성 {dt.date.today()} · `python -m pds.expand.wave2` · 원칙: [부문 검토 기록](../../sectors/_review_log.md)", "",
             f"검토 단위 {len(q):,} (중앙 개별 {int((~q['local']).sum()):,} · 자치단체 가족 {int(q['local'].sum()):,}) — "
             f"키 등급 A {int((q.tier == 'A').sum()):,} · B {int((q.tier == 'B').sum()):,} · C {int((q.tier == 'C').sum()):,}", "",
             "## 1차 판정", "", "| 판정 | 단위 | 뜻 |", "|---|---:|---|"]
    meaning = {"keep-variant": "검증된 데이터의 형제 — 형식이 같아 바로 검증", "keep-core": "핵심 원장(키 있음·개체 단위·전국성)",
               "review": "부문 검토에서 판단 (주소만 · 소수 자치단체 · 서울)", "absorb-std": "전국 표준데이터로 대체",
               "defer-single": "한 자치단체만 — 미룸", "defer-noise": "운영·통계성 — 미룸"}
    for v, n in q["verdict"].value_counts().items():
        lines.append(f"| `{v}` | {n:,} | {meaning.get(v, '')} |")
    lines += ["", "## 부문별", "", "| 부문 | " + " | ".join(t.columns) + " |", "|---|" + "---:|" * len(t.columns)]
    for s, r in t.iterrows():
        lines.append(f"| {s} | " + " | ".join(f"{int(x):,}" for x in r) + " |")
    return "\n".join(lines) + "\n"


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    q = build()
    OUT.mkdir(parents=True, exist_ok=True)
    q.assign(keys=q["keys"].map(",".join), members=q["members"].map(",".join)).to_parquet(OUT / "queue.parquet", index=False)
    (OUT / "README.md").write_text(summary(q), encoding="utf-8")
    print(summary(q))


if __name__ == "__main__":
    main()
