"""현황 종합 문서 — Phase 1~2 산출물을 md 한 개로 모은다 (Phase 3 이후 전략 검토용).

원천: data/processed/*.parquet(카탈로그·분류·점수), knowledge/(결정·키·맥락·패밀리), probe/(명세·호출·셀 통계·종합), reports/.
출력: reports/PDS_현황_종합.md — 다시 돌리면 최신 상태로 재생성된다. 서술 부분(§1·§3·§9)은 이 파일 안의 문장이 원본.
"""
from __future__ import annotations

import datetime as dt
import json
import re
from collections import Counter, defaultdict

import pandas as pd
import yaml

from pds import config

ROOT = config.ROOT
K = config.KNOWLEDGE
P = ROOT / "probe"
OUT = config.REPORTS / "PDS_현황_종합.md"


def _y(path):
    return yaml.safe_load((K / path).read_text(encoding="utf-8"))


def _store(kind):
    from pds.schema import store
    return store.load(kind)


def _j(sub, dsid):
    f = P / sub / f"{dsid}.json"
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else None


def esc(v, n: int | None = None) -> str:
    s = "" if v is None or (isinstance(v, float) and pd.isna(v)) else str(v)
    s = re.sub(r"\s+", " ", s).replace("|", "\\|").strip()
    return s if n is None or len(s) <= n else s[: n - 1] + "…"


def fmt_n(v) -> str:
    try:
        return f"{int(v):,}"
    except (TypeError, ValueError):
        return ""


def table(head: list[str], rows: list[list]) -> list[str]:
    out = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    out += ["| " + " | ".join(esc(c) for c in r) + " |" for r in rows]
    return out


# ───────────────────────── 적재 ─────────────────────────
def load():
    p = config.PROCESSED
    cat = pd.read_parquet(p / "catalog.parquet")
    cls = pd.read_parquet(p / "class.parquet")
    sco = pd.read_parquet(p / "score.parquet")
    d = cat.merge(cls, on="id").merge(sco, on="id")
    d["alive"] = d["excluded_by"].isna()
    tg = json.loads((K / "targets.json").read_text(encoding="utf-8"))
    syn = {}
    for f in sorted(P.glob("synthesis_round*.json")):
        for r in json.loads(f.read_text(encoding="utf-8")):
            syn[r["id"]] = r
    summ = {}
    for f in sorted(P.glob("summary_round*.json")):
        for r in json.loads(f.read_text(encoding="utf-8")):
            summ[r["id"]] = r
    return d, tg, syn, summ


# ───────────────────────── 서술 ─────────────────────────
INTRO = """\
# PDS 현황 종합 — Phase 1·2 산출물 (Phase 3 이후 전략 검토용)

생성 {today} · `python -m pds.consolidate`로 재생성 · 원천: `data/processed/`, `knowledge/`, `probe/`, `reports/`

이 문서는 지금까지의 작업(벌크 메타 → 분류·랭킹 → 대상 확정 → 실호출 검증)을 한 곳에 모은 것이다.
표와 데이터별 상세는 파일에서 자동으로 뽑았고, 결정·논의는 `knowledge/sectors/_review_log.md`·yaml의 `reason`·`note`에서 가져왔다.

## 0. 한눈에

| 항목 | 값 |
|---|---|
| 포털 전체 데이터 (2026-07-31 목록개방현황 스냅샷) | {n_all:,}건 |
| 분류 체계 | 정책분야 {n_field} → 부문 {n_sector} → 세부 부문 {n_sub} (front {n_front}) · 부문 위 법 계층(domain) {n_domain} |
| 프로젝트 제외 (규칙 {n_excl_rule}개) | {n_excl:,}건 → 생존 {n_alive:,}건 |
| 부문 재배치 규칙 (BRM → 부문 이관) | {n_map}개 |
| 분석 대상 (targets.json, front 세부 부문마다 대표 1건) | {n_tg}건 (라운드1 {r1} · 라운드2 {r2} · 외부 {rx}) |
| 실호출·다운로드 검증 완료 | **{n_ver}건** · 실패 {n_fail} · 보류 {n_pend} |
| 전역 조인 키 원장 | {n_keys}종 · 외부 키 발급처 {n_iss}곳 |
| 맥락 연결(context) | {n_ctx}개 ({ctx_dims}) |
| 데이터 패밀리 | {n_fam} (pps-procurement) |
| 도시에·법령·레시피 | 0 (Phase 3부터) |

### 목차
1. 목표와 단계 · 2. 전체 카탈로그와 분류 체계 · 3. 분석 차원(점수 축·판정 축) · 4. 분류·관계 논의 기록 ·
5. 조인 키·키 발급처·맥락·패밀리·법 계층 · 6. 분석 대상 {n_tg}건 · 7. 검증 결과 요약 · 8. 데이터별 상세 (검증 {n_ver}건) ·
9. 검증에서 드러난 공통 사항 · 10. 미결·재검토 목록 (Phase 3 이전에 정할 것)
"""

