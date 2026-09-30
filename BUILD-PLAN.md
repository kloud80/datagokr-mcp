# PDS 개발 계획 — 지식 기반 공공데이터 전략 시스템 (BUILD-PLAN v1)

작성: 2026-09-28 · 이 문서는 `DESIGN.md`(검색 엔진 설계 v1)를 **대체**한다. DESIGN.md의 스택·DDL·랭킹 계산식은 부품으로 재사용하되, 개발 순서와 최종 목표는 이 문서를 따른다.
대상: Claude Code. 각 Phase는 앞 Phase의 산출물이 있어야 시작한다. 시간 제약 없음. 품질 우선.

> 메모 (2026-09-28): DESIGN.md는 이 리포에 없으며 참조하지 않는다. DESIGN.md를 인용하는 항목(DDL, §5 ingest, §7 freshness 등)은 이 리포의 코드(`pds/`)와 `sql/`이 원본이다.

---

## 0. 무엇을 만드는가

**최종 시스템의 핵심은 검색이 아니라 전략이다.** 사용자가 목표("성수동 상권 변화를 월 단위로 추적하고 싶다")를 말하면, 시스템은 축적된 데이터 지식을 바탕으로

1. data.go.kr의 **어떤 데이터**를 가져와야 하는지
2. **왜** 그것을 추천하는지 (법적 근거, 갱신 주기, 실제 검증 결과)
3. 여러 데이터를 **어떻게 연계**하면 목표에 도달하는지 (조인 키, 순서, 함정)
4. 바로 실행 가능한 **코드**

를 MCP 수준의 구조화된 응답으로 돌려준다. 사람이 읽어도, 에이전트가 받아도 즉시 실행 가능해야 한다.

이를 위해 개발은 6단계로 간다. 1~3단계는 지식을 쌓는 단계(오래 걸림, 사람과 대화하며 진행), 4~6단계는 그 지식을 쓰는 단계.

```
Phase 1  벌크 메타 → 부문·기관·행정단위별 핵심 데이터 랭킹 → HTML 리포트 → 구름과 대화로 대상 확정
Phase 2  확정 데이터를 하나씩 심층 검증 (실제 키 발급 → 호출 → 다운로드 → 셀 통계 → 실데이터 확인)
Phase 3  검증 결과 + 법령·행정절차·공개시점을 합쳐 데이터 도시에(dossier) 작성 → 지식체계 저장
Phase 4  전략 프로토콜: 목표 → 지식체계 조회 → 구조화된 전략 응답 (MCP 스키마)
Phase 5  샘플 코드 생성기: 전략 응답 → 실행 가능한 Python 템플릿
Phase 6  키·로그인 인터페이스: 사용자의 data.go.kr 계정으로 키를 받아오는 별도 MCP 서버
```

---

## 1. 공통 기반 (Phase 0, 모든 Phase가 공유)

DESIGN.md §1·§3·§4·§13에서 그대로 가져온다. 변경점만 적는다.

| 항목 | 결정 |
| --- | --- |
| 저장소 | `pds/` 단일 리포. Python 3.12+, Postgres(회사 개발 DB `dataops`, 스키마 `구름`, 테이블 접두어 `pds_`). **pgvector는 쓰지 않는다** — 임베딩은 별도 저장소(§3.3). |
| 지식체계 저장 형식 | **Markdown 파일이 원본**(`knowledge/dossiers/{dataset_id}.md`, git 관리) + Postgres는 파생 인덱스. 위키형 편집·diff·리뷰가 git에서 공짜로 되기 때문. |
| 브라우저 자동화 | Playwright (Python). 로그인 세션은 `storage_state.json`으로 보관, 비밀번호는 코드·DB에 절대 저장 안 함. |
| LLM 호출 | Anthropic API. 모든 프롬프트는 `prompts/*.md`에 파일로 두고 버전 관리. |
| 사람 검토 지점 | Phase 1 끝(대상 확정), Phase 3 각 도시에(승인), Phase 4 전략 골든셋. 이 세 지점은 자동화하지 않는다. |

```
pds/
├── BUILD-PLAN.md            ← 이 문서
├── DESIGN.md                ← 부품 참조용
├── knowledge/               ← Phase 3 산출물, git 관리
│   ├── sectors/             ← 부문 정의 (Phase 1 확정)
│   ├── dossiers/            ← 데이터별 도시에 md
│   ├── laws/                ← 법령 요약 md
│   └── recipes/             ← 연계 레시피 md (Phase 4)
├── pds/
│   ├── ingest/  rank/  probe/  dossier/  strategy/  codegen/  mcp/
├── reports/                 ← Phase 1 HTML
├── prompts/
└── tests/
```

