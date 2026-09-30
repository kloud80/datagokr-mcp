# PDS Phase 3 — 지식 체계 설계 명세 (KNOWLEDGE-SPEC v1)

작성: 2026-09-30 · 대상: Claude Code · 전제: `BUILD-PLAN.md`(6단계 계획)와 Phase 1·2 산출물(`knowledge/`, `probe/`, `data/processed/`)
이 문서는 BUILD-PLAN Phase 3~4의 **"어떻게"**를 확정한다. Phase 3의 산출물은 더 이상 사람이 쓰는 설명서 markdown이 아니라 **스키마로 검증되는 지식 파일과 거기서 렌더링되는 설명서**다.

> **적용 메모 (2026-09-30, Claude)** — 이 리포에 적용하면서 달라진 점. 본문과 어긋나면 이 메모가 우선한다.
> 1. **pgvector 없음.** 회사 개발 DB는 PostgreSQL 17.6이고 `vector` 확장이 설치 가능 목록에도 없다(`pg_trgm` 1.6만 설치됨, 2026-09-30 조회).
>    임베딩은 ARCHITECTURE §2.3 결정대로 **DB 밖** `data/embeddings/<model>/`(청크 hash 키 parquet)에 두고, DB와는 id로만 잇는다. 벡터 검색은 로컬 인덱스.
> 2. **DB 스키마·테이블 접두어 유지.** `.env`의 `POSTGRES_SCHEME`, 테이블 접두어 `pds_`. 새 테이블은 `sql/006_…`부터 번호 마이그레이션.
> 3. **기존 지식 그래프(`pds_kg_*`, `pds/knowledge/compile.py`)는 버리지 않는다.** 7종 엔티티는 같은 노드·엣지 모델에 새 type(`claim`, `mapping`, `recipe`, `gap`, `law`)과
>    엣지(`joinable`, `lookup` …)로 들어가고, 원본 yaml 위치만 명세대로 바뀐다(`knowledge/keys/`, `knowledge/contexts/`, `knowledge/gaps.yaml`).
> 4. **Claim kind에 `access` 추가.** §2.2 승격 조건(cadence·key·access)과 §7-3(승인유형 → access claim)이 요구하는데 §3.5 목록에 없어서.
> 5. **검증 두 단계.** `pds validate`는 스키마·참조 오류를 막고, §2.2 승격 조건(Claim ≥ 3·Edge ≥ 1)은 `pds validate --strict`에서만 오류로 본다.
>    Phase 3 작업 순서상 Edge(§7-5)보다 Dataset 생성(§7-2)이 먼저라, 그 사이에는 경고로 둔다.
> 6. **여덟 번째 엔티티 CodeList(코드표)** — `knowledge/codes/{id}.yaml`(+parquet), 필드는 `schema.fields[].code_list`로 연결 (구름 2026-09-30 제안:
>    "코드와 이름이 있는 데이터는 코드표를 설명에 담아야 AI가 데이터를 불러들이는 품질이 달라진다"). 순서는 **필드 전수 판정(`pds/codes/needs.py`,
>    reports/code_needs.md) → 확보 계획(`knowledge/codes/_plan.yaml`) → 원천 확보(`pds/codes/build.py`)**. completeness: complete(공식 전체)·master_scan(전수 원장 스캔)·observed(표본).

---

## 0. 결정 요약

