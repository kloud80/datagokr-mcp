"""Phase 1 랭킹 정리 문서 (Markdown) → reports/phase1_ranking.md

평가 방법·결정 근거와 정책분야별 결과(정책영역 요약, 분야 상위, 영역별 상위)를 한 파일에 담는다.
데이터마다 '근거' 열은 점수 구성요소를 사람이 읽는 말로 푼 것.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd

from pds import config
from pds.rank.score import API_KIND_SCORE, WEIGHTS

FIELD_TOP = 15
AREA_TOP = 3
KIND_LABEL = {"REST": "REST API", "API_LINK": "외부 API", "SOAP": "SOAP", "STD": "표준데이터",
              "FILE": "파일", "FILE_LINK": "외부 파일"}
EXTERNAL = {"API_LINK", "FILE_LINK"}


def _load() -> pd.DataFrame:
    p = config.PROCESSED
    return (pd.read_parquet(p / "catalog.parquet")
            .merge(pd.read_parquet(p / "class.parquet"), on="id")
            .merge(pd.read_parquet(p / "score.parquet"), on="id")
            .query("excluded_by.isna()", engine="python"))  # 프로젝트 제외 규칙 (knowledge/sectors/exclusions.yaml)


def _cell(v) -> str:
    return str(v).replace("|", "／").replace("\n", " ") if v is not None else ""


def reason(r) -> str:
    """점수 구성요소 → 한 줄 근거."""
    parts = []
    parts.append(f"활용 상위 {max(1, round((1 - r.s_usage) * 100))}%")
    g = r.s_granularity
    parts.append("건별 원천" if g >= 0.85 else "집계·통계" if g <= 0.3 else "입도 불명")
    if r.s_novelty >= 0.9:
        parts.append("시의성 높음")
    elif r.s_novelty <= 0.2:
        parts.append("이미 알려진 내용")
    if r.s_coverage <= 0.3:
        parts.append("번호 조회형(전수 불가)" if r.coverage_ev == "lookup-only" else "표본·일부")
    if isinstance(r.linkable_ev, str) and r.linkable_ev != "none" and "linkable" not in str(r.imputed):
        parts.append(f"연계키 {r.linkable_ev}")
    if r.national_key:
        parts.append("국가중점")
    elif r.standard:
        parts.append("제공표준")
    kind = r.api_kind_label
    if kind in EXTERNAL:
        parts.append("외부 사이트 연결")
    if isinstance(r.imputed, str):
        parts.append("갱신·메타는 판단 불가(REST 중앙값)")
    else:
        f = r.s_freshness
        parts.append("갱신 양호" if f >= 0.8 else "갱신 보통" if f >= 0.4 else "갱신 지연")
        parts.append(f"메타 채움 {r.s_meta_fill:.0%}")
    if isinstance(r.approval_dev, str):
        parts.append({"auto": "자동승인", "review": "심의승인"}[r.approval_dev])
    return " · ".join(parts)


def _dataset_table(df: pd.DataFrame, rank_col: str) -> list[str]:
    out = ["| 순위 | 전체 | 데이터 | 기관 | 유형 | 행정단위 | 점수 | 활용 | 지정 | 유형 | 원천 | 연계 | 전수 | 갱신 | 메타 | 근거 |",
           "| ---: | ---: | --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |"]
    for k, r in enumerate(df.itertuples(), 1):
        title = f"[{_cell(r.title)}](https://www.data.go.kr/data/{r.id}/" \
                f"{'fileData' if r.api_kind_label in ('FILE', 'FILE_LINK', 'STD') else 'openapi'}.do)"
        out.append(
            f"| {k} | {r.rank_overall:,} | {title} | {_cell(r.agency_name)} | {KIND_LABEL[r.api_kind_label]} | "
            f"{r.admin_unit} | {r.prelim_score:.3f} | {r.s_usage:.2f} | {r.s_designation:.2f} | "
            f"{r.s_api_kind:.2f} | {r.s_granularity:.2f} | {r.s_linkable:.2f} | {r.s_coverage:.2f} | "
            f"{r.s_freshness:.2f} | {r.s_meta_fill:.2f} | {reason(r)} |")
    return out


FIELD_DIR = "phase1_fields"


def _field_file(no: int, field: str) -> str:
    return f"{no:02d}_{field}.md"


def _areas(g: pd.DataFrame) -> pd.DataFrame:
    return (g.groupby("sector").agg(n=("id", "size"), avg=("prelim_score", "mean"))
            .sort_values("avg", ascending=False))


def _field_summary(g: pd.DataFrame) -> list[str]:
    from pds.rank.classify import ADMIN_UNITS, AGENCY_TIERS
    ga = g["api_kind_label"].isin(["REST", "API_LINK", "SOAP"])
    L = [
        f"- 데이터 {len(g):,}건 (API {int(ga.sum()):,} · 외부 API {int((g['api_kind_label'] == 'API_LINK').sum()):,}) · "
        f"국가중점 {int(g['national_key'].sum()):,} · 평균 점수 {g['prelim_score'].mean():.3f}",
        f"- 유형: {_dist(g['api_kind_label'].map(KIND_LABEL), [KIND_LABEL[k] for k in KIND_LABEL])}",
        f"- 기관 계층: {_dist(g['agency_tier'], list(AGENCY_TIERS))}",
        f"- 행정단위: {_dist(g['admin_unit'], list(ADMIN_UNITS))}",
        f"- 주요 기관(API 수): " + " · ".join(
            f"{a} {c}" for a, c in g.loc[ga, "agency_name"].value_counts().head(6).items()),
        "",
        "**정책영역**",
        "",
        "| 정책영역 | 데이터 | API | 국가중점 | 평균 점수 | 영역 1위 |",
        "| --- | ---: | ---: | ---: | ---: | --- |",
    ]
    for a, st in _areas(g).iterrows():
        ag = g[g["sector"] == a]
        L.append(f"| {a.split(' - ', 1)[-1]} | {int(st.n):,} | "
                 f"{int(ag['api_kind_label'].isin(['REST', 'API_LINK', 'SOAP']).sum()):,} | "
                 f"{int(ag['national_key'].sum()):,} | {st.avg:.3f} | {_cell(ag.iloc[0]['title'])} |")
    return L


def _full_table(g: pd.DataFrame) -> list[str]:
    """정책영역 안 전체 목록. 링크 대신 목록키(포털 URL: data.go.kr/data/{목록키}/openapi.do|fileData.do)."""
    L = ["| # | 전체 | 목록키 | 데이터 | 기관 | 계층 | 유형 | 행정단위 | 점수 | 활용수 | 활용 | 지정 | 유형 | 원천 | 연계 | 전수 | 갱신 | 메타 | 수정일 | 근거 |",
         "| ---: | ---: | --- | --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |"]
    for k, r in enumerate(g.itertuples(), 1):
        mod = r.modified_at.isoformat() if hasattr(r.modified_at, "isoformat") and not pd.isna(r.modified_at) else ""
        use = "" if pd.isna(r.usage_count) else f"{int(r.usage_count):,}"
        L.append(f"| {k} | {r.rank_overall:,} | {r.id} | {_cell(r.title)} | {_cell(r.agency_name)} | {r.agency_tier} | "
                 f"{KIND_LABEL[r.api_kind_label]} | {r.admin_unit} | {r.prelim_score:.3f} | {use} | "
                 f"{r.s_usage:.2f} | {r.s_designation:.2f} | {r.s_api_kind:.2f} | {r.s_granularity:.2f} | "
                 f"{r.s_linkable:.2f} | {r.s_coverage:.2f} | {r.s_freshness:.2f} | "
                 f"{r.s_meta_fill:.2f} | {mod} | {reason(r)} |")
    return L


def _render_field_file(path: Path, no: int, field: str, g: pd.DataFrame, areas: pd.DataFrame, snap) -> None:
    L = [
        f"# 5.{no} {field} — 전체 목록 ({len(g):,}건)",
        "",
        f"- 기준 스냅샷 {snap} · 메타 기반 1차 점수 (방법·결정 근거는 [../phase1_ranking.md](../phase1_ranking.md) §2~4)",
        "- `#`=정책영역 안 순위, `전체`=96,110건 중 순위. `활용·지정·유형·갱신·메타`=구성요소 점수(0~1).",
        "- 포털 링크: `https://www.data.go.kr/data/{목록키}/openapi.do` (API) · `fileData.do` (파일·표준)",
        "",
        "## 요약",
        "",
    ]
    L += _field_summary(g)
    L += [""]
    for i, a in enumerate(areas.index, 1):
        ag = g[g["sector"] == a]
        L += [f"## {i}. {a.split(' - ', 1)[-1]} ({len(ag):,}건)", ""]
        if ag["subsector"].notna().any():
            depth_ko = {"front": "앞", "back": "뒤", "hold": "보류", "system": "시스템 자체"}
            subs = ag.groupby("subsector", sort=False).agg(n=("id", "size"), best=("prelim_score", "max"),
                                                            sname=("subsector_name", "first"),
                                                            depth=("subsector_depth", "first"))
            subs = subs.sort_values(["depth", "best"], key=lambda c: c.map({"front": 0, "system": 1, "hold": 2, "back": 3})
                                    if c.name == "depth" else -c)
            L += ["| 세부 부문 | 깊이 | 건수 |", "| --- | --- | ---: |"]
            L += [f"| {r.sname} (`{k}`) | {depth_ko.get(r.depth, r.depth)} | {r.n:,} |" for k, r in subs.iterrows()]
            L += [""]
            for k, r in subs.iterrows():
                L += [f"### {i}.{list(subs.index).index(k) + 1} {r.sname} (`{k}`) — {depth_ko.get(r.depth, r.depth)} ({r.n:,}건)", ""]
                L += _full_table(ag[ag["subsector"] == k])
                L += [""]
        else:
            L += _full_table(ag)
            L += [""]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(L), encoding="utf-8")


def _dist(s: pd.Series, order=None) -> str:
    vc = s.value_counts()
    keys = [k for k in (order or vc.index) if k in vc]
    return " · ".join(f"{k} {vc[k]:,}" for k in keys)


def render(out: Path | None = None) -> Path:
    from pds.rank.classify import ADMIN_UNITS, AGENCY_TIERS

    df = _load().sort_values("rank_overall")
    for stale in (config.REPORTS / FIELD_DIR).glob("*.md"):  # 분야 순서가 바뀌면 번호가 달라지므로 비우고 다시 쓴다
        stale.unlink()
    snap = df["snapshot_date"].iloc[0]
    n = len(df)
    api = df["api_kind_label"].isin(["REST", "API_LINK", "SOAP"])
    top = df.head(100)
    L: list[str] = []
    w = WEIGHTS

    L += [
        "# PDS Phase 1 — 공공데이터 핵심 데이터 랭킹 (메타 기반 1차 평가)",
        "",
        f"- 기준 스냅샷: 공공데이터포털 목록개방현황 **{snap}** · 대상 **{n:,}건**",
        f"- 생성: {datetime.now():%Y-%m-%d %H:%M} · 재생성: `python -m pds build && python -m pds report-md`",
        "- 성격: 메타만으로 매긴 **검증 전 1차 순위**. 실제 호출·다운로드 검증은 Phase 2에서 한다.",
        "- 대화형 리포트: `reports/phase1_ranking.html` (체크·메모·targets.json 내보내기)",
        "",
        "## 1. 한눈에",
        "",
        f"| 구분 | 값 |",
        f"| --- | --- |",
        f"| 전체 | {n:,} |",
        f"| 유형 | {_dist(df['api_kind_label'].map(KIND_LABEL), [KIND_LABEL[k] for k in KIND_LABEL])} |",
        f"| API 중 외부 사이트 연결 | {int((df['api_kind_label'] == 'API_LINK').sum()):,} / {int(api.sum()):,} |",
        f"| 국가중점 | {int(df['national_key'].sum()):,} (API {int(df.loc[api, 'national_key'].sum()):,}) |",
        f"| 기관 계층 | {_dist(df['agency_tier'], list(AGENCY_TIERS))} |",
        f"| 행정단위(추정) | {_dist(df['admin_unit'], list(ADMIN_UNITS))} |",
        f"| 상위 100 구성 | {_dist(top['api_kind_label'].map(KIND_LABEL))} · 국가중점 {int(top['national_key'].sum())} |",
        "",
        "## 2. 평가 방법",
        "",
        "### 2.1 입력",
        "",
        "| 목록키 | 데이터 | 쓰임 |",
        "| --- | --- | --- |",
        "| 15062804 | 공공데이터포털 목록개방현황 | 주 테이블. 분류체계(BRM), 기관, 유형, 활용·조회수, 국가중점·표준 여부, 승인유형, 트래픽, 보유근거, 한계 |",
        "| 15121937 | 공공데이터포털 목록 메타정보 | 요청변수·출력결과(컬럼명) → 행정단위 추정, 메타 채움 |",
        "| 15156444 | 공공데이터 제공 표준 | 표준데이터 300종의 항목 정의 → 표준데이터의 출력 컬럼 |",
        "",
        "### 2.2 3축 분류",
        "",
        "| 축 | 방법 | 한계 |",
        "| --- | --- | --- |",
        "| 부문 | BRM 분류체계 그대로(정책분야 16 · 정책영역 74). 병합·분할은 다음 단계 대화에서 확정 | 대기능(3레벨)은 벌크 메타에 없음 |",
        "| 기관 계층 | 행정표준기관코드 앞자리 + 기관명 (1=중앙, 3~6=지자체(광역/기초는 이름으로), B=공공기관, 교육청은 이름) | 대학·센터 등 소수는 '기타' |",
        "| 행정단위 | 컬럼명 토큰 규칙으로 가장 세밀한 공간 단위 추정: 필지·건물 > 개별(주소·좌표) > 읍면동 > 시군구 > 시도 > 전국·비공간. 컬럼 근거=high, 제목 근거=medium, 컬럼 정보 없음=low | low {:,}건은 추정 불가 → LLM 보정 예정 |".format(
            int((df['admin_unit_conf'] == 'low').sum())),
        "",
        "### 2.3 점수",
        "",
        "```",
        "prelim_score = " + " + ".join(f"{v:g}·{k}" for k, v in w.items()),
        "```",
        "",
        "| 항목 | 가중치 | 계산 | 근거 |",
        "| --- | ---: | --- | --- |",
        f"| usage 활용 | {w['usage']} | (활용신청·다운로드 + 조회수)의 log를 유형 그룹(API/STD/FILE) 안 **백분위**로 | 규모가 다른 유형끼리 섞지 않음. min-max는 상위권이 1.0으로 포화돼 백분위로 바꿈 |",
        f"| designation 지정 | {w['designation']} | 국가중점 1.0 / AI·고가치 Top100 0.8 / 제공표준 0.6 / 없음 0 | 품질관리 약속의 신호지만 기관 단위로 몰려 있어 **동점 구분 수준**으로만 반영. Top100 목록은 아직 미반영 |",
        f"| api_kind 유형 | {w['api_kind']} | " + " / ".join(f"{KIND_LABEL[k]} {v:g}" for k, v in API_KIND_SCORE.items()) + " | API 우선 원칙. 외부 연결은 깎지 않음 |",
        f"| freshness 갱신 | {w['freshness']} | 명시 주기: 경과일/주기 ≤1.5배 → 1, 4배에서 0. 수시·미기재: 반감기 365일. 차기 등록 예정일 30일 초과 경과 시 ×0.5 | 포털 수정일 기준. API는 메타 수정일이라 실제 갱신은 Phase 2에서 실측 |",
        f"| meta_fill 메타 채움 | {w['meta_fill']} | 출력결과·보유근거·데이터 한계(+API는 요청변수) 채움률 | 설명이 충실할수록 도시에 작성·연계가 쉬움 |",
        f"| granularity 건별 원천 | {w['granularity']} | 출력 컬럼에 개체명·관리번호·주소/좌표 → 1.0(건별) · 수치 컬럼(건수·합계·비율…) 비중 30%↑ → 0.1(집계) · 제목에 통계/집계/실적/○○별 → 0.25~0.3 · 판단 불가 0.5 | 통계보다 최소 단위 원천이 재가공·연계에 유리 (2026-09-28 구름) |",
        f"| linkable 연계 키 | {w['linkable']} | 사업자번호·행정구역코드·PNU·건물키 0.4, 기관코드·표준분류코드 0.3, 업무번호·주소·좌표 0.2, 우편번호 0.1 합산(최대 1) | 다른 데이터와 붙일 키가 있어야 전략(연계)이 된다 |",
        f"| coverage 전수 | {w['coverage']} | 전국/전체/목록/표준 또는 1,000행 이상 → 1.0 · 기본 0.8 · 표본·일부 또는 번호를 알아야만 조회(진위확인·계약과정통합 등) → 0.3 | 전체를 뽑을 수 있어야 원천으로 쓴다 |"
        f"| novelty 시의성 | {w['novelty']} | 세부 부문 판정(high 1.0 · medium 0.6 · low 0.2), 없으면 갱신 주기(일간 1.0 … 연간 0.4) | \"LLM이 이미 아는가\" — 법령 본문처럼 학습된 내용보다 당일 올라오는 의안·판례·공고가 가치 (2026-09-28 구름) |",
        "",
        "## 3. 결정 기록 (2026-09-28)",
        "",
        "| # | 결정 | 이유 | 효과 |",
        "| --- | --- | --- | --- |",
        "| 1 | **외부 링크 데이터는 점수를 깎지 않는다** (외부 API = REST와 같은 1.0, 외부 파일 = 파일과 같은 0.4) | 포털엔 목록만 있고 실제는 기관 사이트(VWorld 등)에 있어도, 가서 연결하면 쓸 수 있다. 불편함은 전략 응답의 `access.channel=\"external\"`과 접근 절차로 드러낸다 (BUILD-PLAN §9) | 연속지적도(API 활용 1위) 8,698위 → {:,}위 |".format(
            int(df.loc[df["title"] == "국토교통부_연속지적도", "rank_overall"].iloc[0])),
        "| 2 | 외부 API의 갱신·메타 채움은 **판단 불가 → 포털 REST API 중앙값 대입** | 포털에 컬럼 정보가 없고 포털 수정일은 외부 데이터 갱신과 무관. 0점은 부당한 감점, 항목 제외(재정규화)는 상위 100 중 76개 독식으로 과보정 | 외부 API = '관리 상태는 보통인 API'로 취급. `imputed` 컬럼에 표시 |",
        "| 3 | **국가중점 가중치 0.20 → 0.05, 활용 0.30 → 0.40(백분위)**, 갱신·메타 0.15 → 0.175 | 초안에서 국가중점이 상위 1,000개의 99%를 차지(사실상 입장 자격). 지정이 기관 시리즈 단위로 몰림(행안부 341·식약처 290·국회사무처 275건), 활용 점수가 상위권에서 포화 | 상위 100 국가중점 100% → {:.0%}. 단기예보 2,073위 → {:,}위 |".format(
            top["national_key"].mean(), int(df.loc[df["title"] == "기상청_단기예보 조회서비스", "rank_overall"].iloc[0])),
        "| 5 | **건별 원천·연계 키·전수 축 추가** (원천 0.15, 연계 0.10, 전수 0.05). 활용 0.40→0.30, 유형 0.20→0.15, 갱신·메타 0.175→0.10 | 통계·기간·지역 집계보다 건별 원천(사전규격 한 건, 계약 한 건, 물품 하나)이 쓸모 있고, 전수가 나오고 연계 키가 있으면 더 좋다 — 모든 분야 공통 (구름) | 상위 100 중 집계형 13 → 0. 조달청 통계 445위 → 수천 위 |",
        "| 4 | 임베딩은 회사 개발 DB(pgvector 미설치)에 두지 않고 별도 저장 | 공용 개발 DB에 확장 설치는 과함 | Phase 3에서 저장소 결정 |",
        "",
        "## 4. 알려진 한계",
        "",
        "- 메타 기반 순위다. 수정일·주기·컬럼은 포털 신고값이고 실제와 다를 수 있다 → Phase 2 실측으로 교정.",
        "- 외부 API 4,778건 모두 포털 승인유형 값은 있고 트래픽 값은 없다. 실제로 키를 어디서 받는지는 Phase 2에서 확인.",
        "- 행정단위는 규칙 추정. 컬럼 정보 없는 건은 '전국·비공간(low)'로 표시돼 있을 뿐 실제 전국 데이터라는 뜻이 아니다.",
        "- 보유근거(88% 공란)·데이터 한계(95% 공란)가 대부분 비어 있어 메타 채움 점수의 변별력이 낮다.",
        "- 부문은 포털이 등록한 BRM 분류를 그대로 썼다. '공공행정 - 일반행정'이 {:,}건으로 사실상 미분류 묶음이고, 아파트 실거래가 시리즈도 여기 들어가 있다 → 부문 확정 대화에서 재배치.".format(
            int((df["sector"] == "공공행정 - 일반행정").sum())),
        "- AI·고가치 Top 100 목록 미반영 (`data/ref/top100_ids.txt`에 넣으면 반영).",
        "",
        "## 5. 정책분야별 결과",
        "",
        "이 문서엔 분야별 요약 → 정책영역 표 → 분야 상위 {} → 정책영역별 상위 {}만 싣는다.".format(FIELD_TOP, AREA_TOP),
        f"**분야별 전체 목록**(96k 전부, 정책영역별)은 `{FIELD_DIR}/` 아래 분야 파일에 있다. 한 파일에 다 넣으면 30MB가 넘어 열기 어렵다.",
        "점수 열은 0~1. `활용·지정·유형·갱신·메타`는 구성요소 점수, `전체`는 96k 중 전체 순위.",
        "",
    ]

    # 분야 순서: 상위 100에 많이 든 순 → 평균 점수
    fstats = df.groupby("sector_field").agg(n=("id", "size"), avg=("prelim_score", "mean"))
    fstats["in_top"] = top.groupby("sector_field").size().reindex(fstats.index).fillna(0).astype(int)
    order = fstats.sort_values(["in_top", "avg"], ascending=False).index.tolist()

    L.append("| 정책분야 | 전체 목록 | 데이터 | API | 국가중점 | 평균 점수 | 상위100 포함 | 분야 1위 |")
    L.append("| --- | --- | ---: | ---: | ---: | ---: | ---: | --- |")
    for f in order:
        g = df[df["sector_field"] == f]
        ga = g["api_kind_label"].isin(["REST", "API_LINK", "SOAP"])
        fn = _field_file(order.index(f) + 1, f)
        L.append(f"| [{f}](#5{order.index(f) + 1}-{f}) | [{fn}]({FIELD_DIR}/{fn}) | {len(g):,} | {int(ga.sum()):,} | {int(g['national_key'].sum()):,} | "
                 f"{g['prelim_score'].mean():.3f} | {fstats.loc[f, 'in_top']} | {_cell(g.iloc[0]['title'])} |")
    L.append("")

    for no, f in enumerate(order, 1):
        g = df[df["sector_field"] == f]
        areas = _areas(g)
        fname = _field_file(no, f)
        L += [f"### 5.{no} {f}", "", f"**전체 목록 ({len(g):,}건): [{FIELD_DIR}/{fname}]({FIELD_DIR}/{fname})**", ""]
        L += _field_summary(g)
        L += ["", f"**분야 상위 {FIELD_TOP}**", ""]
        L += _dataset_table(g.head(FIELD_TOP), "rank_overall")
        L += ["", f"**정책영역별 상위 {AREA_TOP}**", ""]
        for a in areas.index:
            ag = g[g["sector"] == a].head(AREA_TOP)
            L.append(f"*{a.split(' - ', 1)[-1]}*")
            L.append("")
            for r in ag.itertuples():
                L.append(f"- {r.prelim_score:.3f} · {_cell(r.title)} ({_cell(r.agency_name)}, "
                         f"{KIND_LABEL[r.api_kind_label]}, 전체 {r.rank_overall:,}위) — {reason(r)}")
            L.append("")
        L.append("")
        _render_field_file(config.REPORTS / FIELD_DIR / fname, no, f, g, areas, snap)

    out = out or (config.REPORTS / "phase1_ranking.md")
    out.write_text("\n".join(L), encoding="utf-8")
    return out
