# 지식 파일 편집 규칙 (KNOWLEDGE-SPEC §9-8)

`knowledge/` 아래 yaml이 이 시스템의 원본이다. DB·설명서·임베딩은 여기서 다시 만든다. 고친 뒤에는 반드시:

```
python -m pds validate          # 스키마·상호 참조 (오류 0이어야 머지)
python -m pds validate --strict # 승격 조건까지 (verified 데이터셋: 근거 있는 claim ≥ 3 · Edge ≥ 1)
python -m pytest -q
```

## 1. 어디를 고치나

| 무엇 | 파일 | 누가 쓰나 |
|---|---|---|
| 데이터셋 | `knowledge/datasets/{분야}/{id}.yaml` | 기계 필드는 `python -m pds gen-dataset`가 다시 쓴다. 사람은 `summary_user · limits · synonyms · sla · facets · edges_hint · family · status · cycle`와 번호 50 이상 claim만 |
| 조인 키 | `knowledge/keys/{id}.yaml` | 사람 |
| 매핑표 | `knowledge/mappings/{a}__{b}.yaml` + `.parquet` | `pds/mapping/` 스크립트 (손으로 parquet 고치지 않음) |
| 조인·lookup 선언 | `knowledge/edges.yaml` | 자동 후보 → 사람 확정 (`source: admin`) |
| 맥락 | `knowledge/contexts/{id}.yaml` | 사람 |
| 레시피(골든셋 정답) | `knowledge/recipes/{slug}.yaml` | 사람 (구름) |
| 공백 | `knowledge/gaps.yaml` | 사람 |

## 2. claim 규칙

- **근거 없는 값은 쓰지 않는다.** 사실은 claim으로 쓰고, `evidence`는 1개 이상.
- 근거 유형: `measured`(프로브) · `law`(법제처 원문) · `admin_review`(검토 결정) · `portal_meta`(포털 등록값) · `inferred`(LLM 초안) · `user`(피드백).
  프로토콜에 나가는 claim은 `measured`·`law`·`admin_review` 중 하나가 있어야 한다. `inferred`만 있는 claim은 설명서에 "(미확인)"으로 보인다.
- **번호**: `c-{데이터셋 id}-{NN}`. 01~49는 생성기 슬롯(01 access · 02 cadence · 03 key · 04 coverage · 05 legal_basis · 06~09 admin_note · 10~19 pitfall),
  **사람이 쓰는 claim은 50부터**. 한번 인용된 번호는 바꾸지 않는다(레시피·전략 응답이 id로 인용).
- `measured` claim은 `valid_until`(기본 관측 + 6개월)을 둔다. 지나면 재확인 큐.
- 틀린 claim은 지우지 말고 `rank: deprecated` — 전략 응답의 `not_recommended` 사유가 된다.

## 3. Edge 규칙

- LLM은 Edge를 만들지 않는다. 자동 후보(`source: auto`)는 사람이 확인해 `source: admin`으로 올린다.
- `joinable`·`lookup`은 `on.left/right`와 `relationship`(카디널리티)이 필수. 코드 체계가 다르면 `via_mapping`.
- `verified.by: measured`는 `pds/probe/join.py` 실측 매칭률이 있을 때만.
- candidate 데이터셋은 조인에 참여할 수 없다.

## 4. 승인

부문·대상·Edge 확정·레시피 정답은 구름이 승인한다(BUILD-PLAN §8-5). 결정을 내린 대화는 `knowledge/sectors/_review_log.md`에 날짜·결정자와 함께 남긴다 —
생성기가 이 기록을 `admin_review` 근거로 인용한다.