---

## Phase 1 — 핵심 데이터 랭킹과 대상 확정

**목표**: 벌크 메타만으로 "부문 → 기관 → 행정단위" 3축 랭킹을 만들고, HTML 리포트를 놓고 구름과 대화하며 부문 구분과 부문별 심층 분석 대상을 확정한다.

### 1.1 입력
- 목록 메타정보 15121937, 목록개방현황 15062804, 제공 표준 15156444 (DESIGN.md §5 ingest)
- BRM 1~3레벨 (정책분야 17 / 정책영역 76 / 대기능)
- 국가중점데이터 목록, AI·고가치 Top 100 목록

### 1.2 3축 정의

| 축 | 값 | 출처 |
| --- | --- | --- |
| 부문(sector) | BRM 정책영역 76개를 출발점으로, 대화로 병합·분할해 최종 15~25개 | BRM + 대화 |
| 기관(agency) | 제공기관, 계층(중앙/공공기관/광역/기초) | 벌크 메타 |
| 행정단위(admin_unit) | 데이터가 다루는 공간 단위: 전국/시도/시군구/읍면동/필지·건물/개별 | title·컬럼에서 추정 + LLM 분류 |

### 1.3 1차 랭킹 점수 (메타만으로 계산, 검증 전)

```
prelim_score = 0.30·usage       (활용신청+조회수, kind 안 백분위)
             + 0.05·designation (국가중점 1.0 / Top100 0.8 / 제공표준 0.6 / 없음 0)
             + 0.15·api_kind    (REST API·외부링크 API 1.0 / SOAP 0.8 / 표준데이터셋 0.7 / FILE·외부링크 FILE 0.4)
             + 0.15·granularity (건별 원천 1.0 / 판단 불가 0.5 / 통계·집계 0.1~0.3, `pds/rank/shape.py`)
             + 0.10·linkable    (연계 키: 사업자번호·행정구역코드·PNU·건물키·기관코드·표준분류코드·주소·좌표 가중 합)
             + 0.05·coverage    (전수 1.0 / 기본 0.8 / 표본·일부·번호 조회형 0.3)
             + 0.10·novelty     (시의성: "LLM이 이미 아는가"의 반대. 세부 부문 판정 high/medium/low, 없으면 갱신 주기)
             + 0.05·freshness   (수정일·주기 기준, `pds/rank/score.py`)
             + 0.05·meta_fill   (요청변수·출력결과·보유근거·한계 채움률)
```

**가중치 변경 (2026-09-28).** 초안(usage 0.30 / designation 0.20 / api_kind 0.20 / freshness 0.15 / meta_fill 0.15)은 국가중점이 상위 1,000개의 99%를 차지해 사실상 입장 자격이 됐다. 원인: 지정이 기관 시리즈 단위로 몰림(행안부 341·식약처 290·국회사무처 275건), 활용 점수(log min-max, p99 컷)가 상위권에서 포화. 지정은 동점 구분 수준으로 낮추고 활용은 백분위로 바꿨다. 국가중점만 보고 싶으면 리포트의 '국가중점만' 필터를 쓴다.

**평가 축 추가 (2026-09-28, 구름).** 통계·기간·지역 집계보다 **건별 원천(최소 단위)** 데이터 — 사전규격 한 건, 계약 한 건, 물품 하나씩 조회되는 것 — 를 위로. **전수**가 나오면 더 높게, **연계 가능한 키**가 있으면 더 좋게. 모든 분야 공통. 판정은 출력 컬럼명·제목 기반 규칙이라 Phase 2 실측으로 교정한다.
API 중심 원칙에 따라 `api_kind` 가중치가 크다. 파일데이터는 후보에 남기되 순위가 낮다.

**외부 링크는 깎지 않는다.** 포털에 목록만 있고 실제 API·파일은 기관 사이트(VWorld, 한국수출입은행 등)에 있는 데이터(API 4,778건)도 가서 연결하면 쓸 수 있다. 불편함은 점수가 아니라 전략 응답의 `access.channel = "external"`과 접근 절차로 드러낸다(§9).
외부 링크 API는 포털에 컬럼 정보가 없고 포털 수정일이 실제 갱신과 무관하므로 `freshness`·`meta_fill`은 판단 불가다. 0점(깎임)도 제외 후 재정규화(상위 100 중 76개 독식)도 아니게, 포털 REST API의 중앙값을 넣는다(`imputed` 컬럼에 표시). 결과: 상위 100 중 외부 9개, 상위 500 중 57개.

