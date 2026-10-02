"""LLM 재순위 — 검색 풀(검증 데이터 30개 안팎)을 질문과의 관련도 0~3으로 매긴다.

검색(BM25+의미)은 넓게 모으고, 여기서 "질문에 정말 쓸 데이터인가"를 판단해 잡음(글자만 겹친 데이터)을 거른다.
LLM은 데이터를 지어내지 않는다 — 입력으로 준 id에 점수만 매기고, 모르는 id는 버린다.
모델 PDS_RERANK_MODEL (기본 claude-haiku-4-5 — 판단만 하므로 싼 모델로 충분, 질문당 1회).
실패하면 None — 플래너는 검색 점수 순서 그대로 간다.
"""
from __future__ import annotations

import json
import os

MODEL = os.environ.get("PDS_RERANK_MODEL") or "claude-haiku-4-5"

SYSTEM = """너는 공공데이터 선별 심사자다. 사용자 질문과 후보 데이터 목록을 받아, 각 데이터가 질문에 답하는 데 얼마나 쓸모 있는지 0~3점으로 매긴다.
3 = 질문의 핵심 대상을 직접 담음 · 2 = 함께 쓰면 분명히 도움 (보조 지표·조인 대상) · 1 = 주제만 스침 · 0 = 무관 (글자만 겹침)
질문의 의도(무엇을 알고 싶은가)를 기준으로 판단하고, 제목의 단어가 겹친다는 이유만으로 점수를 주지 않는다.
질문이 여러 요소를 묻는다면(예: "병상 수와 진료비", "출발지와 도착지 교통량") 요소를 하나씩 나누고, 어느 한 요소라도 직접 담는 데이터는 3점이다.
질문이 직접 말하지 않아도 그 의도를 더 빨리·정확히 알려 주는 대리 지표(예: 지역 경기 → 카드 매출·고용 증감, 건물 노후도 → 사용승인일)는 2~3점이다.
반드시 목록에 있는 id만 쓴다."""

SCHEMA = {
    "type": "object",
    "properties": {"scores": {"type": "array", "items": {
        "type": "object", "properties": {"id": {"type": "string"}, "score": {"type": "integer"}},
        "required": ["id", "score"], "additionalProperties": False}}},
    "required": ["scores"], "additionalProperties": False,
}


def _line(d: dict) -> str:
    cl = d.get("classification") or {}
    s = (d.get("summary_user") or cl.get("why") or "").replace("\n", " ")[:140]
    return f"{d['id']} | {d['title']} | {s}"


def rerank(goal: str, items: list[dict]) -> dict[str, int] | None:
    if not items:
        return {}
    try:
        from pds.service.llm import client
        msg = "질문: " + goal + "\n\n후보 데이터 (id | 제목 | 설명):\n" + "\n".join(_line(d) for d in items)
        resp = client().messages.create(
            model=MODEL, max_tokens=2000, system=SYSTEM, messages=[{"role": "user", "content": msg}],
            output_config={"format": {"type": "json_schema", "schema": SCHEMA}})
        text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
        known = {d["id"] for d in items}
        return {x["id"]: max(0, min(3, int(x["score"]))) for x in json.loads(text)["scores"] if x["id"] in known}
    except Exception as e:  # noqa: BLE001 — 재순위가 실패해도 전략은 나와야 한다
        print(f"[rerank] 실패: {type(e).__name__}: {str(e)[:160]}", flush=True)
        return None