| 결정 | 내용 | 근거 |
| --- | --- | --- |
| 지식 단위 | 엔티티 7종: Dataset · Key · Mapping · Edge · Claim · Context · Recipe | 최종 출력 프로토콜을 역설계하면 정확히 이 7종이 필요 |
| 원본 형식 | YAML + JSON Schema 검증, git 관리 | 사람 리뷰·diff·승인. Phase 1·2 yaml과 연속 |
| 파생 저장 | Postgres 16 (nodes/edges/claims 테이블 + pgvector + tsvector) — yaml에서 빌드, 손으로 안 고침 | DataHub 패턴 "문서 원본 + 파생 그래프 인덱스" |
| 설명서(dossier) | 엔티티가 아니라 **뷰** — yaml에서 markdown 렌더링. Family 단위로 1장 | §10.3-1 답 |
| 조인 | LLM이 생성하지 않고 **선언된 Edge 중에서 선택** | dbt 2026 벤치마크: 생성 84~90% vs 선택 98~100% |
| 사실 표현 | 모든 "왜"는 Claim(값+근거+확인일+랭크). 근거 없는 claim은 신뢰 감점 | Wikibase statement 구조 |
| 커버리지 | **3층**: verified(검증 231) / candidate(선정됐으나 미검증) / catalog(9.6만 메타만) — 프로토콜은 세 층을 모두 출력하되 라벨을 다르게 | "핵심부터, 나머지는 시간 두고 붙인다" |
| 온톨로지·RDF | 안 씀. DCAT/schema.org는 외부 export 전용 | LLM에 트리플을 직접 먹이는 실사례 없음 |

---

## 1. 채택 표준·오픈소스 (전부 특정)

### 1.1 표준 어휘 (필드명·의미를 그대로 차용)

| 우리 필드 | 차용 원천 | 비고 |
| --- | --- | --- |
| `dataset.distributions[]` / `services[]` | W3C DCAT 3 `Distribution` / `DataService` | 파일 vs API 구분. https://www.w3.org/TR/vocab-dcat-3/ |
| `dataset.accrual_periodicity` | DCAT `dcterms:accrualPeriodicity` | 명세상 주기(실측은 claim) |
| `dataset.applicable_legislation[]` | DCAT-AP 3.0 `dcatap:applicableLegislation` | 법령ID+조문. https://semiceu.github.io/DCAT-AP/releases/3.0.0/ |
| `dataset.schema.fields[]`, `primary_key`, `foreign_keys[]` | Frictionless Table Schema | https://specs.frictionlessdata.io/table-schema/ |
| `field.semantic_type` | Croissant `Field` 시맨틱 타입 발상 | 값 = Key id (예: `pnu`) |
| `key.type` = primary / foreign / natural / unique | dbt MetricFlow `entities.type` | https://docs.getdbt.com/docs/build/semantic-models |
| `edge.relationship` = one_to_one / one_to_many / many_to_one / many_to_many, `edge.direction` | Cube `joins.relationship` + LookML `relationship` | 조인 경로 탐색·fan-trap 방지 |
| `dataset.sla` {frequency, latency, time_of_availability}, `dataset.team`, `authoritative_definitions[]` | ODCS v3 (Bitol) | https://bitol-io.github.io/open-data-contract-standard/latest/ |
| `service.security` {scheme: apiKey, in: query, name: serviceKey} | OpenAPI 3.1 `securitySchemes` | 키 발급처별 인증 표현 |
| `dataset.synonyms[]`, `field.sample_values[]`, `recipe.verified_queries[]` | Snowflake Semantic View YAML의 LLM 전용 필드 | 에이전트 정확도용 |
| `claim` {value, evidence[], qualifiers, rank} | Wikibase statement | 값+근거+한정자+랭크 |
| MCP `Resource`(카드) / `Tool`(실행) / `annotations.priority·lastModified` | MCP spec 2025-06-18 | 노출 계층 |

### 1.2 오픈소스·라이브러리 (버전 고정)