### 1.4 HTML 리포트 (`reports/phase1_ranking.html`)

단일 HTML, 외부 의존 없음(인라인 JS·CSS). 구성:
- 상단: 부문 × 기관계층 히트맵 (셀 = 데이터 수, 클릭 시 필터)
- 좌측: 부문 트리(BRM 정책분야 > 정책영역), 각 노드에 데이터 수·평균 점수
- 중앙: 필터된 데이터 테이블 — 순위, 제목, 기관, kind, 행정단위, prelim_score, 활용, 국가중점, 수정일, 포털 링크. 정렬·검색 가능
- 우측: 선택 데이터의 메타 원문(요청변수·출력결과·보유근거·한계)
- 각 행에 체크박스 "심층 분석 대상" + 메모. 체크 상태는 `localStorage`에 저장하고 "내보내기" 버튼으로 `targets.json` 다운로드

### 1.5 대화 절차 (Claude Code 세션에서 구름과)

1. 리포트를 열고 부문 트리부터 본다. 병합/분할/이름 변경 결정 → `knowledge/sectors/*.md`에 부문 정의(이름, 포함 BRM 영역, 대표 법령, 대표 기관, 한 줄 설명) 작성.
2. 부문별로 상위 20개를 보며 심층 대상 3~8개 체크. 기준: API일 것, 국민이 일상에서 부딪히는 행정 절차와 직결될 것, 다른 데이터와 조인 키가 있을 것.
3. `targets.json` 확정 → Phase 2 입력. 첫 라운드는 총 50~80개.

**완료 기준**: `knowledge/sectors/` 15~25개 파일, `targets.json` 50~80건, 각 대상에 "왜 뽑았는지" 한 줄.

---

## Phase 2 — 데이터 심층 검증 (에이전트 + Playwright)

**목표**: 대상 데이터를 하나씩, 실제로 키를 받고 호출하고 받아서 검증한다. 인기순으로. 메타가 아니라 실물을 본다.

### 2.1 검증 절차 (`pds/probe/deep.py`, 데이터 1건 = 1 run)

| 단계 | 하는 일 | 도구 | 기록 |
| --- | --- | --- | --- |
| a. 페이지 확인 | 포털 상세 페이지 열기, 명세서(HWP/PDF/Swagger) 다운로드, 활용신청 버튼 상태 | Playwright (storage_state로 로그인 상태) | 스크린샷, 명세서 파일, 승인유형 |
| b. 활용신청 | 개발계정 신청 폼 자동 입력(활용목적 고정 문구), 제출 | Playwright | 신청일시, 자동승인 여부 |
| c. 승인 대기 | 자동승인이면 즉시, 심의면 큐에 넣고 다음 데이터로. 매일 마이페이지 확인 | 스케줄 | 승인일시, 대기 일수 |
| d. 키 확인 | 마이페이지에서 Encoding/Decoding 키 추출 | Playwright | 키는 로컬 `secrets/keys.json`(gitignore) |
| e. 호출 | 명세서의 모든 오퍼레이션을 최소 파라미터로 1회씩. JSON·XML 둘 다. 페이징 끝까지 최대 N행(기본 5,000) | httpx | 응답 시간, 상태코드, 본문 오류 여부, 실제 컬럼 목록 |
| f. 다운로드 | 최근 기간 데이터를 parquet로 저장 | pandas | `probe/data/{id}/{date}.parquet` |
| g. 셀 통계 | 컬럼별: 타입 추정, null률, 유니크 수, 상위 값 10개, 수치 분포(min/p50/max), 날짜 범위, 코드값이면 코드표 매칭 여부 | pandas | `probe/stats/{id}.json` |
| h. 실데이터 확인 | 표본 20행을 LLM에 보여 "명세서 설명과 실제 값이 일치하는가, 이상값은" 판정 + 사람 눈으로 5행 | LLM + 사람 | 불일치 목록 |
| i. 갱신 관찰 | 7일 뒤 같은 호출 재실행, 행 수·최신 날짜 변화로 실제 갱신 주기 추정 | 스케줄 | 실측 주기 |
| j. 공개 지연 | 사건일(의안 발의일·판례 선고일·공고일·계약일 등 행 안의 날짜)과 API에 처음 나타난 날짜의 차이. 매일 증분 조회로 신규 행의 첫 관측일을 기록 | 스케줄 | `event_to_publish_lag` (p50/p90 일수) — 시의성(novelty) 판정의 실측 근거, 전략 응답의 "사건 후 N일 내 반영" |