GOAL = """\
## 1. 목표와 단계

**최종 시스템은 검색이 아니라 전략이다.** 사용자가 목표(예: "성수동 상권 변화를 월 단위로 추적")를 말하면
① 어떤 데이터를 ② 왜(법적 근거·갱신 주기·실측 결과) ③ 어떻게 연계해(조인 키·순서·함정) ④ 바로 실행 가능한 코드로
MCP 수준의 구조화된 응답을 돌려준다 (BUILD-PLAN §0).

| Phase | 내용 | 상태 (2026-09-30) |
|---|---|---|
| 1 | 벌크 메타 → 부문·기관·행정단위 랭킹 → 리포트 → 대화로 대상 확정 | **완료** — 76개 정책영역 전부 검토, 세부 부문·제외·이관 규칙 확정 |
| 1.5 | 부문 검토 중 관계 정리 (패밀리·맥락·법 계층·조인 키) | 진행 — 패밀리 1, 맥락 41, 키 58 |
| 2 | 대상별 실제 키 발급 → 호출 → 다운로드 → 셀 통계 | **라운드 1·2·외부 완료** — 검증 {n_ver}/{n_tg} |
| 3 | 도시에(데이터별 설명서: 법·행정 흐름·공개 시점·실측·연계) → 지식체계 | 시작 전 |
| 4 | 전략 프로토콜 (목표 → 지식 조회 → 구조화 응답) + 골든셋 | 시작 전 |
| 5 | 코드 생성기 (전략 JSON → 실행 가능한 Python) | 시작 전 |
| 6 | 사용자 키·로그인 MCP 서버 (`pds-keys`) | 시작 전 (Phase 2의 Playwright 활용신청 자동화가 원형) |

**변하지 않는 원칙** (BUILD-PLAN §8 + 대화에서 확정한 기준)
1. 실물 우선 — 실제 호출·다운로드·통계로 확인한 것만 도시에에 쓴다.
2. 근거 없는 추천 금지 — 전략 응답의 모든 `why`는 도시에 섹션 링크를 가진다.
3. 키는 사용자 것 — 검증용 키는 Phase 2에만 쓴다.
4. API 우선 — 파일데이터는 API가 없을 때만 도시에 대상.
5. 사람이 확정한다 — 부문·대상·도시에 승인·골든셋 정답.
6. **원천(건별) 데이터 > 집계** — 전수 조회가 되고 조인 키가 있으면 더 높게 (구름 2026-09-28).
7. **외부 링크는 깎지 않는다** — 불편함은 점수가 아니라 `access.channel = external`과 접근 절차로 드러낸다.
8. **부문 검토 기준** (구름 2026-09-29) — 분야 핵심·개체 단위·실시간은 살리고, 통계·부수적·불규칙은 우선 배제(삭제 아님, 규칙 id로 표시),
   잘못 등록된 것은 원래 부문으로 옮기고, 다른 부문과의 연결은 맥락(context)으로 기록한다.
9. **분석은 지식으로 남긴다** — 모든 검토 결과는 `knowledge/` yaml·md → `kg-build`로 그래프에 들어간다. 스키마는 새 마이그레이션으로만 바꾼다.
"""