| 용도 | 채택 | 대안(불채택 이유) |
| --- | --- | --- |
| YAML 스키마 검증 | `jsonschema` 4.x + `pydantic` 2.x (모델 = 스키마 원본, `model_json_schema()`로 export) | Cerberus (JSON Schema 호환 약함) |
| 원본 저장 | git + `ruamel.yaml`(주석 보존) | 위키 엔진 (편집 통제 어려움) |
| 파생 DB | Postgres 16 + `pgvector` 0.7 + `pg_trgm` | Neo4j (규모 대비 과함, 3단계 후 재검토) |
| 그래프 탐색 | `networkx` 3.x (yaml→그래프 빌드, 최단 조인 경로, 3단계 확장) | Cube 자체 (BI 전용) |
| 임베딩 | `BAAI/bge-m3` via `sentence-transformers` | OpenAI embedding (오프라인 불가) |
| 한국어 토크나이저 | `kiwipiepy` 0.18+ | mecab (설치 부담) |
| 매핑표 | `pyarrow`/`parquet` + yaml 헤더, 매칭은 `rapidfuzz` + 주소 정규화(`business.juso.go.kr` API) | 순수 문자열 매칭 |
| 설명서 렌더링 | `jinja2` 템플릿 → markdown, `mkdocs-material`로 사이트 (선택) | 손 작성 |
| 법령 원문 | 법제처 open.law.go.kr API (키 확보됨), 캐시는 `knowledge/laws/{id}.yaml` | 크롤링 |
| 코드 생성 | `jinja2` 결정적 렌더 (BUILD-PLAN Phase 5), 검증은 `pytest` + 실호출 | LLM 생성 (비결정적) |
| MCP 서버 | `mcp` Python SDK 1.x (FastMCP), stdio + Streamable HTTP | 자체 프로토콜 |
| 평가 | 자체 `pds/eval` — nDCG·recipe 일치율, `ragas`는 불채택 | — |
| 외부 export | `rdflib`로 DCAT 3 / schema.org JSON-LD 생성 (Phase 5 이후, 선택) | — |

---

## 2. 커버리지 3층 모델 — "핵심부터, 나머지는 붙여 나간다"

포털 96,110건 전체를 한 시스템에 두되, **지식의 깊이를 3층으로 구분**한다. 프로토콜은 세 층을 모두 낼 수 있고, 층마다 라벨과 신뢰가 다르다.

| 층 | `tier` | 대상 | 지식 | 프로토콜 출력 |
| --- | --- | --- | --- | --- |
| **verified** | 검증 완료 | Phase 2 verdict=성공 231건 (+ 이후 검증 추가분) | Dataset yaml 완전, Claim에 `measured` 근거, Edge 선언 | `datasets[]`에 정식 추천, `joins[]`·`pipeline[]`에 참여 |
| **candidate** | 선정·미검증 | targets.json에 있으나 실패·보류·미실행 64건 + 세부 부문 차순위 | Dataset yaml 부분(메타·부문·키 후보), Claim은 `portal_meta` 근거뿐 | `candidates[]`에 "선정됐으나 미검증" 라벨, 조인 참여 불가 |
| **catalog** | 메타만 | 나머지 ~95,800건 (제외 50,281건 포함, 제외는 `excluded_by` 표시) | 벌크 메타 + 3축 분류 + prelim_score + 임베딩 | `unverified_leads[]`에 "관련성 있어 보이는 제목 — 직접 확인 필요" 라벨 |

### 2.1 catalog 층이 프로토콜에 나오는 규칙

목표 임베딩과 catalog 층 Dataset 임베딩(제목+desc_user+컬럼명)의 코사인 ≥ 0.72, 또는 verified 데이터셋과 `same_agency`·`same_law`·`title_pattern` 중 하나 이상 공유 → `unverified_leads[]` 후보. 상위 5개만, 각각 `why_maybe`(한 줄, 규칙 기반 템플릿)·`what_to_check`(활용신청·컬럼·갱신)·`portal_url`을 붙인다. **추천이 아니라 단서**임을 스키마 필드명(`leads`)과 문구로 못 박는다.

### 2.2 승격 경로 (시간이 지나며 붙이는 방법)

```
catalog ──(관리자 선정 or 사용자 요청 or 리드 클릭 누적)──▶ candidate ──(Phase 2 검증 절차 통과)──▶ verified
```

- 승격은 `pds promote {id} --to candidate|verified` 한 명령. candidate로 올리면 Dataset yaml 골격이 벌크 메타에서 자동 생성되고, verified로 올리려면 probe 성공 + Claim ≥ 3(cadence·key·access) + Edge ≥ 1이 있어야 한다(스키마 검증으로 강제).
- 프로토콜에서 `unverified_leads`가 클릭·호출된 로그는 `feedback_event(kind=lead_followed)`로 남고, 누적 N회 이상이면 관리자 큐 `promote`에 오른다. **리드 노출 → 사용 → 승격**이 나머지 9만 건을 붙여 나가는 루프다.
- 세부 부문 312개 중 front 291개는 "대표 1건"만 verified다. 같은 세부 부문의 2~5순위가 candidate 층의 자연스러운 다음 대상.