외부 링크 데이터(`channel=external`)는 a·e~i는 같게 하되 b~d(포털 활용신청·키)는 해당 사이트 절차로 대신한다. 사이트 가입·키 발급은 사람이 하고(자동화하지 않음), 에이전트는 그 절차를 기록해 도시에 "호출 방법 > 접근 경로"에 남긴다.

### 2.2 로그인·키 처리 원칙
- 최초 1회 사람이 브라우저에서 로그인 → `playwright codegen`으로 storage_state 저장. 이후 에이전트는 그 세션만 쓴다.
- 세션 만료 시 에이전트는 멈추고 사람에게 알린다. 비밀번호 자동 입력 없음.
- 키는 Phase 2 검증 전용. Phase 6의 사용자 키와 완전히 분리.

### 2.3 산출물
- `probe/runs/{id}.json`: 위 a~i 전부
- `probe/stats/{id}.json`, `probe/data/{id}/*.parquet`
- 검증 실패(승인 거절, 호출 불가, 명세 불일치 심각)는 `targets.json`에 사유 기록 후 Phase 1로 되돌려 대체 데이터 선정

**완료 기준**: 대상 50~80건 중 검증 완료 ≥ 40건. 나머지는 심의 대기 큐.

---

## Phase 3 — 데이터 도시에와 지식체계

> **2026-09-30: Phase 3~4의 "어떻게"는 `KNOWLEDGE-SPEC.md`가 대체한다.** 도시에는 손으로 쓰는 md가 아니라 스키마로 검증되는 엔티티(Dataset·Key·Mapping·Edge·Claim·Context·Recipe) yaml에서 렌더링되는 뷰다. 아래 3.1 템플릿의 섹션 구성은 KNOWLEDGE-SPEC §8 렌더 템플릿으로 이어진다.

**목표**: 데이터 1건마다 "메타를 넘어서 데이터를 설명하는" 문서를 만든다. 법적 근거, 행정 처리 흐름, 공개 시점, 실측 결과를 한 곳에.

### 3.1 도시에 템플릿 (`knowledge/dossiers/{id}.md`)

```markdown
---
id: 15057511
title: 국토교통부_아파트 매매 실거래가 자료
sector: real-estate-transaction
agency: 국토교통부
admin_unit: 시군구/개별거래
kind: API
verified_at: 2026-10-14
verified_by: agent+구름
status: verified          # verified | pending | rejected
---

## 한 줄
이 데이터로 무엇을 알 수 있는가 (사용자 관점 1문장)

## 법적 근거
- 법령: 부동산 거래신고 등에 관한 법률 §3 (거래 신고 의무)
- 시행령/규칙: …
- 이 법 때문에 데이터가 존재하는 이유, 신고 주체, 신고 기한 (계약 후 30일)

## 행정 처리 흐름
신고 → 시군구 접수 → 국토부 RTMS 집계 → 포털 공개. 각 단계 소요와 데이터가 생성되는 시점.

## 공개 시점과 갱신
- 명세상 주기: 월간 / 실측: 매월 1일 전월분 + 해제·정정은 수시 (7일 관찰 결과)
- 지연: 계약일 기준 최대 약 60일 후 확정
- 소급 정정 여부: 있음 (해제여부 컬럼)

## 컬럼 사전 (실측)
| 컬럼 | 의미 | 타입 | null률 | 값 예시 | 코드표 | 주의 |
| --- | --- | --- | --- | --- | --- | --- |

## 조인 키
- 법정동코드(5자리 시군구), 지번, 아파트명 → 건축물대장과 결합 시 주의점

## 호출 방법
- 엔드포인트, 필수 파라미터, 페이징, 트래픽 한도(개발 1,000/일), 승인유형(자동)
- 함정: Decoding 키 사용, XML 기본, 오류도 200
- 접근 경로: `portal` | `external`. external이면 사이트, 가입·키 발급 절차, 포털 키와 별개 여부, 문서 URL, 트래픽 한도(사이트 기준)

## 실측 요약
행 수, 기간, 응답시간 p50/p95, 명세 불일치 목록 (probe/stats 링크)

## 어울리는 데이터 (연계)
- [[15057512]] 아파트 전월세 — 같은 키, 같은 주기
- [[건축물대장]] — 층·면적 보강

## 한계와 대체
이 데이터로 못 하는 것, 그때 대신 볼 데이터
```

