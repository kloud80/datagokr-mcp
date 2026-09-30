# datagokr-mcp — 공공데이터 전략 시스템

**목표를 말하면, data.go.kr에서 어떤 데이터를 왜·어떻게 이어 써야 하는지와 바로 돌릴 코드를 돌려준다.**
검색기가 아니라 전략기다. 추천 근거는 전부 실제 호출·다운로드·법령 원문·검토 결정으로 확인된 사실(claim)이고,
데이터 사이의 조인은 미리 선언하고 실측한 것(Edge)만 쓴다. LLM은 데이터를 고르거나 조인을 만들지 않고 설명만 쓴다.

```
"성수동 상권 변화를 월 단위로 추적하고 싶어"
 → 소상공인 상가(상권)정보(15012005) + 업종 인허가(15155077) … 연속지적도(PNU) 허브로 결합
 → 성수동1가·2가 법정동코드, 월별 스냅샷 비교 방법, 주의점(검증 호출 조건·필수 파라미터), 실행 코드
```

## 무엇이 들어 있나

| 층 | 규모 (2026-09-30) | 어디 |
|---|---|---|
| **verified** — 키 발급·호출·다운로드·셀 통계까지 검증 | 265 데이터셋 | `knowledge/datasets/` |
| **candidate** — 선정했지만 검증 실패·보류 | 66 | 같은 곳 (`tier: candidate`) |
| **catalog** — 포털 전체 목록 (단서) | 96,110 | `python -m pds build`로 생성 |
| 근거 있는 사실 (claim: 실측·법령·검토 결정) | 1,700+ | 데이터셋 yaml의 `claims` |
| 조인 선언 (Edge) · 실측 매칭률 | 365 · 213 실측 (중앙값 100%) | `knowledge/edges.yaml`, `probe/joins/` |
| 코드 체계 매핑 (학교 99% · 병원 ykiho↔hpid 98% · 공동주택 · 정류장 …) | 7 | `knowledge/mappings/` |
| 코드표 (법정동 49,861 · 기관코드 418,063 · 지목 · 국가 · 통화 · 항구 · HS · NCS …) | 120 | `knowledge/codes/` |
| 조인 키 원장 · 맥락(부처를 가로지르는 묶음) · 법령 원문 · 레시피 초안 | 66 · 41 · 43 · 10 | `knowledge/keys/` `contexts/` `laws/` `recipes/` |

설계 문서: [`BUILD-PLAN.md`](BUILD-PLAN.md) (6단계 계획) · [`KNOWLEDGE-SPEC.md`](KNOWLEDGE-SPEC.md) (지식 엔티티·3층·출력 프로토콜) ·
[`knowledge/ARCHITECTURE.md`](knowledge/ARCHITECTURE.md) · 편집 규칙 [`docs/CONTRIBUTING-knowledge.md`](docs/CONTRIBUTING-knowledge.md) ·
현황 종합 [`reports/PDS_현황_종합.md`](reports/PDS_현황_종합.md)

## 빠르게 써 보기

```bash
python -m venv .venv && .venv/Scripts/activate        # macOS·Linux: source .venv/bin/activate
pip install -e .
cp .env.example .env                                   # CLAUDE_API_KEY만 있어도 채팅이 된다
python -m pds download && python -m pds build          # 포털 벌크 메타 → 카탈로그 9.6만 (catalog 층·단서 검색용)
python -m pds.dossier.render                           # 설명서(docs/dossiers/) — 선택
python -m pds serve                                    # http://127.0.0.1:8765 웹 채팅
```

### 서비스 API