---

## 3. 엔티티 7종 스키마

모든 파일은 `knowledge/` 아래, `pds/schema/*.py`(pydantic)가 스키마 원본이고 `schemas/*.json`으로 export한다. 아래는 필드 요지. 실제 pydantic 모델을 이 표대로 작성할 것.

### 3.1 Dataset — `knowledge/datasets/{sector}/{id}.yaml`

```yaml
id: "15126469"                      # 포털 목록키 (외부는 issuer 접두: "vworld:…")
tier: verified                      # verified | candidate | catalog(파일 없음, DB만)
title: 국토교통부_아파트 매매 실거래가 자료
family: rtms-transactions           # 같은 설명서로 묶는 묶음 (없으면 생략)
sector: 국토관리/주택/real-estate-transactions
domain: 국토기본법/주택               # 법 계층
agency: {id: "1613000", name: 국토교통부}
kind: API                           # API | FILE | STD | EXTERNAL_API | EXTERNAL_FILE
channel: portal                     # portal | external
synonyms: [실거래가, 아파트 매매가, RTMS]
summary_user: |                     # LLM 재작성 3문장 (임베딩 대상)
  ...
applicable_legislation:
  - law: "부동산거래신고법"           # knowledge/laws/{id}.yaml 참조
    law_id: "011369"
    articles: ["3", "6"]
accrual_periodicity: daily          # 명세상. 실측은 claims[cadence]
sla: {frequency: daily, latency_days: 30, time_of_availability: "익일"}   # ODCS
team: {dept: 주택토지실 부동산소비자보호기획단, phone: "..."}
services:                           # DCAT DataService / OpenAPI 요지
  - op: getRTMSDataSvcAptTrade
    endpoint: https://apis.data.go.kr/1613000/RTMSDataSvcAptTrade/...
    method: GET
    security: {scheme: apiKey, in: query, name: serviceKey, issuer: data.go.kr}
    params: [{name: LAWD_CD, required: true, semantic_type: sgg_cd, example: "11110"},
             {name: DEAL_YMD, required: true, format: YYYYMM}]
    paging: {page: pageNo, size: numOfRows, max_size: 1000}
    approval: auto
    traffic: {dev: 1000, prod: 100000}
    format: [xml, json]
    error_style: http200_body_code    # 200인데 본문 오류
distributions: []                   # 파일이면 여기 (url, format, size, updated)
schema:                             # Frictionless
  primary_key: null                 # 실거래는 없음 → dedupe_rule로 대체
  dedupe_rule: [dealYear, dealMonth, dealDay, umdNm, jibun, floor, excluUseAr, dealAmount]
  fields:
    - {name: sggCd, type: string, semantic_type: sgg_cd, null_rate: 0.0, sample_values: ["11110"]}
    - {name: dealAmount, type: integer, unit: 만원, null_rate: 0.0, stats: {min: 500, p50: 62000, max: 1150000}}
  foreign_keys:                     # Frictionless 형식, 대상은 Key id
    - {fields: [sggCd], reference: {key: sgg_cd}}
facets: {}                          # 공통 원장(LOCALDATA 등)이면 {업종: [...]} 필터 축
coverage: {spatial: 전국, admin_unit: 필지·건물, temporal: "2006-01~"}
cycle: default                      # default | event | annual-batch | realtime | ended
claims: [...]                       # §3.5
edges_hint: [15126474, 15126468]    # 자동 매핑 후보 (Edge는 별 파일)
verification:                       # probe 요약 링크
  verdict: 성공
  probed_at: 2026-09-29
  rows: 2000
  total_count: 178691
  run: probe/runs/15126469.json
  stats: probe/stats/15126469.json
limits: |                           # 한계와 대체
  ...
status: active                      # active | suspect_dead | hidden | ended
```