### 3.2 생성 방법
1. `pds/dossier/draft.py`: probe 결과 + 벌크 메타 + 법제처 API(법령 본문) → LLM이 초안 작성 (`prompts/dossier.md`).
2. 사람(구름)이 리뷰. 특히 "법적 근거"와 "행정 처리 흐름"은 LLM 초안을 신뢰하지 않고 원문 조항으로 확인.
3. 승인 시 `status: verified`. PR 단위로 git에 들어간다.

### 3.3 지식체계 저장 (`pds/dossier/index.py`)
- 원본: markdown (위 템플릿). 사람이 읽고 고치는 대상.
- 파생: Postgres에 frontmatter·컬럼사전·조인키·연계 링크를 구조화 적재. `[[링크]]`는 edge 테이블로.
- 임베딩: 도시에 전문 + 섹션별 청크(한 줄·법적근거·연계·한계를 각각). 전략 단계에서 섹션 단위로 검색하기 위해.
- 임베딩 저장: 회사 개발 DB에 pgvector를 깔지 않는다. 벡터는 Postgres 밖 별도 저장소(로컬 파일 기반 벡터 인덱스 등, 도입 시점에 결정)에 두고, Postgres와는 `(doc_id, section)` 키로만 연결한다.
- 부문·법령 문서도 같은 방식 (`knowledge/sectors`, `knowledge/laws`).

**완료 기준**: verified 도시에 ≥ 40건, 부문 문서 전부, 법령 문서 ≥ 20건. 도시에 간 `[[링크]]` 평균 3개 이상.

---

## Phase 4 — 전략 프로토콜

**목표**: 목표를 입력받아 지식체계에서 전략을 만들어 MCP 수준 구조로 반환한다. 이것이 시스템의 핵심.

### 4.1 입력
```json
{ "goal": "성수동 상권 변화를 월 단위로 추적", "constraints": {"budget_calls_per_day": 1000, "need_realtime": false}, "known_keys": ["15081808"] }
```

### 4.2 처리 (`pds/strategy/plan.py`)
1. 목표 → 부문 후보 (부문 문서 임베딩)
2. 부문 내 도시에의 "한 줄"·"연계" 섹션 검색 → 후보 데이터 5~15
3. `knowledge/recipes/`에 이미 있는 연계 레시피와 매칭 (레시피 = 검증된 조인 순서)
4. LLM이 전략 초안 작성 (`prompts/strategy.md`). 근거는 반드시 도시에 섹션 인용. 도시에에 없는 주장은 금지.
5. 응답 스키마 검증 후 반환.

### 4.3 응답 스키마 (MCP 툴 `plan_public_data_strategy`의 출력)

```json
{
  "goal": "…",
  "sector": "commerce-local",
  "summary": "3개 데이터를 월 배치로 결합하면 된다. 실시간은 불가.",
  "datasets": [
    {
      "id": "15081808", "title": "…", "role": "primary",
      "why": "사업자 개·폐업 상태의 원천이며 월 단위 갱신이 실측으로 확인됨 (dossier §공개 시점)",
      "evidence": ["dossiers/15081808.md#공개-시점과-갱신", "dossiers/15081808.md#실측-요약"],
      "access": { "channel": "portal", "key_issuer": "data.go.kr", "approval": "auto", "daily_limit": 1000, "key_type": "decoding", "latency_p95_ms": 420 },
      "fetch": { "endpoint": "…", "params": {"b_no": "<list>"}, "paging": "pageNo/numOfRows", "format": "json" },
      "caveats": ["오류도 HTTP 200으로 옴", "사업자번호는 별도 목록 필요"]
    },
    { "id": "…", "role": "join", "join_on": {"left": "법정동코드", "right": "bjd_cd"}, "why": "…" },
    {
      "id": "15056910", "title": "국토교통부_연속지적도", "role": "join",
      "access": {
        "channel": "external",
        "external": {
          "site": "VWorld (vworld.kr)",
          "portal_page": "https://www.data.go.kr/data/15056910/openapi.do",
          "signup": "VWorld 회원가입 → 인증키 발급 (포털 키와 별개)",
          "key_issuance": "self-service, 즉시",
          "docs_url": "…",
          "steps": ["VWorld 가입", "오픈API 인증키 신청(서비스URL 기재)", "키로 WFS/데이터 API 호출"]
        },
        "daily_limit": null, "key_type": "external", "key_issuer": "vworld.kr"
      },
      "evidence": ["dossiers/15056910.md#호출-방법"]
    }
  ],
  "pipeline": [
    { "step": 1, "do": "fetch 15081808 for target bjd", "produces": "biz_status.parquet" },
    { "step": 2, "do": "fetch … ", "produces": "…" },
    { "step": 3, "do": "join on bjd_cd + month; compute open/close counts", "produces": "monthly_change.parquet" }
  ],
  "schedule": "monthly, run on day 3 (source publishes day 1, lag observed 2d)",
  "not_recommended": [ { "id": "…", "reason": "갱신 중단 의심 (probe 실패율 60%)" } ],
  "confidence": 0.78,
  "gaps": ["유동인구는 공공데이터에 없음 → 통신사 데이터 필요"]
}
```