DIMENSIONS = """\
## 3. 분석 차원

데이터 한 건을 여러 축으로 본다. **점수 축**은 랭킹(`prelim_score`)에 들어가고, **판정 축**은 분류·선정·전략 응답에서 쓴다.

### 3.1 점수 축 — `prelim_score` (메타만으로 계산, Phase 2 실측으로 교정 예정)

| 축 | 가중치 | 값 | 비고 |
|---|---:|---|---|
| usage | 0.30 | 활용신청+조회수, 형태(kind) 안 백분위 | 초안(log min-max)이 상위권에서 포화 → 백분위로 변경 |
| api_kind | 0.15 | REST·외부 API 1.0 / SOAP 0.8 / 표준데이터 0.7 / 파일 0.4 | API 우선 원칙 |
| granularity | 0.15 | 건별 원천 1.0 / 불명 0.5 / 통계·집계 0.1~0.3 | 구름 기준 "건별 원천 우선" (`pds/rank/shape.py`) |
| linkable | 0.10 | 사업자번호·행정구역코드·PNU·건물키·기관코드·표준분류코드·주소·좌표 가중 합 | 출력 컬럼명 규칙 → Phase 2 값 패턴으로 재판정 |
| novelty | 0.10 | 세부 부문 판정 high/medium/low, 없으면 갱신 주기 | "LLM이 이미 아는가"의 반대 (법제 검토 때 신설) |
| designation | 0.05 | 국가중점 1.0 / Top100 0.8 / 제공표준 0.6 | 초안 0.20에서 국가중점이 상위 1,000의 99% 독식 → 동점 구분 수준으로 낮춤 |
| coverage | 0.05 | 전수 1.0 / 기본 0.8 / 표본·일부·번호 조회형 0.3 | |
| freshness | 0.05 | 수정일·주기 | 외부 링크는 판단 불가 → 포털 REST 중앙값 대입(`imputed`) |
| meta_fill | 0.05 | 요청변수·출력결과·보유근거·한계 채움률 | 외부 링크 동일 처리 |

### 3.2 판정 축

| 축 | 값 | 쓰는 곳 |
|---|---|---|
| 부문 / 세부 부문 | BRM 정책영역 → 재배치 → 세부 부문(행정 프로세스 1개 = 근거법 1개+ = 개별 코드 1종) | 분류·선정 |
| depth | front(심층·도시에 대상) / back(뒤로) / hold(보류) / system(이 시스템 자체 문서) | 대상 선정 (front 세부 부문마다 대표 1건) |
| cycle | 기본 / `event` (선거처럼 이벤트 때 생성 후 불변 → freshness 예외) | 최신성 |
| cross_cutting | 공통 마스터 (행정표준코드·도로명주소·법령·철도망 등) | 조인 키 원장 |
| 행정단위(admin_unit) | 전국·비공간 / 시도 / 시군구 / 읍면동 / 필지·건물 / 개별(주소·좌표) | 공간 결합 가능성 |
| coverage | 전국 / 시도 / 시군구 (제공 범위) | 전수 여부 |
| 접근 경로(channel) | portal (apis.data.go.kr·포털 파일) / external (기관 사이트, 별도 키) | 전략 응답 `access` |
| 제외(excluded_by) | 규칙 id (삭제 아님, 표시만) | 랭킹·리포트에서 빠짐 |
| 맥락 차원(context) | life_context · spatial_regulation · admin_area · shared_key · shared_source · same_concept · economic | 부문을 가로지르는 연결 |
| 법 계층(domain) | 예: 국토기본법 → 계획·규제 / 개발사업 / 국토정보 / 주택 / 기반시설 | "이 데이터가 법 체계의 어느 층인가" |

### 3.3 Phase 2 실측 축 (검증에서 새로 생긴 값)

| 축 | 정의 | 원천 |
|---|---|---|
| verdict | 성공 / 파일(별도) / 응답0행 / 파라미터부족 / 키미등록 / 승인대기 / 미실행 | `probe/summary_round*.json` |
| 심의 | 자동승인 / 심의 | `probe/apply/{id}.json` |
| rows / total_count | 받은 행 / API가 말한 전체 건수 | `probe/runs` |
| 실측 키 | 컬럼명 + 값 패턴(자릿수·좌표 범위)으로 판정한 bizno·crno·pnu·bjd·sgg·sido·coord·address·ykiho·apt_complex·stock | `pds/probe/synth.py` |
| latest / lag_days | 날짜 컬럼 최대값, 오늘과의 차이 | 같음 (미래 일정·9999-12-31 같은 값은 주의) |
| 셀 통계 | 컬럼별 타입·null률·유니크 수·상위 값·min/p50/max | `probe/stats/{id}.json` |
| (예정) 갱신 관찰 i, 공개 지연 j | 7일 뒤 재호출 / 사건일→첫 관측일 (`event_to_publish_lag`) | 아직 없음 |
"""

COMMON = """\
## 9. 검증에서 드러난 공통 사항

실호출로 확인된, 여러 데이터에 반복되는 성질. 도시에 "호출 방법·함정"과 코드 생성기 템플릿의 재료다.

1. **호출 체인(파라미터 의존)** — 조회형 API 상당수는 다른 API가 준 코드가 필수 파라미터다 (`파라미터부족` 판정).
   예: 심평원 의료기관 상세(요양기관기호 ykiho) · 공동주택 기본정보(단지코드) · 온비드 물건(물건 번호) · 토지이용규제(PNU) ·
   나이스 급식·학사일정·시간표(교육청코드+학교코드 → `schoolInfo` 먼저). → 패밀리의 `lookup` 엣지와 `probe_params.yaml` 체인 값으로 해결.
2. **"응답 0행"은 대부분 예시값 문제** — 명세의 예시 파라미터가 기한 만료·오타이거나, 지자체 소규모 API가 갱신 중단. 개별 확인 필요.
3. **전체 건수 ≠ 받은 행** — 검증은 기본 1,000~5,000행까지만 받았다. `total_count`가 전수 규모다 (예: 상가업소 22,739 중 2,076, 철도 수송 178,691 중 2,000).
4. **날짜 컬럼의 함정** — 학사일정·건설 계획처럼 미래 날짜가 정상인 데이터, `9999-12-31` 같은 무기한 표시가 있다 → `lag_days` 음수. 최신성은 적재일(LOAD_DTM 등) 컬럼을 따로 봐야 한다.
5. **키 판정의 오탐** — 홈페이지 URL(`HMPG_ADRES`)·메일이 "주소"로, '특성평가격자'가 '가격'으로 걸린 사례. 방송통신 검토 때 URL·메일 주소는 연계 키에서 제외하도록 고쳤고, 값 패턴 판정으로 보강.
6. **같은 대상, 다른 코드 체계** — 학교(나이스 7자리 vs 표준데이터 `B000…`, 실측 겹침 0/12,011), 의료기관(ykiho·hpid·LOCALDATA),
   교통 노드(역·정류장), 시설(어린이집·유치원·사회복지시설). 매핑표가 전략의 선결 과제다 (§5 키 원장 note).
7. **외부 채널은 사이트마다 키 체계가 다르다** — VWorld(key+domain, 개발키는 서비스 URL에 묶임), 서울(URL 경로에 KEY), 나이스(KEY, SNS 로그인만),
   법제처(OC), 국회(KEY). 발급처는 `key_issuers.yaml`, 계정·키 값은 `.env`에만.
8. **표준데이터(STD)는 파일 다운로드 없이 API만 있는 경우**가 있다 — 연결된 API로 대체 검증(`substitute_for`)했다 (공시지가·개별주택가격·연속지적도·초등학교 시간표).
9. **포털 활용신청은 대부분 자동승인** — 심의 건은 `승인대기`로 남는다 (분실물·보건복지 현황 등). Playwright 신청 자동화(`pds/probe/apply.py`)가 Phase 6 `apply_key`의 원형.
"""


