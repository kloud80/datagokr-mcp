"""1차 랭킹 점수 (BUILD-PLAN §1.3). 메타만으로 계산, 검증 전.

prelim_score = 0.30·usage + 0.05·designation + 0.15·api_kind + 0.15·granularity + 0.10·linkable
             + 0.05·coverage + 0.10·novelty + 0.05·freshness + 0.05·meta_fill

가중치 변경 이력 (2026-09-28)
1) 초안 0.30/0.20/0.20/0.15/0.15에서 국가중점이 상위 1,000개의 99%를 차지 → 지정 0.05, 활용 백분위.
2) 구름 결정: 통계·집계보다 건별 원천(최소 단위), 전수 제공, 연계 키 보유를 높게 — 모든 분야 공통.
   granularity·coverage·linkable 추가 (판정: pds/rank/shape.py).
3) 구름 결정: "LLM이 이미 아는가" — 이미 학습된 내용(법령 본문 등)보다 빨리 올라오는 세부 원장을 높게. novelty 0.10 추가,
   freshness·meta_fill 0.10→0.05.
"""
from __future__ import annotations

import math
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from pds import config

WEIGHTS = {"usage": 0.30, "designation": 0.05, "api_kind": 0.15, "granularity": 0.15, "linkable": 0.10,
           "coverage": 0.05, "novelty": 0.10, "freshness": 0.05, "meta_fill": 0.05}

# 시의성·희소성 = "LLM이 이미 아는가"의 반대 (구름 2026-09-28). 세부 부문 판정(subsectors.yaml novelty)이 우선,
# 없으면 갱신 주기로 추정. 법령 본문처럼 이미 학습된 내용은 낮게, 당일 올라오는 의안·판례·공고는 높게.
NOVELTY_LEVEL = {"high": 1.0, "medium": 0.6, "low": 0.2}
NOVELTY_BY_CYCLE = {"일간": 1.0, "주간": 0.9, "월간": 0.8, "수시": 0.6, "분기": 0.5, "반기": 0.45, "연간": 0.4}

# ---------------------------------------------------------------- api_kind

# 외부 링크는 깎지 않는다 (2026-09-28 결정): 포털 밖 사이트(VWorld 등)에서 키를 받아 연결하면 되므로
# 불편할 뿐 쓸 수 있는 데이터다. 불편함은 점수가 아니라 전략 응답의 access.channel="external"로 드러낸다.
#   API_LINK  = 목록유형 API + API유형 LINK (외부 사이트 API) → REST와 같은 1.0
#   FILE_LINK = 파일을 기관 사이트에서 받음 → FILE과 같은 0.4
# SOAP 0.8: 호출은 되지만 다루기 불편.
API_KIND_SCORE = {"REST": 1.0, "API_LINK": 1.0, "SOAP": 0.8, "STD": 0.7, "FILE": 0.4, "FILE_LINK": 0.4}


def api_kind(list_type: str, api_type: str | None, provide_form: str | None) -> str:
    if list_type == "API":
        return {"REST": "REST", "SOAP": "SOAP"}.get(api_type or "", "API_LINK")
    if list_type == "STD":
        return "STD"
    if isinstance(provide_form, str) and "기관자체" in provide_form:
        return "FILE_LINK"
    return "FILE"


# ---------------------------------------------------------------- designation

def designation(national_key: bool, standard: bool, in_top100: bool) -> float:
    if national_key:
        return 1.0
    if in_top100:
        return 0.8
    if standard:
        return 0.6
    return 0.0


def load_top100() -> set[str]:
    """data/ref/top100_ids.txt (한 줄에 목록키 하나). 없으면 빈 집합."""
    p: Path = config.REF / "top100_ids.txt"
    if not p.exists():
        return set()
    return {line.strip() for line in p.read_text(encoding="utf-8").splitlines() if line.strip() and not line.startswith("#")}


# ---------------------------------------------------------------- usage

def usage_scores(usage: pd.Series, views: pd.Series, kind: pd.Series) -> pd.Series:
    """활용신청(다운로드)+조회수의 kind 그룹 안 백분위 (0~1).

    kind마다 규모가 다르다(파일 다운로드 수 ≫ API 활용신청 수) → 그룹 안에서만 비교.
    kind는 REST/SOAP/API_LINK를 API로 묶고 FILE/FILE_LINK를 FILE로 묶는다.
    min-max(p99 컷)는 상위 REST 88건이 1.0으로 포화돼 상위권을 가르지 못해 백분위로 바꿨다.
    """
    x = np.log1p(usage.fillna(0).astype(float) + views.fillna(0).astype(float))
    group = kind.map({"REST": "API", "SOAP": "API", "API_LINK": "API", "STD": "STD",
                      "FILE": "FILE", "FILE_LINK": "FILE"})
    return x.groupby(group).rank(pct=True, method="average")


