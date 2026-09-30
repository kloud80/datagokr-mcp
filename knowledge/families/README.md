# 데이터 패밀리 (Data Family) 표준 v1

작성 2026-09-28 · 첫 적용: [pps-procurement](pps-procurement/family.md) (조달청 공공조달 API 18종)

## 1. 패밀리란

**하나의 업무 흐름을 여러 데이터셋이 나눠서 제공하는 묶음**이다. 데이터 하나만 봐서는 쓸 수 없고, "어느 API가 어느 단계를 맡고, 어떤 번호로 서로 이어지는가"를 알아야 활용이 된다.

패밀리로 묶는 기준 (하나 이상 해당):
- 같은 기관·같은 시스템이 한 업무 절차를 단계별 API로 쪼개 제공 (예: 나라장터 발주계획 → 사전규격 → 입찰 → 낙찰 → 계약)
- 한 데이터의 출력 키가 다른 데이터의 조회 파라미터로 쓰인다 (호출 체인)
- 코드 마스터(기관코드, 물품분류, 업종코드)를 여러 데이터가 공유한다

도시에(`knowledge/dossiers/`)는 **데이터 1건**을 설명하고, 패밀리는 **데이터들 사이**를 설명한다. 도시에의 "어울리는 데이터(연계)" 섹션은 패밀리가 있으면 패밀리를 링크한다.

## 2. 저장 형식 — 왜 세 겹인가

| 파일 | 대상 | 역할 |
| --- | --- | --- |
| `family.yaml` | 기계 (전략 엔진·코드 생성기·검증기) | **원본 그래프.** 엔티티·키·데이터셋·엣지·레시피. 스키마 검증 대상 |
| `family.md` | 사람 (리뷰어·사용자) | 업무 흐름 설명, 다이어그램(mermaid), API별 역할, 함정, 레시피 해설. yaml과 어긋나면 yaml이 맞다 |
| `operations.md` | 사람·LLM | 오퍼레이션 전체 목록(요청 파라미터 포함). 공식 참고자료에서 **자동 생성**, 손으로 고치지 않는다 |

검토한 대안과 버린 이유:
- **그래프 DB(Neo4j 등)**: 노드 수가 패밀리당 수십 개라 과하다. git diff·리뷰가 안 된다. 필요하면 yaml에서 파생 적재한다.
- **md만**: 사람은 읽기 좋지만 전략 엔진이 "입찰공고번호로 계약을 찾는 경로"를 계산할 수 없다.
- **yaml만**: 업무 맥락(왜 이 순서인지, 법적 이유)이 빠진다.

Postgres 파생(Phase 3 index): `pds_family`, `pds_family_node`, `pds_family_edge`로 적재해 전략 단계에서 경로 탐색에 쓴다.

## 3. 그래프 모델

```
entity (업무 객체)  ──lifecycle──▶ entity          업무 절차 순서
   ▲ provides                                       
dataset / operation ──lookup──▶ dataset/operation   A의 출력 키를 B의 조회 파라미터로 (실행 가능한 체인)
dataset.field ──join──▶ dataset.field               출력끼리 같은 값 (변환 포함)
dataset.field ──reference──▶ master dataset         코드 → 코드 마스터
key ──hierarchy──▶ key                               상위/하위 코드
dataset ──mirror──▶ dataset                          같은 구조, 다른 모집단
dataset ──derived──▶ dataset(s)                      다른 데이터의 평탄화·부분 뷰
dataset ──aggregate──▶ dataset                       통계 집계 원천
```

### 3.1 노드

| 종류 | 필수 필드 | 설명 |
| --- | --- | --- |
| `entities[]` | `id`, `name`, `keys` | 업무 객체. 절차 단계(`stage`)가 있으면 순서를 적는다 |
| `keys[]` | `id`, `name`, `format`, `aliases` | 식별자. **데이터셋마다 필드명이 달라도 같은 키면 하나로 묶는다** (`aliases`). 전역 조인 키(`knowledge/keys.yaml`)와 같으면 `global_key`로 표시 → 지식 그래프에서 `same_as` 엣지 |
| `datasets[]` | `id`(목록키), `short`, `role`, `service` | 패밀리 구성 데이터셋 |