### 4.4 골든셋
목표 50건 + 사람이 작성한 정답 전략. `pds/strategy/eval.py`가 datasets 집합 일치율·pipeline 순서 일치·evidence 유효성(링크가 실제 도시에 섹션인가)을 채점.

**완료 기준**: 골든셋 50건에서 primary 데이터 일치 ≥ 80%, evidence 유효율 100%.

---

## Phase 5 — 샘플 코드 생성기

**목표**: 전략 응답을 그대로 넣으면 실행되는 Python 코드를 만든다. 대부분은 이걸 복사해 바꿔 쓰는 용도.

### 5.1 템플릿 (`pds/codegen/templates/`)
- `fetch_api.py.j2`: 키 로드(환경변수), Encoding/Decoding 자동 판별, 페이징 루프, 200-but-error 처리, 재시도, parquet 저장
- `join.py.j2`: pipeline의 join 단계 → pandas merge, 키 정규화(법정동코드 자릿수, 지번 표기)
- `schedule.py.j2`: cron 문자열 + 갱신 관찰 로직
- `notebook.ipynb.j2`: 위 셋을 셀로 묶은 노트북

### 5.2 생성 (`pds/codegen/render.py`)
전략 JSON → Jinja2 렌더 → `out/{goal_slug}/` 폴더. LLM은 쓰지 않는다 (결정적 생성). 각 데이터의 fetch 파라미터·함정은 도시에 "호출 방법"에서 그대로 온다.

### 5.3 검증
생성된 코드를 Phase 2 검증 키로 실제 실행 → 성공해야 전략이 "실행 가능"으로 표시된다. 실패하면 도시에 "호출 방법" 오류로 되돌린다.

**완료 기준**: 골든셋 50건의 생성 코드 실행 성공 ≥ 90%.

---

## Phase 6 — 사용자 키·로그인 인터페이스 (별도 MCP 서버)

**목표**: 사용자가 자기 data.go.kr 계정으로 키를 받아 전략을 실행하게 한다. Claude/GPT 채팅과 에이전트 모두에서.

### 6.1 분리 원칙
- 전략 서버(`pds-strategy`)와 키 서버(`pds-keys`)는 **다른 MCP 서버**. 전략 서버는 키를 절대 보지 않는다.
- 키 서버는 사용자 로컬에서 돈다(stdio). 키는 사용자 머신의 `~/.pds/keys.json`에만 존재.

### 6.2 `pds-keys` 툴

| 툴 | 동작 |
| --- | --- |
| `login_portal` | 로컬 브라우저(Playwright headed)를 띄워 사용자가 직접 로그인. storage_state를 `~/.pds/session.json`에 저장. 비밀번호는 서버가 보지 않음 |
| `apply_key` | `dataset_id` → 포털 활용신청 폼 자동 입력·제출. 자동승인이면 즉시 키 반환, 심의면 `pending`. `channel=external`이면 자동화하지 않고 `external.steps`를 안내로 반환 (`status: "manual"`) |
| `get_key` | `dataset_id` → 로컬 키 반환 (Decoding). 없으면 `apply_key` 안내. 외부 사이트 키는 사용자가 `set_key`로 직접 등록 |
| `set_key` | `dataset_id, key` → 외부 사이트에서 받은 키를 로컬에 저장 |
| `list_keys` | 보유 키·승인 상태·트래픽 잔량 |
| `call` | `dataset_id, params` → 로컬 키로 직접 호출, 정규화된 결과. 전략 서버 응답의 `fetch`를 그대로 넘기면 된다 |

### 6.3 사용 흐름 (Claude Desktop 예)
```
사용자: 성수동 상권 변화 추적하고 싶어
Claude → pds-strategy.plan_public_data_strategy(goal) → 전략 JSON
Claude → pds-keys.get_key("15081808") → 없음 → apply_key → 자동승인 → 키
Claude → pds-keys.call("15081808", fetch.params) → 데이터
Claude → (Phase 5 코드 템플릿 제시) "이 코드를 돌리면 매달 갱신됩니다"
```
GPT는 Custom GPT Actions로 같은 두 서버를 HTTP로 노출. 에이전트 프레임워크는 MCP 클라이언트로 직접.