**catalog 층**은 yaml 파일을 만들지 않는다. `data/processed/catalog.parquet`의 행 + 임베딩만 있고, 스키마의 `id·title·sector·agency·kind·prelim_score·excluded_by·embedding` 필드만 채워진 상태로 DB에 적재된다.

### 3.2 Key — `knowledge/keys/{id}.yaml` (기존 keys.yaml을 분리)

```yaml
id: pnu
name: 필지고유번호
type: natural                       # primary | foreign | natural | unique (dbt)
pattern: '^\d{19}$'
master_datasets: ["15051939"]        # 원장
composed_of: [bjd_cd, 대장구분, 본번, 부번]   # 합성 키면
issuer: 국토교통부                    # 코드 부여 주체
related_keys: [{key: bjd_cd, relation: prefix}]
notes: ...
```

### 3.3 Mapping — `knowledge/mappings/{a}__{b}.yaml` + `.parquet`

```yaml
id: school_cd__neis_school_cd
left: {key: school_cd, system: 표준데이터 학교ID}
right: {key: neis_school_cd, system: 나이스}
method: name_address_match          # exact | name_address_match | coord_nearest | manual
built_at: 2026-10-05
rows: 12011
match_rate: 0.94
unmatched_policy: keep_left         # 매핑 실패 시 조인 처리
file: mappings/school_cd__neis_school_cd.parquet   # 컬럼: left_value, right_value, confidence, method
```

**Phase 3 착수 시 먼저 만들 매핑 5개**: 학교(3체계), 의료기관(ykiho·hpid·LOCALDATA), 사회복지시설(시설코드·장기요양·어린이집·유치원), 교통 노드(역·정류장), 공동주택 단지(K-apt·실거래 단지명·청약). 이것 없이는 Edge를 선언할 수 없다.

### 3.4 Edge — `knowledge/edges.yaml` (한 파일, 빌드 시 DB로)

```yaml
- id: e-0001
  src: "15126469"
  dst: "15051939"                    # 연속지적도 / 토지대장
  rel: joinable                      # joinable | lookup | instance_of | supersedes | same_concept | continues | related_to
  on: {left: [sggCd, umdNm, jibun], right: [pnu], via_mapping: null, transform: "sgg+umd+jibun → pnu 조립 규칙 R-07"}
  relationship: many_to_one          # Cube/LookML 카디널리티
  direction: src_to_dst
  verified: {by: measured, run: probe/joins/e-0001.json, match_rate: 0.97, at: 2026-10-06}
  source: admin                      # auto | admin | user
  confidence: 1.0
```

- `lookup`은 "src를 호출하려면 dst의 값이 필수 파라미터"(§9-1 호출 체인). Phase 2 `파라미터부족` 8건이 여기서 해소된다.
- `verified.by=measured`가 없는 Edge는 프로토콜 `joins[]`에 나오되 `confidence` 낮음 표시. Phase 3에서 **Edge 실측 프로브**(`pds/probe/join.py`: 양쪽 샘플 받아 키 매칭률 계산)를 추가한다.

### 3.5 Claim — Dataset yaml 안 `claims:` (별도 파일 아님)

```yaml
claims:
  - id: c-15126469-01
    kind: cadence           # cadence | publish_lag | legal_basis | key | coverage | health | pitfall | join_verified | admin_note
    value: "일 갱신, 계약 후 30일 내 신고분이 순차 반영, 해제·정정은 소급"
    evidence:
      - {type: measured, source: "probe/runs/15126469.json#lag_days", observed_at: 2026-09-29, detail: "lag 2일"}
      - {type: law, source: "law:011369#3", detail: "30일 내 신고 의무"}
      - {type: admin_review, source: "knowledge/sectors/_review_log.md#주택", by: 구름, at: 2026-09-29}
    qualifiers: {applies_to: "매매", since: "2024-08"}
    rank: preferred         # preferred | normal | deprecated
    valid_until: 2027-03-31
```

