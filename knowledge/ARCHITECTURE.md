# PDS 지식 저장 아키텍처 v1 (Knowledge Store Protocol)

작성 2026-09-28 · 대상: 이 리포에서 분석한 모든 결과(부문·세부 부문·결정·제외·이관·패밀리·조인 키·판정)를
**설명과 관계를 함께** 저장해, 나중에 그래프 탐색이든 벡터 검색이든 "사용 방법을 제시할 때" 근거로 꺼내 쓰기 위한 규약.

> 2026-09-30: Phase 3 엔티티 스키마는 `KNOWLEDGE-SPEC.md`가 원본이다. 모든 지식 파일은 `pds/schema/`(pydantic)로 검증된다
> (`python -m pds validate`, JSON Schema는 `schemas/`). 옛 `keys.yaml`·`sectors/contexts.yaml`은 `knowledge/_superseded/`.

원칙: **파일이 원본, DB는 컴파일 산출물.** 사람이 고치는 곳은 `knowledge/`(git)뿐이고, 그래프·청크·임베딩은 언제든 다시 만든다.
새 타입이 나오면 규약(이 문서)과 마이그레이션을 같이 올리며 앞으로 간다.

---

## 1. 층 구조

```
L0 원천        data/raw/ (포털 벌크 메타), data/ref/ (참고자료 파싱본)                      재현용, git 밖(raw)·안(ref)
L1 카탈로그     data/processed/*.parquet → pds_catalog_dataset / pds_dataset_class / pds_dataset_score
               (python -m pds build / load-db)                                          매 스냅샷 재계산
L2 지식 원본    knowledge/  ← 사람이 쓰고 리뷰하는 유일한 곳 (git)
               ├─ keys/{id}.yaml                 전역 조인 키 원장 (KNOWLEDGE-SPEC §3.2, 2026-09-30 keys.yaml에서 분리)
               ├─ key_issuers.yaml               외부 키 발급처 (.env 변수 이름만)
               ├─ datasets/{분야}/{id}.yaml       Dataset 엔티티 — verified·candidate 층 (§3.1, claims 포함)
               ├─ edges.yaml                     데이터셋 사이 조인·lookup 선언 (§3.4)
               ├─ mappings/{a}__{b}.yaml·parquet 코드 체계 매핑표 (§3.3)
               ├─ contexts/{id}.yaml             맥락 연결 (§3.6, 2026-09-30 sectors/contexts.yaml에서 분리)
               ├─ gaps.yaml                      공백 — 포털에 없는 업무 영역 (§9-1, subsectors.yaml gaps에서 분리)
               ├─ laws/{law_id}.yaml             법령 원문 캐시 (§7-6)
               ├─ recipes/{slug}.yaml            검증된 파이프라인 = 골든셋 정답 (§3.7)
               ├─ sectors/sector_map.yaml        부문 재배치 결정
               ├─ sectors/subsectors.yaml        세부 부문 정의(규칙·깊이·주기·공백)
               ├─ sectors/sector_tree.yaml       부문 위 법 체계 계층(domain) — 예: 국토기본법 → 국토계획법 → 개별 개발사업법
               ├─ sectors/exclusions.yaml        프로젝트 제외 결정
               ├─ sectors/<정책분야>/<정책영역>.md  부문 설명서 (프로세스·법·코드·수요·체인·판단)
               ├─ sectors/_review_log.md         판정표·검토 기록
               ├─ families/<slug>/family.yaml·md  데이터 패밀리 (API 묶음의 관계 그래프)
               └─ dossiers/·laws/·recipes/        (Phase 3~4)
L3 지식 그래프   pds/knowledge/compile.py → data/processed/kg/*.parquet·jsonl → pds_kg_* 테이블
               (python -m pds kg-build / kg-load)                                       L1+L2에서 결정적으로 생성
L4 소비        전략 엔진(그래프 경로), 검색(벡터→청크→노드→그래프 확장), MCP 응답의 evidence
```

## 2. 그래프 모델 — 타입이 있는 속성 그래프

모든 것을 **노드·엣지·문서·청크** 네 테이블로 담는다. 새 개념은 새 `type` 값으로 추가하므로 대부분 스키마 변경이 필요 없다
(속성은 `props jsonb`). 자주 조회하는 속성이 생기면 그때 마이그레이션으로 컬럼을 올린다.

### 2.1 노드 ID 규약 `<type>:<key>`