# ───────────────────────── 섹션 생성 ─────────────────────────
def sec_catalog(d: pd.DataFrame, subs) -> list[str]:
    L = ["## 2. 전체 카탈로그와 분류 체계", "",
         "### 2.1 원천", "",
         "- 목록 메타정보 `15121937` (2026-07-03) · 목록개방현황 `15062804` (2026-07-31) · 제공 표준 `15156444` (2025-10-01) — `data/raw/`",
         f"- 합친 카탈로그 `data/processed/catalog.parquet` {len(d):,}건 × 44컬럼 (제목·기관·BRM·보유근거·갱신주기·요청변수·출력결과·활용수·국가중점·표준 등)",
         "- 분류 결과 `class.parquet` (부문·세부 부문·행정단위·제외), 점수 `score.parquet` (축별 점수와 판정 근거)", "",
         "### 2.2 분류 층", "",
         "```",
         "BRM 정책분야(16)                       ← 포털 등록값",
         " └ 정책영역 = 부문(sector)             ← sector_map.yaml 규칙으로 기관·시스템 기준 재배치 (원래 BRM은 보존)",
         "    └ 세부 부문(subsector)             ← subsectors.yaml: 행정 프로세스 1개 = 근거법 1개+ = 개별 코드 1종, depth·novelty·cycle",
         "       └ 데이터셋                       ← exclusions.yaml 규칙에 걸리면 excluded_by 표시 (삭제 아님)",
         "부문 위: domain (sector_tree.yaml, 법 체계 계층)   부문 옆: context (contexts.yaml, 부처를 가로지르는 맥락)",
         "```", "",
         "### 2.3 정책분야별 규모", ""]
    g = d.groupby("sector_field")
    rows = []
    for f, x in sorted(g, key=lambda t: -len(t[1])):
        al = x[x.alive]
        rows.append([f, fmt_n(len(x)), fmt_n(len(al)), fmt_n(len(x) - len(al)), x.sector.nunique(),
                     len(al.groupby(['sector', 'subsector'])), fmt_n((al.subsector_depth == "front").sum()),
                     fmt_n((al.api_kind_label.isin(["REST", "SOAP", "API_LINK"])).sum()), fmt_n((al.api_kind_label == "STD").sum()),
                     fmt_n(al.api_kind_label.isin(["FILE", "FILE_LINK"]).sum())])
    al = d[d.alive]
    rows.append(["**계**", fmt_n(len(d)), fmt_n(len(al)), fmt_n(len(d) - len(al)), d.sector.nunique(), len(al.groupby(['sector', 'subsector'])),
                 fmt_n((al.subsector_depth == "front").sum()), fmt_n(al.api_kind_label.isin(["REST", "SOAP", "API_LINK"]).sum()),
                 fmt_n((al.api_kind_label == "STD").sum()), fmt_n(al.api_kind_label.isin(["FILE", "FILE_LINK"]).sum())])
    L += table(["정책분야", "전체", "생존", "제외", "부문 수", "세부 부문(생존)", "front 데이터", "API", "표준", "파일"], rows)
    L += ["", "### 2.4 부문별 규모와 세부 부문", "",
          "세부 부문 표기: `slug`(이름, 생존 건수). **굵게** = front(심층 대상). 제외 규칙은 건수 상위 3개.", ""]
    for f, x in sorted(d.groupby("sector_field"), key=lambda t: -len(t[1])):
        L += [f"#### {f}", ""]
        rows = []
        for s, y in sorted(x.groupby("sector"), key=lambda t: -len(t[1])):
            ya = y[y.alive]
            sc = ya.groupby(["subsector", "subsector_name", "subsector_depth"]).size().reset_index(name="n").sort_values("n", ascending=False)
            subs_txt = ", ".join((f"**{r.subsector}**" if r.subsector_depth == "front" else r.subsector) + f"({r.subsector_name}, {r.n:,})"
                                 for r in sc.itertuples())
            ex = y.excluded_by.value_counts().head(3)
            L_ex = ", ".join(f"{k} {v:,}" for k, v in ex.items())
            rows.append([s.split(" - ", 1)[-1], fmt_n(len(y)), fmt_n(len(ya)), subs_txt, L_ex])
        L += table(["부문", "전체", "생존", "세부 부문", "주요 제외 규칙"], rows) + [""]
    return L


def sec_review() -> list[str]:
    L = ["## 4. 분류·관계 논의 기록", "",
         "정책영역별 검토에서 내린 결정의 요지 (`knowledge/sectors/_review_log.md`에서 결정·이유·이관·키·맥락 줄만 추림, 판정표는 원문 참조).",
         "2026-09-28은 구름이 직접 결정, 2026-09-29 오후부터는 구름이 정한 기준을 Claude가 적용(\"이제 남은건 니가 알아서\").", ""]
    txt = (K / "sectors" / "_review_log.md").read_text(encoding="utf-8").splitlines()
    for ln in txt:
        if ln.startswith("## "):
            L += ["", "#" + ln]
        elif ln.startswith("- **"):
            L.append(ln)
    L += ["", "### 4.x 제외 규칙 전체 (exclusions.yaml)", ""]
    ex = _y("sectors/exclusions.yaml")
    L += table(["규칙", "결정", "이유"], [[e["id"], f"{e.get('decided_at', '')} {e.get('decided_by', '')}", esc(e.get("reason"), 260)] for e in ex])
    L += ["", "### 4.y 부문 재배치 규칙 전체 (sector_map.yaml)", ""]
    sm = _y("sectors/sector_map.yaml")
    L += table(["규칙", "→ 부문", "이유"], [[m["id"], m.get("set_sector", ""), esc(m.get("reason"), 220)] for m in sm])
    return L