# ---------------------------------------------------------------- freshness

CYCLE_DAYS = {"일간": 1, "주간": 7, "월간": 31, "분기": 92, "반기": 183, "연간": 366}
IRREGULAR_HALF_LIFE_DAYS = 365


def _is_date(v) -> bool:
    # NaT는 datetime(=date 하위클래스) 인스턴스라 isinstance만으로 걸러지지 않는다
    return isinstance(v, date) and not pd.isna(v)


def freshness(modified_at: date | None, update_cycle: str | None, next_reg_date: date | None,
              snapshot: date) -> float:
    """수정일이 선언된 주기를 지키는가.

    - 주기 명시: 경과일/주기 ≤ 1.5 → 1.0, 이후 선형 감소해 4.0배에서 0.
      (일·주 단위 주기는 포털 수정일이 매번 바뀌지 않으므로 최소 허용 경과를 31일로 둔다)
    - 수시·미기재: 반감기 365일 지수 감쇠.
    - 차기 등록 예정일이 스냅샷보다 30일 이상 지났으면 ×0.5 (약속한 갱신을 안 함).
    - 주의: API의 수정일은 메타 수정일이지 데이터 갱신일이 아니다. 실측 주기는 Phase 2에서 잰다.
    """
    if not _is_date(modified_at):
        return 0.0
    age = max((snapshot - modified_at).days, 0)
    cycle = CYCLE_DAYS.get(update_cycle or "")
    if cycle:
        ratio = age / max(cycle, 31)
        score = 1.0 if ratio <= 1.5 else max(0.0, 1.0 - (ratio - 1.5) / 2.5)
    else:
        score = math.pow(0.5, age / IRREGULAR_HALF_LIFE_DAYS)
    if _is_date(next_reg_date) and (snapshot - next_reg_date).days > 30:
        score *= 0.5
    return round(score, 4)


# ---------------------------------------------------------------- meta_fill

def meta_fill(kind: str, request_vars, output_cols, legal_basis, data_limit) -> float:
    """요청변수·출력결과·보유근거·한계 채움률. 요청변수는 API(REST/SOAP)에만 해당하므로 그 외엔 분모에서 뺀다."""
    fields = [output_cols, legal_basis, data_limit]
    if kind in ("REST", "SOAP"):
        fields.append(request_vars)
    filled = sum(1 for f in fields if isinstance(f, str) and f.strip())
    return filled / len(fields)


# ---------------------------------------------------------------- 합산

def weighted_mean(out: pd.DataFrame) -> pd.Series:
    """NaN(판단 불가) 항목은 분자·분모에서 모두 뺀다."""
    num = sum(WEIGHTS[k] * out[f"s_{k}"].fillna(0) for k in WEIGHTS)
    den = sum(WEIGHTS[k] * out[f"s_{k}"].notna() for k in WEIGHTS)
    return num / den