- `evidence.type`: measured(프로브) · law(법제처) · portal_meta(벌크 메타) · admin_review(검토 기록) · inferred(LLM 초안, 승인 전) · user(피드백)
- **규칙**: `inferred`만 있는 claim은 설명서에 "(미확인)" 표시, 프로토콜 `evidence`에 안 나감. `deprecated`는 `not_recommended` 사유가 된다. `valid_until` 지난 claim은 관리자 큐 `recheck`.
- Phase 1·2 검토 기록(§4 논의 기록, yaml `reason`·`note`)은 스크립트로 `admin_review` claim으로 일괄 변환한다 — 수십 개가 이미 확보돼 있다.

### 3.6 Context — `knowledge/contexts/{id}.yaml` (기존 41개 유지, 필드 추가)

```yaml
id: early-childhood-care
dimension: life_context             # life_context | spatial_regulation | admin_area | shared_key | shared_source | same_concept | economic
question: 우리 아이 어디에 맡길까 — 어린이집·유치원·돌봄
members: [{dataset: "…", role: primary}, {dataset: "…", role: join}]
requires_mappings: [childcare_center_cd__kindergarten_cd]
recipe: recipes/early-childhood-care.yaml     # Phase 4에서 채움 (골든셋 정답)
```

### 3.7 Recipe — `knowledge/recipes/{slug}.yaml` (검증된 파이프라인 = 골든셋 정답)

```yaml
id: early-childhood-care
goal_examples: ["성수동 어린이집 유치원 정원 비교", "…"]   # Snowflake verified_queries 발상
context: early-childhood-care
datasets: [{id: "…", role: primary}, {id: "…", role: join}]
joins: [e-0113, e-0114]              # Edge id만 — 여기서 새 조인을 만들지 않는다
pipeline:
  - {step: 1, do: fetch, dataset: "…", params: {bjd_cd: "$place"}, produces: childcare.parquet}
  - {step: 2, do: fetch, dataset: "…", produces: kindergarten.parquet}
  - {step: 3, do: join, edge: e-0113, produces: facilities.parquet}
  - {step: 4, do: aggregate, by: [bjd_cd], measures: [capacity_sum]}
schedule: {cron: "0 3 5 * *", reason: "어린이집 공시 매월 초 갱신 (c-…-02)"}
verified: {code_run: out/early-childhood-care/run.log, at: 2026-10-20, ok: true}
author: 구름
```

---

## 4. 출력 프로토콜 최종 스키마 (MCP `plan_public_data_strategy` 출력)

```json
{
  "goal": "…", "sector": "…", "summary": "…",
  "datasets": [ { "id", "tier": "verified", "role": "primary|join|context|lookup",
                  "why": "…", "evidence": ["c-…-01", "c-…-03"],
                  "access": {"issuer","scheme","approval","daily_limit","latency_p95_ms"},
                  "fetch": {"op","endpoint","params","paging","format"},
                  "caveats": ["c-…-05"] } ],
  "joins": [ { "edge": "e-0113", "left", "right", "on", "relationship", "via_mapping", "confidence" } ],
  "pipeline": [ … ],
  "schedule": { "cron", "reason", "evidence" },
  "candidates": [ { "id", "tier": "candidate", "title", "sector", "status": "승인대기|파라미터부족|…",
                    "why_maybe": "…", "blocked_by": "…" } ],
  "unverified_leads": [ { "id", "tier": "catalog", "title", "agency", "kind", "portal_url",
                          "similarity": 0.78, "why_maybe": "제목·컬럼이 목표와 유사 / 같은 기관·법령",
                          "what_to_check": ["활용신청 승인유형", "출력 컬럼에 bjd_cd 존재 여부", "최근 수정일"],
                          "note": "미검증 — 직접 확인 후 판단" } ],
  "not_recommended": [ { "id", "reason", "evidence" } ],
  "gaps": [ "…" ],                         // knowledge/gaps.yaml (§10.2 공백 목록)
  "confidence": 0.78,
  "knowledge_version": "2026-10-20T…"      // git commit
}
```

**검증 규칙(서버가 응답 전에 강제)**: `datasets[].evidence`의 모든 claim id가 존재하고 `inferred`만인 것이 없을 것 · `joins[].edge`가 edges.yaml에 존재할 것 · `unverified_leads`는 최대 5개, `tier=catalog`만 · `candidates`에는 조인 참여 없음. 하나라도 어기면 응답 거부.