| 메서드 | 경로 | 내용 |
|---|---|---|
| POST | `/api/chat` | `{messages:[{role,content}]}` → 답 + 전략(`plans`) + 도구 기록. 모델 `claude-opus-5-5` |
| POST | `/api/plan` | `{goal, use_llm}` → 전략 응답 ([KNOWLEDGE-SPEC §4](KNOWLEDGE-SPEC.md) 스키마, 서버가 검증 규칙을 강제) |
| GET | `/api/search?q=&tier=verified\|candidate\|catalog` | 3층 검색 |
| GET | `/api/datasets/{id}` · `/api/datasets/{id}/dossier` | 상세 · 설명서 markdown |
| GET | `/api/codes` · `/api/codes/{id}?q=` | 코드표 목록 · 코드 조회 |
| GET | `/api/stats` | 지식 체계 규모 |

전략 응답의 규칙: `datasets[].evidence`는 근거 있는 claim id만 · `joins[].edge`는 `edges.yaml`에 선언된 것만 ·
`candidates`는 조인에 참여하지 않음 · `unverified_leads`(catalog)는 최대 5개이고 "직접 확인" 단서일 뿐.

### MCP (Claude Desktop 등)

```json
{
  "mcpServers": {
    "datagokr": {
      "command": "C:/path/to/datagokr-mcp/.venv/Scripts/python.exe",
      "args": ["-m", "pds", "mcp"],
      "cwd": "C:/path/to/datagokr-mcp"
    }
  }
}
```

도구: `plan_public_data_strategy` · `search_datasets` · `get_dataset` · `list_code_lists` · `lookup_code` · 리소스 `dataset://{id}`.
`python -m pds mcp --http`면 streamable-http(:8766).

## 지식을 쌓는 파이프라인 (Phase 1~3)

```
python -m pds download / build            벌크 메타 → 부문·세부 부문·제외·점수 (knowledge/sectors/*.yaml 규칙)
python -m pds probe-specs|probe-apply|probe-run <round>   명세 수집 → 포털 활용신청(Playwright) → 호출·셀 통계
python -m pds.probe.fullpull <plan>       매핑·코드표용 전수 원장 수집 (data/master/)
python -m pds.mapping.build_<name>        코드 체계 매핑 (학교·병원·공동주택·복지시설·정류장)
python -m pds.codes.needs / build         코드표 필요 목록 → 확보
python -m pds.laws.fetch                  법제처 원문
python -m pds gen-dataset                 Dataset yaml + 자동 claim
python -m pds.edges.auto && python -m pds.probe.join      Edge 후보 → 실측 매칭률
python -m pds.probe.observe               갱신 관찰 스냅샷 (매주 — 주기 실측)
python -m pds.dossier.drafts              요약·한계 LLM 초안 (Batches API, review.summary=draft)
python -m pds validate [--strict]         스키마·상호 참조·승격 조건
python -m pytest -q
```

## 키와 개인정보

- 저장소에는 **키·계정·세션을 넣지 않는다**. `.env`, `secrets/`, `data/raw|processed|master/`, `probe/data/`는 `.gitignore`.
- 키는 사용자 것이다: 포털 데이터는 각자 data.go.kr 활용신청, 외부 사이트(브이월드·나이스·서울·법제처 등)는 해당 사이트에서 발급.
  발급 절차는 [`knowledge/key_issuers.yaml`](knowledge/key_issuers.yaml).
- 포함된 파생 데이터(코드표·매핑·실측 통계)는 공공데이터포털 개방 데이터에서 만든 것이며 원 데이터의 이용허락 조건을 따른다.

## 상태와 한계

- 갱신 주기(cadence) 실측은 2026-09-30 기준선만 있다 — 7일 뒤 `observe` 재실행부터 근거가 생긴다.
- 요약·한계 문장은 LLM 초안(`review.summary: draft`)이다. 레시피 10개도 초안 — 골든셋 정답은 사람이 확정한다.
- 검색은 글자 2-gram BM25. KNOWLEDGE-SPEC의 임베딩(bge-m3)은 `pds/service/index.py`의 `search_*` 뒤에 끼우면 된다.
- 표본 겹침만으로 판정한 조인은 "실측 보류"로 두었다(전수 원장이 없는 키).

라이선스 MIT.