`datasets[].role` 어휘:

| role | 뜻 |
| --- | --- |
| `stage` | 업무 절차의 한 단계를 제공 (발주계획, 입찰공고, 계약 …) |
| `hub` | 여러 단계를 한 번에 이어주는 통합 조회 (키 하나로 전 과정) |
| `reference` | 코드·마스터 (기관, 업체, 물품분류, 업종) |
| `aggregate` | 통계·집계 |
| `derived` | 다른 데이터의 표준화·평탄화 뷰 |
| `mirror` | 같은 구조의 다른 모집단 (예: 민간 누리장터) |

### 3.2 엣지

모든 엣지 공통: `type`, `from`, `to`, `status`, `evidence`.

| type | 추가 필드 | 예 |
| --- | --- | --- |
| `lifecycle` | `via`(키) , `condition` | 입찰공고 → 낙찰 (via 입찰공고번호) |
| `lookup` | `key`, `from_field`, `to_param`, `to_ops`, `inqry_div` | 낙찰.`bidNtceNo` → 계약과정통합(`inqryDiv=1`, `bidNtceNo`) |
| `join` | `left`, `right`, `transform` | 계약.`ntceNo` = 입찰.`bidNtceNo`+`bidNtceOrd` |
| `reference` | `key`, `master_op` | `dminsttCd` → 사용자정보.`getDminsttInfo02` |
| `hierarchy` | `parent`, `child`, `rule` | 물품분류번호(8) → 세부품명번호(10) |
| `mirror` / `derived` / `aggregate` | `note` | |

`status` 어휘 — **원칙 1(실물 우선)을 그래프에도 적용한다**:

| status | 뜻 | 누가 올리나 |
| --- | --- | --- |
| `documented` | 공식 문서(참고자료·명세)에 적혀 있음 | 문서 파싱 |
| `inferred` | 필드명·샘플값으로 추론, 문서에 명시 없음 | 사람·LLM |
| `verified` | Phase 2 실제 호출로 값이 이어지는 것을 확인 | probe |
| `refuted` | 실제로는 안 이어짐 (삭제하지 않고 남긴다) | probe |

`evidence`: `"doc:<목록키>#<오퍼레이션>"`, `"probe:<run id>"`, `"web:<url>"`.

### 3.3 부가 섹션

- `conventions`: 패밀리 공통 호출 규칙 (URL 패턴, 오퍼레이션 접미사 의미, 조회구분 `inqryDiv`, 날짜 형식, 조회기간 제한, 중첩 리스트 필드 구문)
- `pitfalls`: 패밀리 공통 함정
- `recipes[]`: 검증된(또는 검증 대상) 호출 순서. `id`, `goal`, `steps[]`(`dataset`, `op`, `params`, `take`), `status`. Phase 4 `knowledge/recipes/`로 승격될 후보.

## 4. 작성 절차

1. 대상 데이터셋의 포털 Swagger와 **참고자료(docx)**를 받아 파싱 → `data/ref/families/<slug>/` (원문 파생 JSON, 재현용)
2. 오퍼레이션·요청 파라미터·응답 필드에서 식별자 후보 추출 → 키 묶기(`aliases`) → 엣지 초안 (`documented` / `inferred`)
3. 업무 절차 조사(기관 안내, 법령) → `entities`·`lifecycle`
4. `family.yaml` 작성 → `python -m pds family-check <slug>`로 스키마·참조 검증
5. `family.md` 작성, `operations.md` 자동 생성
6. 사람 검토 → Phase 2에서 `inferred` 엣지부터 실호출 검증 → `verified`/`refuted`

## 5. 파일 배치

```
knowledge/families/
├── README.md                 ← 이 문서 (표준)
├── _schema.json              ← family.yaml JSON Schema
└── <slug>/
    ├── family.yaml
    ├── family.md
    └── operations.md         ← 자동 생성
data/ref/families/<slug>/     ← 원문 파싱 결과 (reference_docs.json, swagger_ops.json)
```