---

## 5. 저장·빌드 파이프라인

```
knowledge/*.yaml ──validate(pydantic)──▶ pds build ──▶ Postgres
   │                                               ├─ nodes(datasets 3층), edges, claims, keys, mappings(parquet 참조)
   │                                               ├─ embeddings (bge-m3: summary_user+컬럼명+synonyms)
   │                                               └─ tsv (kiwi)
   └──render(jinja2)──▶ docs/dossiers/{family}.md  (설명서 뷰) ──▶ MCP Resource dataset://{id}
```

- `pds build`는 멱등, CI에서 PR마다 실행(스키마 실패 시 머지 불가).
- 그래프 탐색은 빌드 시 `networkx`로 `edges` → 인접 리스트를 만들어 DB에 캐시. 전략 플래너는 DB만 읽는다.
- catalog 층 96k는 벌크 적재 배치(Phase 1 파이프라인)가 계속 채운다. verified/candidate yaml이 catalog 행을 **덮어쓰지 않고 join**한다(같은 id, `tier` 컬럼으로 구분).

---

## 6. 전략 플래너 처리 순서 (`pds/strategy/plan.py`)

1. 목표 → 슬롯 추출(지역·기간·대상) + 의도 분류 (BUILD-PLAN 유지)
2. **Context 매칭**: `question` 임베딩 top-3 → 해당 Context의 Recipe가 있으면 그대로 사용(골든셋 경로)
3. Recipe 없으면: 부문 후보 → verified Dataset 후보 5~15 (임베딩+BM25, 기둥 안 검색)
4. **Edge 그래프에서 조인 경로 탐색** (networkx 최단 경로, `verified.by=measured` 우선, 카디널리티로 fan-trap 회피). 경로가 없으면 `gaps`에 "조인 경로 미선언"으로 보고 — LLM이 조인을 지어내지 않는다
5. candidate 층에서 같은 세부 부문·같은 Context 멤버 → `candidates[]`
6. catalog 층에서 §2.1 규칙 → `unverified_leads[]`
7. LLM은 `why`·`summary` 문장만 작성. 입력은 선택된 claim 텍스트, 출력은 claim id 인용을 강제(스키마 검증)
8. §4 검증 규칙 통과 후 반환

---

## 7. Phase 3 작업 순서 (Claude Code 세션 단위)

| # | 작업 | 산출물 | 완료 기준 |
| --- | --- | --- | --- |
| 1 | pydantic 스키마 7종 + JSON Schema export + `pds validate` | `pds/schema/`, `schemas/*.json` | 기존 keys/contexts/targets yaml이 검증 통과(필드 추가 마이그레이션 포함) |
| 2 | `pds gen-dataset {id}`: probe 결과 + 벌크 메타 → Dataset yaml 자동 생성 (231건) | `knowledge/datasets/**` | 231개 파일, `tier: verified`, verification·schema.fields 채움 |
| 3 | 검토 기록 → `admin_review` claim 일괄 변환, probe lag → `cadence`/`publish_lag` claim, 승인유형 → `access` claim | claims 블록 | Dataset당 claim ≥ 3 |
| 4 | 매핑 5개 (`pds/mapping/build_*.py`) | `knowledge/mappings/` | 각 match_rate 보고, 미매칭 정책 명시 |
| 5 | Edge 선언: 실측 키 보유(§7 요약)에서 자동 후보 → 관리자 확정, `lookup` 엣지로 파라미터부족 8건 재시도 | `knowledge/edges.yaml`, `pds/probe/join.py` | verified Dataset당 Edge ≥ 1, 실측 매칭률 기록 |
| 6 | 법령 층: `applicable_legislation` 참조 → 법제처 API로 `knowledge/laws/{id}.yaml` 채움 | laws/ | 참조된 법령 전부 원문 조문 확보 |
| 7 | LLM 초안: `summary_user`, `limits`, `inferred` claim 생성 → 구름 승인 큐 | — | family 단위 승인 |
| 8 | `pds build` + `pds render` + catalog 96k 적재 | Postgres, docs/dossiers | 설명서 렌더 231건, DB 3층 적재 |
| 9 | 갱신 관찰(7일 재호출)·공개 지연 실측 배치 시작 | probe/observe | cadence claim에 `measured` 근거 |
| 10 | Context 41 → Recipe 초안 (Phase 4 골든셋 시작) | recipes/ | 우선 10개 |