def sec_relations(d) -> list[str]:
    L = ["## 5. 조인 키 · 키 발급처 · 맥락 · 패밀리 · 법 계층", "", "### 5.1 전역 조인 키 원장 (`knowledge/keys/`)", ""]
    keys = _store("key")
    L += table(["id", "이름", "형식", "원장(master)", "메모"],
               [[k["id"], esc(k["name"], 60), esc(k.get("format"), 60), ", ".join(map(str, k.get("master_datasets") or [])), esc(k.get("notes"), 240)]
                for k in keys])
    L += ["", "### 5.2 외부 키 발급처 (`key_issuers.yaml`) — 값은 `.env`에만", ""]
    iss = _store("issuer")
    L += table(["id", "이름", "키 파라미터", ".env 변수", "발급 절차"],
               [[i["id"], i["name"], i.get("key_param", ""), ", ".join((i.get("env") or {}).values()), esc(i.get("issuance"), 160)] for i in iss])
    L += ["", "### 5.3 맥락 연결 (`knowledge/contexts/`) — 부처를 가로지르는 묶음", "",
          "차원: life_context(같은 생애 질문) · spatial_regulation(같은 필지에 겹치는 규제) · admin_area(같은 행정구역 지표) · "
          "shared_key(같은 키) · shared_source(같은 원천 시스템) · same_concept(같은 개념 다른 기준) · economic(돈·거래 흐름)", ""]
    alive = d[d.alive]
    cnt = alive.groupby(["sector", "subsector"]).size().to_dict()
    cnt_s = alive.groupby("sector").size().to_dict()
    for c in _store("context"):
        mem = []
        for m in c.get("members", []):
            n = cnt.get((m["sector"], m.get("subsector")), 0) if m.get("subsector") else cnt_s.get(m["sector"], 0)
            mem.append(f"{m['sector'].split(' - ', 1)[-1]}/{m.get('subsector') or '*'}" + (f"({m['role']})" if m.get("role") else "") + f" {n:,}")
        L += [f"- **{c['name']}** `{c['id']}` · {c['dimension']}" + (f" · 키 `{c['key']}`" if c.get("key") else ""),
              f"  - 질문: {esc(c.get('question'))}" if c.get("question") else "  -",
              f"  - {esc(c.get('note'), 400)}", f"  - 멤버: {' · '.join(mem)}"]
    L += ["", "### 5.4 법 계층 (`sector_tree.yaml`)", ""]
    L += table(["domain", "법", "부문", "관련 부문", "메모"],
               [[t["id"], esc(t.get("law"), 160), ", ".join(t.get("sectors") or []), ", ".join(t.get("related") or []), esc(t.get("note"), 200)]
                for t in _y("sectors/sector_tree.yaml")])
    L += ["", "### 5.5 데이터 패밀리 — `pps-procurement` (조달청 나라장터 18종)", "",
          "- 한 업무 절차를 단계별 API로 쪼갠 묶음: 발주계획 → 조달요청 → 사전규격 → 입찰공고 → 개찰·낙찰 → 계약, 쇼핑몰 납품요구.",
          "- 단계는 **차세대 나라장터 통합번호**로 이어지고 **계약과정통합공개(15129459)**가 번호 하나로 전 과정을 잇는 허브.",
          "- 발주계획·사전규격 없는 입찰, 공고 없는 계약이 정상 (소액·수의계약) — 체인이 끊겨도 오류가 아니다.",
          "- 엣지 타입 lifecycle·lookup·join·reference·hierarchy·mirror·derived·aggregate, 상태 documented → inferred → verified/refuted.",
          "- 표준 `knowledge/families/README.md`. 다른 기관 API 묶음(가맹정보 40여 종·기업집단포털·나이스 등)에 같은 방식 적용 예정.", ""]
    return L


def sec_targets(tg, d) -> list[str]:
    dd = d.set_index("id")
    L = [f"## 6. 분석 대상 {len(tg)}건 (`knowledge/targets.json`)", "",
         "선정 규칙 (`pds/probe/targets.py`): 제외되지 않은 **front 세부 부문마다 대표 1건** — 포털 우선 → 형태(REST·표준 > 파일 > 외부 링크) → 점수 → 활용 순.",
         "라운드 1 = 포털에서 바로 검증 가능한 상위 80건, 라운드 2 = 나머지 포털, external = 기관 사이트 키가 필요한 것.",
         "`why`는 세부 부문 정의의 `value_source`(왜 이 세부 부문이 가치 있는가)에서 시작했다.", "",
         "부문별 대상 수: " + " · ".join(f"{k} {v}" for k, v in Counter(t['sector'].split(' - ')[0] for t in tg).most_common()), ""]
    rows = []
    for t in sorted(tg, key=lambda t: (t["sector"], t["subsector"])):
        pr = t.get("probe") or {}
        rows.append([f"[{t['id']}](#d-{t['id']})" if t["status"] == "verified" else t["id"], esc(t["title"], 60),
                     t["sector"].split(" - ", 1)[-1], f"{t['subsector']}", t["kind"], t["round"], t["prelim_score"], fmt_n(t.get("usage")),
                     {"verified": "✅", "failed": "✗", "pending": "…"}.get(t["status"], t["status"]), pr.get("verdict") or "", esc(t.get("why"), 120)])
    L += table(["id", "데이터", "부문", "세부 부문", "형태", "라운드", "점수", "활용", "상태", "판정", "왜"], rows)
    return L