| type | key 규칙 | 예 | 원천 |
| --- | --- | --- | --- |
| `dataset` | 포털 목록키 | `dataset:15126315` | L1 |
| `agency` | 제공기관코드 | `agency:1230000` | L1 |
| `field` | BRM 정책분야 | `field:공공행정` | L1 |
| `sector` | `정책분야/정책영역` | `sector:공공행정/정부조달` | L1 + sector_map |
| `subsector` | `정책분야/정책영역/slug` | `subsector:공공행정/국정운영/election` | subsectors.yaml |
| `gap` | `정책분야/정책영역/slug` | `gap:공공행정/국정운영/political-finance` | subsectors.yaml `gaps` |
| `decision` | 규칙 id | `decision:ftc-non-core` | exclusions·sector_map |
| `key` | 전역 키 id | `key:bizno` | keys/{id}.yaml |
| `family` | slug | `family:pps-procurement` | families/ |
| `fkey` | `family/key id` (패밀리 안 키) | `fkey:pps-procurement/bid_ntce_no` | family.yaml |
| `entity` | `family/entity id` | `entity:pps-procurement/bid_notice` | family.yaml |
| `recipe` | `family/recipe id` | `recipe:pps-procurement/trace-one-procurement` | family.yaml |
| `series` | `기관코드/제목-slug` | `series:1140100/국민권익위원회_민원빅데이터_분석정보_api` | 카탈로그 (제목 끝 연도만 다른 같은 기관 데이터) |
| `context` | 맥락 id | `context:early-childhood-care` | contexts/{id}.yaml (부처가 달라 부문은 다르지만 국민 입장에서 같은 맥락, 2026-09-29 추가) |
| `domain` | `정책분야/slug` | `domain:국토관리/계획·규제` | sectors/sector_tree.yaml (부문 위 법 체계 계층, 2026-09-29 추가) |
| `issuer` | 키 발급처 id | `issuer:open.law.go.kr` | key_issuers.yaml (계정 값 없이 .env 변수 이름만) |
| (예약) `law`, `dossier`, `operation`, `goal` | | | Phase 3~4 |

### 2.2 엣지 타입

| type | from → to | 의미 | props |
| --- | --- | --- | --- |
| `in_field` | sector → field | | |
| `in_sector` | dataset → sector | 현재 부문 | `brm`(원래 BRM), `rank_in_sector`, `prelim_score` |
| `in_subsector` | dataset → subsector | | `depth` |
| `subsector_of` | subsector → sector | | `depth`, `cycle`, `cross_cutting` |
| `gap_of` | gap → sector | 데이터가 없는 업무 영역 | `note` |
| `provided_by` | dataset → agency | | |
| `excluded_by` | dataset → decision | 프로젝트 제외 | |
| `remapped_by` | dataset → decision | BRM에서 다른 부문으로 이관 | `from_brm` |
| `has_key` | dataset → key | 연계 키 보유 (shape 판정·패밀리 별칭) | `source`(shape/family), `field`, `io` |
| `defines_key` | dataset → key | 키의 원장 데이터 | |
| `key_parent` | key → key | 묶음 키 계층 | |
| `key_related` | key → key | 접두·합성·매핑 관계 (keys/{id}.yaml `related_keys`, 2026-09-30) | `relation`, `note` |
| `same_as` | fkey → key | 패밀리 키 = 전역 키 | |
| `member_of` | dataset → family | | `role`, `short` |
| `provides` | dataset → entity | 패밀리 업무 객체 제공 | |
| `lifecycle` `lookup` `join` `reference` `hierarchy` `mirror` `derived` `aggregate` | 패밀리 엣지 그대로 | families/README.md §3.2 | 원본 엣지 속성 전부 |
| `uses` | recipe → dataset | 레시피 단계 | `step` |
| `part_of_series` | dataset → series | 연도별 분할 등록 | `year` |
| `continues` | dataset → dataset | 같은 시리즈의 다음 연도 (대체가 아니라 이어짐) | |
| `in_context` | subsector·sector → context | 같은 맥락 묶음의 멤버 | `dimension`(life_context·spatial_regulation·admin_area·shared_key·shared_source·same_concept), `role`, `key` |
| `context_key` | context → key | 이 맥락을 잇는 전역 키 | |
| `in_domain` | sector → domain | 부문이 속한 법 체계 층 | `law` |
| `domain_of` | domain → domain·field | 계층 (parent 없으면 field 바로 아래) | |
| `related_sector` | domain → sector | 다른 분야에 있지만 같은 법 층 (예: 개발사업 층 ↔ 농업·농촌) | |
| `key_issued_by` | dataset → issuer | 어디서 키를 받아야 하나 (access.key_issuer) | |

모든 엣지 공통 속성: `status`(documented·inferred·verified·refuted·decided·computed), `evidence`(목록), `source`(원본 파일 경로).
`computed`는 L1 규칙 계산 결과(예: shape 판정), `decided`는 사람 결정(sector_map·exclusions).