세션 4·5가 무게중심이다. 매핑과 Edge가 없으면 프로토콜의 `joins`가 비고, 그러면 이 시스템은 검색기와 다를 바 없다.

---

## 8. 설명서(dossier) 렌더 템플릿 (`templates/dossier.md.j2`)

Family 단위 1장. 섹션 순서와 각 섹션의 원천:

| 섹션 | 원천 |
| --- | --- |
| 한 줄 | `summary_user` 첫 문장 |
| 이 묶음의 데이터 | family 멤버 Dataset 표 (id·op·tier) |
| 법적 근거 | `applicable_legislation` + `laws/` 조문 원문 + claim[legal_basis] |
| 행정 처리 흐름 | claim[admin_note] + `inferred`(미확인 표시) |
| 공개 시점과 갱신 | `sla` + claim[cadence, publish_lag] (근거 유형 표시) |
| 컬럼 사전 | `schema.fields` (실측 통계 포함) |
| 조인 키·연결 | `foreign_keys` + Edge 목록(카디널리티·실측률) + 필요한 Mapping |
| 호출 방법·함정 | `services` + claim[pitfall] |
| 실측 요약 | `verification` |
| 어울리는 데이터 | Context 멤버 + Edge `related_to` |
| 아직 확인 안 된 이웃 | 같은 세부 부문 candidate + catalog 상위 리드 5개 (§2.1 규칙) |
| 한계와 대체 | `limits` + claim[health, deprecated] |

렌더 결과는 git에 커밋하지 않는다(파생물). MCP Resource로만 노출.

---

## 9. 추가로 작성해야 할 것 (BUILD-PLAN에 없던 항목)

1. `knowledge/gaps.yaml` — §10.2 공백 5건을 엔티티화. 프로토콜 `gaps[]`의 원천. 필드: sector, question, reason, external_candidate.
2. `knowledge/rules/` — 실거래 dedupe 규칙, PNU 조립 규칙(R-07), 주소 정규화 규칙 등 **transform 규칙 코드**. Edge `on.transform`이 참조. Python 함수 + 테스트.
3. `pds/probe/join.py` — Edge 실측 프로브(양쪽 샘플 키 매칭률). Phase 2에 없던 검증 유형.
4. `pds/probe/observe.py` — 7일 재호출·공개 지연(`event_to_publish_lag`) 배치. BUILD-PLAN §2.1 i 항목의 구현.
5. `pds/promote.py` — 3층 승격 명령과 스키마 강제.
6. `feedback_event.kind=lead_followed` — 리드 클릭·호출 로그와 관리자 큐 `promote`(BUILD-PLAN 큐 5종에 6번째 추가).
7. `pds/export/dcat.py` — 외부 공개용 DCAT 3 / schema.org JSON-LD (선택, Phase 5 이후).
8. `docs/CONTRIBUTING-knowledge.md` — yaml 편집 규칙: claim 없는 값 금지, evidence 유형, PR 승인자, `valid_until` 의무.

---

## 10. 원칙 (KNOWLEDGE-SPEC 고유)

1. **선언된 조인만 선택한다.** LLM은 Edge를 만들지 않는다.
2. **근거 없는 사실은 사실이 아니다.** claim에 `measured`·`law`·`admin_review` 중 하나가 없으면 프로토콜에 나가지 않는다.
3. **세 층은 섞이지 않는다.** verified만 추천, candidate는 후보, catalog는 단서. 필드명이 그 차이를 말한다.
4. **원본은 yaml, 나머지는 파생이다.** DB·설명서·임베딩은 언제든 다시 만들 수 있어야 한다.
5. **승격은 검증을 통과해야만 된다.** 관리자도 스키마를 우회할 수 없다.