def sec_results(tg) -> list[str]:
    L = ["## 7. 검증 결과 요약", ""]
    v = Counter((t.get("probe") or {}).get("verdict") or "없음" for t in tg)
    L += ["판정별: " + " · ".join(f"{k} {n}" for k, n in v.most_common()), "",
          "- `파일(별도)` = 파일·표준데이터: 포털 파일을 내려받아 셀 통계를 냈으면 verified, 다운로드가 없으면 failed(대체 API로 검증한 경우 `substituted_by`).",
          "- 실패 사유별 조치: 키미등록 → 포털 신청 상태 확인 · 파라미터부족 → 체인 값 지정 · 응답0행 → 예시값·제공기관 확인 · 미실행 → 명세 없음(외부 시스템).", ""]
    by = defaultdict(Counter)
    for t in tg:
        by[t["sector"].split(" - ")[0]][t["status"]] += 1
    L += table(["정책분야", "대상", "검증", "실패", "보류"],
               [[f, sum(c.values()), c["verified"], c["failed"], c["pending"]] for f, c in sorted(by.items(), key=lambda x: -sum(x[1].values()))])
    kc = Counter(k for t in tg if t["status"] == "verified" for k in ((t.get("probe") or {}).get("keys") or []))
    L += ["", "실측 조인 키 보유 (검증 건 기준): " + " · ".join(f"{k} {n}" for k, n in kc.most_common()), "",
          "### 7.1 실패·보류 목록", ""]
    L += table(["id", "데이터", "부문/세부", "형태", "판정", "메모"],
               [[t["id"], esc(t["title"], 60), f"{t['sector'].split(' - ', 1)[-1]}/{t['subsector']}", t["kind"],
                 (t.get("probe") or {}).get("verdict") or t["status"], esc(t.get("note"), 140)]
                for t in sorted(tg, key=lambda t: ((t.get("probe") or {}).get("verdict") or "", t["sector"])) if t["status"] != "verified"])
    return L


def _num(v) -> str:
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return f"{v:.4g}" if isinstance(v, float) else str(v)


def _fmt_stat(s: dict) -> str:
    if not isinstance(s, dict):
        return ""
    if s.get("min") is not None and s.get("type") == "number" and s.get("unique", 0) > 5:
        return " ~ ".join(_num(s.get(k)) for k in ("min", "p50", "max") if s.get(k) is not None)
    top = s.get("top") or {}
    return ", ".join(f"{esc(k, 28)}({v})" for k, v in list(top.items())[:3])