### 2.3 문서·청크 (설명 = 벡터화 대상)

- `doc`: 노드에 붙는 설명 단위. **md는 제목(##) 단위로 쪼개** 섹션마다 한 문서. yaml의 `reason`·`note`·`does`·`use_when`도 문서로.
  `doc_id = <node_id>#<section-slug>`, `kind` = sector_doc·family_doc·decision_reason·subsector_note·gap_note·key_note·dataset_desc.
- `chunk`: 벡터화 단위(문서를 ~800자 창으로 분할, 앞뒤 겹침 100자). `chunk_id = doc_id~seq`, `hash = sha1(text)`.
- **임베딩은 DB 밖**(회사 개발 DB에 pgvector 없음, 2026-09-28 결정): `data/embeddings/<model>/<hash>.npy` 또는 모델별 parquet
  (`hash, vector`). 청크 hash가 같으면 재사용 → 모델 교체·재계산이 싸다.

## 3. 저장소

| 위치 | 내용 |
| --- | --- |
| `data/processed/kg/nodes.parquet` `edges.parquet` `docs.parquet` `chunks.parquet` | 컴파일 결과 (분석·노트북용) |
| `data/processed/kg/*.jsonl` | 같은 내용, 다른 도구로 옮기기 쉬운 형식 (그래프 DB·LLM 컨텍스트) |
| Postgres `구름.pds_kg_node / pds_kg_edge / pds_kg_doc / pds_kg_chunk` | 조회·전략 엔진용 (`sql/002_knowledge_graph.sql`) |
| Postgres `구름.pds_kg_build` | 컴파일 이력 (시각, 원본 해시, 건수) |

## 4. 소비 방법 (나중에 "사용 방법 제시" 때)

**그래프 — 호출·연계 경로**: 두 데이터가 어떻게 이어지나
```sql
-- dataset A와 B가 공유하는 전역 키
select k.dst as key from pds_kg_edge k join pds_kg_edge m on k.dst = m.dst
where k.type = 'has_key' and m.type = 'has_key' and k.src = 'dataset:15157207' and m.src = 'dataset:15126469';
-- 패밀리 lookup 체인 따라가기 (재귀 CTE, 깊이 제한)
with recursive path(node, depth, trail) as (
  select 'dataset:15129462', 0, array['dataset:15129462']
  union all
  select e.dst, p.depth + 1, p.trail || e.dst from path p join pds_kg_edge e on e.src = p.node
  where e.type = 'lookup' and p.depth < 4 and not e.dst = any(p.trail))
select * from path;
```
**벡터 — 질문에서 근거로**: 질문 임베딩 → 가까운 청크 → `doc.node_id` → 그 노드에서 그래프 1~2홉 확장(`in_subsector`, `member_of`,
`has_key`, `lookup`) → 전략 응답의 `datasets`·`evidence` 후보. 즉 **벡터는 입구, 그래프는 설명**.

**전략 응답 evidence**: BUILD-PLAN §4.3의 `evidence` 링크는 `doc_id`를 그대로 쓴다(예: `sector:공공행정/정부조달#번호-체계`).

## 5. 마이그레이션 규약

- `sql/NNN_이름.sql`, 번호 순 적용. 적용 기록은 `pds_schema_migrations(version, name, checksum, applied_at)`.
- **적용된 파일은 고치지 않는다.** 바꿀 게 있으면 새 번호 파일(`ALTER …`). 체크섬이 달라지면 적용기가 경고하고 멈춘다.
- `001_catalog.sql`은 2026-09-28 기준선(그날까지의 ALTER를 흡수한 전체 스키마). 이후 변경은 002부터.
- 그래프 타입 추가는 **스키마 변경 없이** 이 문서 §2 표에 행을 추가하고 컴파일러에 생성 규칙을 넣는다. 자주 쓰는 속성을
  컬럼으로 올리거나 인덱스가 필요할 때만 마이그레이션.
- 지식 원본(yaml) 형식이 바뀌면 `version` 필드를 올리고 컴파일러가 두 버전을 모두 읽게 한 뒤, 파일을 옮기고 구버전 읽기를 뺀다.

## 6. 작업 흐름

```
사람과 대화 → knowledge/*.yaml·md 수정 (결정·설명)
          → python -m pds build            (L1 재계산: 규칙 반영된 부문·제외·점수)
          → python -m pds kg-build          (L3 컴파일 → data/processed/kg/)
          → python -m pds load-db && python -m pds kg-load   (Postgres 반영, 미적용 마이그레이션 자동 적용)
          → python -m pds report / report-md (사람용 리포트)
```