**완료 기준**: Claude Desktop에서 위 흐름이 사람 개입 없이(로그인 제외) 끝까지 돈다.

---

## 7. 작업 순서 (Claude Code 세션 단위)

| # | 세션 | 산출물 | 사람 검토 |
| --- | --- | --- | --- |
| 1 | ingest + 3축 분류 + prelim_score | Postgres 적재, 점수 | — |
| 2 | Phase 1 HTML 리포트 | `reports/phase1_ranking.html` | **구름과 대화 → sectors/, targets.json** |
| 3 | Playwright 로그인·활용신청·키 추출 | `pds/probe/portal.py` | 최초 로그인 1회 |
| 4 | deep probe a~i | `probe/runs/*.json`, stats, parquet | 표본 5행 육안 |
| 5 | 도시에 초안 생성 + index | `knowledge/dossiers/*.md` | **도시에별 승인** |
| 6 | 법령·부문 문서 | `knowledge/laws/`, `sectors/` 보강 | 법령 조항 확인 |
| 7 | 전략 플래너 + 스키마 + 골든셋 | `pds/strategy/`, 골든셋 50 | **정답 전략 작성** |
| 8 | 코드 생성기 + 실행 검증 | `pds/codegen/`, `out/` | — |
| 9 | pds-strategy MCP 서버 | `pds/mcp/strategy_server.py` | — |
| 10 | pds-keys MCP 서버 | `pds/mcp/keys_server.py` | Claude Desktop 시연 |
| 11 | (선택) 검색 UI — DESIGN.md §6 | 도시에 위의 얇은 검색 | — |

세션 2, 5, 7이 이 프로젝트의 무게중심이다. 코드보다 사람과의 대화 시간이 길다.

---

## 8. 원칙 (변하지 않는 것)

1. **실물 우선.** 메타가 뭐라 하든 실제 호출·다운로드·통계로 확인한 것만 도시에에 쓴다.
2. **근거 없는 추천 금지.** 전략 응답의 모든 `why`는 도시에 섹션 링크를 가진다. 링크가 깨지면 응답이 거부된다.
3. **키는 사용자 것.** 시스템은 사용자 키를 저장하지도 대리 호출하지도 않는다. 검증용 키는 Phase 2에만 쓴다.
4. **API 우선.** 파일데이터는 API가 없을 때만 도시에 대상이 된다.
5. **사람이 확정한다.** 부문, 대상, 도시에 승인, 골든셋 정답은 자동화하지 않는다.

---

## 9. 접근 경로 (portal / external)

데이터에 닿는 길은 둘이다. 전략 응답·도시에·코드 생성·키 서버가 모두 이 구분을 쓴다.

| channel | 뜻 | 키 | 자동화 | 예 |
| --- | --- | --- | --- | --- |
| `portal` | data.go.kr 게이트웨이(apis.data.go.kr)로 호출, 포털 파일 다운로드 | 포털 활용신청 키 | Phase 2·6에서 활용신청 자동화 | 아파트 실거래가, 상가(상권)정보 |
| `external` | 포털엔 목록·안내만 있고 실제 API·파일은 기관 사이트 | 기관 사이트에서 따로 발급 | 가입·발급은 사람. 이후 호출은 동일하게 자동 | 연속지적도(VWorld), 환율(한국수출입은행), 지하철 실시간(서울 열린데이터광장) |

판정: 벌크 메타에서 `목록유형=API & API유형=LINK` → external API, `제공형태=기관자체에서 다운로드` → external FILE. Phase 2에서 실제로 확인해 도시에에 확정한다.

원칙:
- 랭킹 점수에서 external을 깎지 않는다. 불편함은 응답의 `access`에 절차로 드러낸다.
- 전략 응답에서 external 데이터는 `access.external.steps`를 반드시 채운다. 사람이 처음 봐도 어디 가서 무엇을 하면 되는지 알 수 있어야 한다.
- 코드 생성기는 external 키를 `PDS_KEY_{dataset_id}` 환경변수로 받는다. 포털 키와 섞지 않는다.


---

## 10. 데이터 패밀리 (2026-09-28 추가)

여러 API가 한 업무 절차를 단계별로 나눠 제공하는 경우(예: 조달청 나라장터 18종), 데이터 1건 단위 도시에만으로는 "어느 API를 어떤 순서로, 어떤 번호로 이어 부르나"를 전달할 수 없다. 이를 **데이터 패밀리**로 따로 저장한다.