def sec_details(tg, d, syn, summ) -> list[str]:
    dd = d.set_index("id")
    ctx_by = defaultdict(list)
    for c in _store("context"):
        for m in c.get("members", []):
            ctx_by[(m["sector"], m.get("subsector"))].append(c["name"])
            if not m.get("subsector"):
                ctx_by[(m["sector"], "*")].append(c["name"])
    L = [f"## 8. 데이터별 상세 (검증 완료 {sum(t['status'] == 'verified' for t in tg)}건)", "",
         "각 항목: ① 메타(포털 등록값) ② 분류·점수 판정과 근거 ③ 선정 이유와 맥락 ④ 접근·호출 실측 ⑤ 실측 조인 키·최신성 ⑥ 컬럼 실측(명세 설명 + 셀 통계).",
         "컬럼 표는 오퍼레이션마다 최대 30개. 값 열은 숫자면 min ~ p50 ~ max, 아니면 상위 값(건수).", ""]
    cur = None
    for t in sorted((t for t in tg if t["status"] == "verified"), key=lambda t: (t["sector"], t["subsector"])):
        i = t["id"]
        m = dd.loc[i] if i in dd.index else None
        if t["sector"] != cur:
            cur = t["sector"]
            L += ["", f"### {cur}", ""]
        L += [f"<a id=\"d-{i}\"></a>", f"#### {i} · {t['title']}", ""]
        pr = t.get("probe") or {}
        s = syn.get(i, {})
        sm = summ.get(i, {})
        # ① 메타
        if m is not None:
            L += ["**메타** — " + " · ".join(x for x in [
                f"기관 {m.agency_name}", f"형태 {t['kind']}" + (f"({m.api_type})" if isinstance(m.api_type, str) and m.api_type else ""),
                f"원래 BRM {m.brm}" if isinstance(m.brm, str) else "", f"갱신 {m.update_cycle}" if isinstance(m.update_cycle, str) else "",
                f"수정일 {str(m.modified_at)[:10]}" if m.modified_at is not None else "",
                f"활용 {fmt_n(m.usage_count)} · 조회 {fmt_n(m.view_count)}", "국가중점" if m.national_key in (True, "Y", "y", 1) else "",
                f"표준 {m.std_id}" if isinstance(m.std_id, str) and m.std_id else "", f"[포털]({t['url']})"] if x)]
            if isinstance(m.legal_basis, str) and m.legal_basis.strip():
                L.append(f"- 보유근거: {esc(m.legal_basis, 200)}")
            if isinstance(m.description, str) and m.description.strip():
                L.append(f"- 설명: {esc(m.description, 420)}")
            if isinstance(m.keywords, str) and m.keywords.strip():
                L.append(f"- 키워드: {esc(m.keywords, 150)}")
            # ② 판정
            L += [f"- **분류·판정**: 세부 부문 `{t['subsector']}`({t['subsector_name']}, {m.subsector_depth}) · 행정단위 {m.admin_unit} · 범위 {m.coverage}"
                  + (f" · novelty {m.novelty}" if isinstance(m.novelty, str) else "") + (" · 공통 마스터" if m.cross_cutting is True else ""),
                  f"- **점수** {m.prelim_score:.3f} (부문 {fmt_n(m.rank_in_sector)}위) — 활용 {m.s_usage:.2f} · 형태 {m.s_api_kind:.2f} · "
                  f"입도 {m.s_granularity:.2f} · 연계 {m.s_linkable:.2f} · 시의성 {m.s_novelty:.2f} · 최신 {m.s_freshness:.2f}"
                  + (" (외부: 최신·메타 대입)" if m.imputed is True else "")]
            ev = [f"{lbl} {esc(getattr(m, c), 90)}" for lbl, c in (("입도:", "granularity_ev"), ("연계:", "linkable_ev"), ("범위:", "coverage_ev"),
                                                                    ("시의성:", "novelty_ev")) if isinstance(getattr(m, c), str) and getattr(m, c)]
            if ev:
                L.append("  - 판정 근거 — " + " · ".join(ev))
        # ③ 선정 이유·맥락
        L.append(f"- **왜 대상인가**: {esc(t.get('why'))}")
        ctx = ctx_by.get((t["sector"], t["subsector"]), []) + ctx_by.get((t["sector"], "*"), [])
        if ctx:
            L.append(f"- **맥락**: {' · '.join(dict.fromkeys(ctx))}")
        if t.get("note"):
            L.append(f"- 메모: {esc(t['note'])}")
        # ④ 접근·호출
        apply = _j("apply", i) or {}
        spec = _j("specs", i) or {}
        run = _j("runs", i) or {}
        ch = run.get("channel", "portal")
        acc = [f"경로 {ch}" + (f"({run.get('site')})" if run.get("site") else "")]
        if apply.get("심의여부"):
            acc.append(f"심의 {apply['심의여부']}")
        if spec.get("host"):
            acc.append(f"host `{spec['host']}`")
        if spec.get("operations"):
            acc.append(f"오퍼레이션 {len(spec['operations'])}개")
        ops = run.get("ops") or []
        if ops:
            acc.append(f"성공 {sum(bool(o.get('ok')) for o in ops)}/{len(ops)}")
        if sm.get("ms"):
            acc.append(f"평균 {sm['ms']}ms")
        acc.append(f"받은 행 {fmt_n(pr.get('rows') or s.get('rows'))}" + (f" / 전체 {fmt_n(pr.get('total_count') or s.get('total_count'))}"
                                                                           if (pr.get("total_count") or s.get("total_count")) else ""))
        if pr.get("formats"):
            acc.append("형식 " + "/".join(pr["formats"]))
        L.append("- **호출 실측**: " + " · ".join(acc))
        req = []
        for o in (spec.get("operations") or [])[:6]:
            rp = [p["name"] for p in o.get("params", []) if p.get("required") and p["name"] not in ("serviceKey", "pageNo", "numOfRows", "ServiceKey")]
            req.append(f"`{o.get('path')}` {esc(o.get('summary') or o.get('name'), 40)}" + (f" (필수: {', '.join(rp)})" if rp else ""))
        if req:
            L.append("  - 오퍼레이션: " + " · ".join(req))
        need = sorted({p for o in ops for p in (o.get("needs_params") or [])})
        if need:
            L.append(f"  - 체인 필요 파라미터: {', '.join(need)}")
        # ⑤ 키·최신성
        kc = s.get("key_columns") or {}
        keys = pr.get("keys") or s.get("keys") or []
        L.append(f"- **실측 조인 키**: {', '.join(keys) if keys else '없음'}"
                 + (" — " + ", ".join(f"`{c}`→{'/'.join(v)}" for c, v in list(kc.items())[:12]) if kc else ""))
        dates = s.get("dates") or {}
        if dates or pr.get("latest"):
            L.append(f"- **최신성**: 최신 {pr.get('latest') or s.get('latest')} (지연 {pr.get('lag_days') if pr.get('lag_days') is not None else s.get('lag_days')}일)"
                     + (" — " + ", ".join(f"{c} {v['min']}~{v['max']}" for c, v in list(dates.items())[:4]) if dates else ""))
        # ⑥ 컬럼
        desc = {}
        for o in spec.get("operations") or []:
            for f in o.get("response_fields") or []:
                desc.setdefault(str(f.get("name")).split(".")[-1].lower(), f.get("desc"))
        st = _j("stats", i) or {}
        for op, cols in list(st.items())[:4]:
            if not isinstance(cols, dict) or not cols:
                continue
            L += ["", f"<details><summary>컬럼 실측 — {esc(op, 60)} ({len(cols)}개)</summary>", ""]
            L += table(["컬럼", "의미(명세)", "타입", "null", "유니크", "값"],
                       [[c, esc(desc.get(str(c).lower()), 40), (v or {}).get("type", ""), f"{(v or {}).get('null_rate', 0):.0%}" if isinstance((v or {}).get("null_rate"), (int, float)) else "",
                         fmt_n((v or {}).get("unique")), _fmt_stat(v)] for c, v in list(cols.items())[:30]])
            L += ["", "</details>"]
        L.append("")
    return L