def score(df: pd.DataFrame, cls: pd.DataFrame, snapshot: date) -> pd.DataFrame:
    top100 = load_top100()
    out = pd.DataFrame({"id": df["id"]})
    out["api_kind_label"] = [api_kind(lt, at, pf) for lt, at, pf in
                             zip(df["list_type"], df["api_type"], df["provide_form"])]
    out["s_usage"] = usage_scores(df["usage_count"], df["view_count"], out["api_kind_label"]).round(4)
    out["s_designation"] = [designation(n, s, i in top100) for n, s, i in
                            zip(df["national_key"], df["standard"], df["id"])]
    out["s_api_kind"] = out["api_kind_label"].map(API_KIND_SCORE)
    out["s_freshness"] = [freshness(m, c, n, snapshot) for m, c, n in
                          zip(df["modified_at"], df["update_cycle"], df["next_reg_date"])]
    # 이벤트 주기(선거 등): 이벤트 때만 생성되고 확정 후 불변 → 주기·경과일로 재지 않는다.
    # 마지막 이벤트 이후 수정됐으면 1.0, 아니면 0.7 (구름 결정 2026-09-28, subsectors.yaml cycle: event)
    event = cls["cycle_override"].eq("event").to_numpy()
    if event.any():
        last = pd.to_datetime(cls["last_event"], errors="coerce").dt.date.to_numpy()
        mod = df["modified_at"].to_numpy()
        out.loc[event, "s_freshness"] = [1.0 if _is_date(m) and _is_date(l) and m >= l else 0.7
                                          for m, l in zip(mod[event], last[event])]
    out["s_meta_fill"] = [round(meta_fill(k, r, o, l, d), 4) for k, r, o, l, d in
                          zip(out["api_kind_label"], df["request_vars"], df["output_cols"],
                              df["legal_basis"], df["data_limit"])]
    out["s_novelty"] = [NOVELTY_LEVEL[n] if isinstance(n, str) and n in NOVELTY_LEVEL else NOVELTY_BY_CYCLE.get(c, 0.5)
                        for n, c in zip(cls["novelty"], df["update_cycle"])]
    out["novelty_ev"] = [f"subsector:{n}" if isinstance(n, str) else f"cycle:{c}" if isinstance(c, str) else "default"
                         for n, c in zip(cls["novelty"], df["update_cycle"])]
    from pds.rank.shape import coverage, granularity, linkable
    g = [granularity(t, o) for t, o in zip(df["title"], df["output_cols"])]
    out["s_granularity"] = [x[0] for x in g]
    out["granularity_ev"] = [x[1] for x in g]
    # 세부 부문이 "집계여도 핵심"으로 판정한 경우(예: 주민등록 인구) 입도 하한을 둔다 (subsectors.yaml granularity_floor)
    floor = pd.to_numeric(cls["granularity_floor"], errors="coerce").to_numpy()
    raised = [f == f and f is not None and gv < f for gv, f in zip(out["s_granularity"], floor)]
    out.loc[raised, "s_granularity"] = floor[raised]
    out.loc[raised, "granularity_ev"] = out.loc[raised, "granularity_ev"] + " → floor(subsector)"
    c = [coverage(t, d, k, r) for t, d, k, r in
         zip(df["title"], df["description"], out["api_kind_label"], df["row_count"])]
    out["s_coverage"] = [x[0] for x in c]
    out["coverage_ev"] = [x[1] for x in c]
    lk = [linkable(t, o, r) for t, o, r in zip(df["title"], df["output_cols"], df["request_vars"])]
    out["s_linkable"] = [x[0] for x in lk]
    out["linkable_ev"] = [x[1] for x in lk]
    # 외부 링크 API는 포털에 컬럼 정보가 없고, 포털 수정일은 외부 사이트 데이터의 갱신과 무관하다.
    # 0점(깎임)도 재정규화(면제 → 상위권 독식, 2026-09-28 확인)도 아니게, 판단 불가 항목에는
    # 포털 REST API의 중앙값을 넣는다 = "평균적인 API"로 취급. 원값이 없었다는 표시는 imputed 컬럼에 남긴다.
    external = out["api_kind_label"].eq("API_LINK")
    rest = out["api_kind_label"].eq("REST") & cls["excluded_by"].isna().to_numpy()
    out["imputed"] = None
    for k in ("s_freshness", "s_meta_fill"):
        out.loc[external, k] = round(float(out.loc[rest, k].median()), 4)
    # 컬럼 정보가 없는 외부 API는 입도·연계 키도 판단 불가 → 같은 방식으로 REST 중앙값
    ext_nocols = external & out["granularity_ev"].eq("no-cols")
    for k in ("s_granularity", "s_linkable"):
        out.loc[ext_nocols, k] = round(float(out.loc[rest, k].median()), 4)
    out.loc[external, "imputed"] = "freshness,meta_fill"
    out.loc[ext_nocols, "imputed"] = "freshness,meta_fill,granularity,linkable"
    out["prelim_score"] = weighted_mean(out).round(4)

    # 순위는 프로젝트 대상(제외 규칙에 안 걸린 것)끼리만 매긴다. 제외 데이터는 순위 없음(<NA>)
    ranked = out.merge(cls[["id", "sector", "agency_tier", "admin_unit", "excluded_by"]], on="id")
    live = ranked["excluded_by"].isna()
    r = ranked[live]
    for col, grp in (("rank_overall", None), ("rank_in_sector", ["sector"]),
                     ("rank_in_sector_tier", ["sector", "agency_tier"])):
        rk = (r["prelim_score"] if grp is None else r.groupby(grp)["prelim_score"]).rank(ascending=False, method="min")
        out[col] = pd.Series(rk, index=r.index).reindex(out.index).astype("Int64")
    out["top100_available"] = bool(top100)
    return out