- 표준: `knowledge/families/README.md`, 스키마 `knowledge/families/_schema.json`, 검증 `python -m pds family-check <slug>`
- 형식: `family.yaml`(원본 그래프: 엔티티·키·데이터셋·엣지·레시피) + `family.md`(사람용 설명·다이어그램) + `operations.md`(공식 참고자료에서 자동 생성)
- 엣지 타입: lifecycle / lookup / join / reference / hierarchy / mirror / derived / aggregate
- 엣지 상태: documented(문서) → inferred(추론) → verified / refuted(Phase 2 실호출). 원칙 1(실물 우선)을 관계에도 적용
- Phase와의 관계:
  - Phase 1.5: 부문 검토 중 묶음이 보이면 패밀리 작성 (첫 사례: `pps-procurement`)
  - Phase 2: `inferred` 엣지를 실제 호출로 검증
  - Phase 3: 도시에의 "어울리는 데이터(연계)"는 패밀리를 링크. index 시 `pds_family*` 테이블로 적재
  - Phase 4: 전략 엔진이 `lookup` 엣지로 호출 경로를 계산하고, `recipes`를 `knowledge/recipes/`로 승격

---

## 11. 지식 저장 아키텍처 (2026-09-28 추가)

분석 결과(부문·세부 부문·결정·제외·이관·패밀리·조인 키·판정)를 **설명과 관계를 함께** 저장해, 이후 그래프 탐색·벡터 검색으로 "사용 방법을 제시할 때" 근거로 쓴다. 규약 전문: `knowledge/ARCHITECTURE.md`.

- **파일이 원본, DB는 컴파일 산출물.** 사람이 고치는 곳은 `knowledge/`(yaml·md, git)뿐
  - `knowledge/keys/{id}.yaml` 전역 조인 키 원장 · `sectors/{sector_map,subsectors,exclusions}.yaml` 결정 · `sectors/<분야>/<영역>.md` 부문 설명서 · `families/` 패밀리
- **세부 부문**: BRM 정책영역 → 세부 부문 2단. 원칙 "행정 프로세스 1개 = 근거법 1개+ = 개별 코드 1종". 정책영역 하나가 곧 부문이면 세부 없음. 깊이: front(앞)/back(뒤)/hold(보류)/system(시스템 자체 문서). 선거처럼 이벤트 주기면 `cycle: event`로 freshness 예외
- **지식 그래프**: 노드(`<type>:<key>`)·엣지·문서(md 섹션 단위)·청크(벡터화 단위) 네 테이블. 새 개념은 새 type 값으로 추가(스키마 변경 없음)
  - `python -m pds kg-build` → `data/processed/kg/*.parquet·jsonl`, `python -m pds kg-load` → Postgres `pds_kg_*`
  - 임베딩은 DB 밖(`data/embeddings/`), 청크 hash로 캐시
  - 소비: 벡터는 입구(질문 → 청크 → 노드), 그래프는 설명(노드 → 부문·패밀리·조인 키·lookup 경로)
- **마이그레이션**: `sql/NNN_*.sql` 번호 순 자동 적용, `pds_schema_migrations`에 체크섬 기록. 적용된 파일은 고치지 않고 새 번호로 ALTER. 001은 2026-09-28 기준선, 002 지식 그래프, 003 기준선 보정

**키 발급처 (2026-09-28 추가).** 외부 채널은 사이트마다 키 체계가 다르다 — 법제처 `open.law.go.kr`(OC 파라미터), 국회 `open.assembly.go.kr`(KEY), VWorld(key), 포털(serviceKey). 발급처 목록은 `knowledge/key_issuers.yaml`, 전략 응답은 `access.key_issuer`로 표시하고, Phase 6 `pds-keys`는 data.go.kr 외 발급 흐름도 지원해야 한다. 계정·키 값은 `.env`에만 있고 파일·DB·로그에는 변수 이름만 남긴다. 계정 값을 쓰는 자동 로그인은 §2.2(사람이 로그인) 원칙과 충돌하므로 Phase 2에서 확인 후 결정.

**시의성 축 (2026-09-28 추가).** "LLM이 이미 아는가"를 랭킹 축(novelty, 0.10)으로 둔다. 법령 본문·규칙처럼 이미 공개·학습된 내용은 낮게, 당일 올라오는 의안·판례·표결·공고는 높게. 세부 부문 정의(`subsectors.yaml` `novelty`)가 판정 원본이고, 실측은 Phase 2 단계 j `event_to_publish_lag`.