def sec_open(d) -> list[str]:
    L = ["## 10. 미결·재검토 목록 (Phase 3 이전에 정할 것)", "",
         "### 10.1 검토 기록에 남은 재검토·확인·보류 항목", ""]
    for ln in (K / "sectors" / "_review_log.md").read_text(encoding="utf-8").splitlines():
        if re.match(r"- \*\*(재검토|확인 필요|보류|병합 때|주의|다음|구조 이슈)", ln):
            L.append(ln)
    L += ["", "### 10.2 공백(gap) — 포털에 데이터가 없는 업무 영역", ""]
    for g in _store("gap"):
        L.append(f"- {g['sector']} / {g['name']}{' (해소)' if g.get('status') == 'resolved' else ''}: {esc(g['reason'])}"
                 + (f" — 포털 밖 대안: {g['external_candidate']}" if g.get("external_candidate") else ""))
    L += ["", "### 10.3 Phase 3 설계 전에 결정할 구조 질문", "",
          "1. **도시에 단위** — 데이터 1건 vs 세부 부문 대표 1건 vs 패밀리 1개. 가맹정보(40여 API)·나이스(10 오퍼레이션)·실거래(13종 → 도시에 1개로 이미 결정)처럼 묶음이 자연스러운 곳이 많다.",
          "2. **공통 원장 도시에** — LOCALDATA 인허가(음식점·숙박·체육·의료·식품), 사회복지시설 마스터, 표준데이터 계열을 부문별로 쪼갤지 하나로 둘지.",
          "3. **코드 매핑표를 먼저 만들지** — 학교(3체계)·의료기관(ykiho·hpid·LOCALDATA)·시설코드·교통 노드·단지코드. 전략 응답의 조인 경로가 여기에 달려 있다.",
          "4. **실패 62건 처리** — 대체 데이터 재선정(같은 세부 부문 다음 순위) vs 체인 파라미터로 재시도 vs 보류.",
          "5. **갱신 관찰(i)·공개 지연(j)** — 7일 재호출과 증분 관측을 언제 돌릴지 (시의성 축의 실측 근거).",
          "6. **법령 층(laws/)** — 도시에 \"법적 근거\"를 법제처 API 원문 조항으로 채우는 순서 (키는 확보됨: open.law.go.kr).",
          "7. **골든셋(Phase 4)** — 맥락(context) 41개의 `question`이 목표 문장 후보. 어느 것부터 정답 전략을 쓸지.",
          ""]
    return L


def build() -> str:
    d, tg, syn, summ = load()
    subs = _y("sectors/subsectors.yaml")
    ctx = _store("context")
    alive = d[d.alive]
    st = Counter(t["status"] for t in tg)
    rd = Counter(t["round"] for t in tg)
    head = INTRO.format(
        today=dt.date.today().isoformat(), n_all=len(d), n_field=d.sector_field.nunique(), n_sector=d.sector.nunique(),
        n_sub=sum(len(s["subsectors"]) for s in subs), n_front=sum(x["depth"] == "front" for s in subs for x in s["subsectors"]),
        n_domain=len(_y("sectors/sector_tree.yaml")), n_excl_rule=len(_y("sectors/exclusions.yaml")), n_excl=len(d) - len(alive),
        n_alive=len(alive), n_map=len(_y("sectors/sector_map.yaml")), n_tg=len(tg), r1=rd["1"], r2=rd["2"], rx=rd["external"],
        n_ver=st["verified"], n_fail=st["failed"], n_pend=st["pending"], n_keys=len(_store("key")), n_iss=len(_store("issuer")),
        n_ctx=len(ctx), ctx_dims=" · ".join(f"{k} {v}" for k, v in Counter(c["dimension"] for c in ctx).most_common()),
        n_fam=sum(1 for p in (K / "families").iterdir() if p.is_dir()))
    parts = [head, GOAL.format(n_ver=st["verified"], n_tg=len(tg))]
    parts += ["\n".join(sec_catalog(d, subs)), DIMENSIONS, "\n".join(sec_review()), "\n".join(sec_relations(d)),
              "\n".join(sec_targets(tg, d)), "\n".join(sec_results(tg)), "\n".join(sec_details(tg, d, syn, summ)), COMMON,
              "\n".join(sec_open(d))]
    OUT.write_text("\n\n".join(parts) + "\n", encoding="utf-8")
    return str(OUT)


if __name__ == "__main__":
    print(build())
