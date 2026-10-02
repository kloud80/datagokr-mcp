"""LLM 계층 — 전략 설명(explain)과 채팅 에이전트(chat). 모델 PDS_CHAT_MODEL(기본 claude-opus-5-5), 키는 .env CLAUDE_API_KEY(또는 ANTHROPIC_API_KEY).

원칙 (KNOWLEDGE-SPEC §6-7, §10): LLM은 데이터·조인을 고르지 않는다 — 플래너가 고른 것에 "왜"·요약 문장만 붙이고, 인용은 입력으로 준 claim id만.
채팅은 도구(검색·상세·전략·코드표)를 서버가 실행하고, 답은 도구 결과에 근거한다.
안전 분류기 거절에 대비해 서버측 폴백(fallbacks: "default", beta server-side-fallback-2026-07-01)을 켠다.
"""
from __future__ import annotations

import json
import os
import time
from typing import Callable

import anthropic

from pds import config
from pds.schema import GROUNDED
from pds.service import index as sindex

MODEL = os.environ.get("PDS_CHAT_MODEL") or "claude-opus-5-5"  # 비용에 맞춰 .env로 바꾼다 (예: claude-sonnet-5-5, claude-haiku-4-5)
FALLBACK = {"betas": ["server-side-fallback-2026-07-01"], "extra_body": {"fallbacks": "default"}}


def client() -> anthropic.Anthropic:
    return anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY) if config.ANTHROPIC_API_KEY else anthropic.Anthropic()


def _text(resp) -> str:
    return "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")


# ─────────────────────────── explain — 전략 응답의 summary·why
EXPLAIN_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "datasets": {"type": "array", "items": {"type": "object", "properties": {
            "id": {"type": "string"}, "why": {"type": "string"}, "evidence": {"type": "array", "items": {"type": "string"}}},
            "required": ["id", "why", "evidence"], "additionalProperties": False}},
    },
    "required": ["summary", "datasets"],
    "additionalProperties": False,
}
EXPLAIN_SYSTEM = """당신은 한국 공공데이터 전략 시스템의 설명 작성자입니다. 시스템이 이미 고른 데이터·조인·파이프라인에 설명만 붙입니다.
- summary: 한국어 2~3문장. 목표에 이 조합이 어떻게 답하는지, 한계(조인 경로 없음·실측 보류 등)가 있으면 한 구절.
- datasets[].why: 데이터마다 한국어 1~2문장. 목표에서 그 데이터가 맡는 역할(primary/join/lookup/context)과 이유.
- datasets[].evidence: 그 문장의 근거로 입력에 있는 claim id만. 입력에 없는 id·사실을 만들지 않습니다.
- 데이터를 추가하거나 빼지 않습니다. 과장 없이 짧게."""


def explain(plan: dict) -> dict:
    ix = sindex.get()
    lines = [f"목표: {plan['goal']}", f"맥락: {plan.get('context') or '없음'}", "", "## 데이터"]
    allowed = {}
    for d in plan["datasets"]:
        cl = ix.grounded_claims(d["id"])
        allowed[d["id"]] = {c["id"] for c in cl}
        lines.append(f"### [{d['role']}] {d['id']} {d['title']}")
        summ = (ix.datasets[d["id"]].get("summary_user") or "")[:400]
        if summ:
            lines.append(f"요약: {summ}")
        lines += [f"- [{c['id']}] ({c['kind']}) {c['value'][:260]}" for c in cl[:10]]
    lines.append("\n## 조인")
    lines += [f"- {j['edge']}: {j['left']} ⋈ {j['right']} on {j['on']}" + (f" via {j['hub']}" if j.get("hub") else "")
              + (f" 실측 {j['match_rate']}" if j.get("match_rate") is not None else " 실측 보류") for j in plan["joins"]] or ["- 없음"]
    if plan["gaps"]:
        lines.append("\n## 공백\n" + "\n".join(f"- {g}" for g in plan["gaps"]))
    r = client().beta.messages.create(model=MODEL, max_tokens=4000, system=EXPLAIN_SYSTEM, **FALLBACK,
                                      output_config={"effort": "low", "format": {"type": "json_schema", "schema": EXPLAIN_SCHEMA}},
                                      messages=[{"role": "user", "content": "\n".join(lines)}])
    if r.stop_reason == "refusal":
        return plan
    out = json.loads(_text(r))
    plan["summary"] = out["summary"].strip()
    by = {x["id"]: x for x in out["datasets"]}
    for d in plan["datasets"]:
        x = by.get(d["id"])
        if not x:
            continue
        ev = [c for c in x["evidence"] if c in allowed[d["id"]]]  # 목록 밖 인용은 버린다
        d["why"] = x["why"].strip()
        if ev:
            d["evidence"] = ev
    plan["explained_by"] = MODEL
    return plan


# ─────────────────────────── chat — 도구를 쓰는 대화 에이전트
TOOLS = [
    {"name": "plan_strategy", "description": "사용자 목표(자연어)에 맞는 공공데이터 조합·조인·파이프라인·실행 코드를 만든다. 목표가 나오면 먼저 이것을 부른다.",
     "input_schema": {"type": "object", "properties": {"goal": {"type": "string", "description": "사용자 목표 문장"}},
                      "required": ["goal"], "additionalProperties": False}},
    {"name": "exclude_dataset", "description": "직전 plan_strategy 결과에서 목표에 맞지 않는 데이터를 뺀다(지역·대상·시점 불일치 등). "
                                              "전략 패널·코드가 함께 갱신된다. 답에서만 빼고 전략에 남겨 두지 않는다.",
     "input_schema": {"type": "object", "properties": {"id": {"type": "string"}, "reason": {"type": "string", "description": "사용자에게 보일 한 줄 사유"}},
                      "required": ["id", "reason"], "additionalProperties": False}},
    {"name": "search_datasets", "description": "지식 체계에서 데이터셋을 검색한다. tier: verified(검증) · candidate(선정·미검증) · catalog(포털 전체 9.6만, 단서).",
     "input_schema": {"type": "object", "properties": {"query": {"type": "string"},
                                                       "tier": {"type": "string", "enum": ["verified", "candidate", "catalog"]}},
                      "required": ["query", "tier"], "additionalProperties": False}},
    {"name": "get_dataset", "description": "데이터셋 한 건의 상세 — 호출 방법·필드·조인 키·근거 claim·연결된 Edge.",
     "input_schema": {"type": "object", "properties": {"id": {"type": "string"}}, "required": ["id"], "additionalProperties": False}},
    {"name": "find_code_list", "description": "코드표 목록을 이름·필드명으로 찾는다 (예: 지목, 용도지역, 법정동, 기관코드, 통화, HS).",
     "input_schema": {"type": "object", "properties": {"keyword": {"type": "string"}}, "required": ["keyword"], "additionalProperties": False}},
    {"name": "lookup_code", "description": "코드표에서 코드값 또는 이름으로 찾는다 (예: code_list=bjd_cd, q=성수동).",
     "input_schema": {"type": "object", "properties": {"code_list": {"type": "string"}, "q": {"type": "string"}},
                      "required": ["code_list", "q"], "additionalProperties": False}},
]
CHAT_SYSTEM = """당신은 data.go.kr 공공데이터 전략 도우미입니다. 사용자의 목표를 듣고, 어떤 공공데이터를 어떻게 이어 쓰면 되는지 안내합니다.
지식 체계는 세 층입니다: verified(실제 호출·다운로드로 검증) · candidate(선정됐으나 미검증) · catalog(포털 전체 목록, 단서일 뿐).
화면 오른쪽 패널에 전략(데이터 카드·조인 지도·단계·코드)이 그대로 나옵니다. 답은 그 전략을 읽어 주는 설명입니다.

규칙
- 목표가 나오면 plan_strategy를 먼저 부르고, 그 결과만 바탕으로 답합니다. 데이터·조인을 스스로 지어내지 않습니다.
- 전략과 다른 말을 하지 않습니다. 고른 데이터가 목표에 맞지 않으면(지역·대상·시점 불일치) 답에서만 빼지 말고
  exclude_dataset으로 전략에서 빼고 사유를 한 줄로 말합니다. not_recommended에 있는 데이터는 그 사유를 그대로 전합니다.
- 데이터는 반드시 [[목록키]] 형식으로 언급합니다 (예: 일반음식점 인허가 [[15154916]]). 화면이 카드 링크로 바꿉니다. 괄호 속 숫자로 쓰지 않습니다.
- candidate·catalog는 "미검증 단서"라고 분명히 말합니다.
- 조인은 plan_strategy가 준 선언된 Edge만 말합니다. 경로가 없으면 없다고 말합니다.
- 코드값 뜻이나 지역 코드가 필요하면 find_code_list·lookup_code로 확인합니다.
- 답은 한국어로 짧게 — 패널에 세부가 다 있으므로 핵심만 8~14줄. 순서: ①핵심 데이터와 역할 ②어떻게 잇나 ③주의점 ④다음에 할 일.
- 키(인증키)를 요구받으면: 포털 데이터는 data.go.kr 활용신청, 외부 사이트는 해당 사이트 발급이라고 안내합니다. 키 값을 묻거나 다루지 않습니다."""

TOOL_LABEL = {"plan_strategy": "전략 계산", "exclude_dataset": "전략에서 제외", "search_datasets": "데이터 검색",
              "get_dataset": "데이터 상세 조회", "find_code_list": "코드표 찾기", "lookup_code": "코드값 조회"}
STAGE_LABEL = {"context": "맥락 찾기", "candidates": "데이터 후보", "joins": "조인 경로"}

Emit = Callable[[dict], None]


def _slim(p: dict) -> str:
    ix = sindex.get()
    slim = {k: p[k] for k in ("goal", "context", "summary", "confidence", "gaps")}
    slim["datasets"] = [{k: d[k] for k in ("id", "role", "title", "agency", "why")} | {"access": d["access"], "rows": d.get("rows")}
                        for d in p["datasets"]]
    slim["joins"] = [{k: j[k] for k in ("edge", "left", "right", "on", "relationship", "via_mapping", "match_rate", "hub")} for j in p["joins"]]
    slim["not_recommended"] = [{k: x.get(k) for k in ("id", "title", "reason")} for x in p["not_recommended"]]
    slim["candidates"] = [{k: c[k] for k in ("id", "title", "status")} for c in p["candidates"]]
    slim["unverified_leads"] = [{k: x[k] for k in ("id", "title", "agency")} for x in p["unverified_leads"]]
    slim["claims"] = {d["id"]: [c["value"][:160] for c in ix.grounded_claims(d["id"])][:8] for d in p["datasets"]}
    return json.dumps(slim, ensure_ascii=False, default=str)


def run_tool(name: str, args: dict, plans: list, emit: Emit | None = None, t0: float = 0.0) -> str:
    ix = sindex.get()
    emit = emit or (lambda _e: None)
    if name == "plan_strategy":
        from pds.strategy.plan import plan

        def progress(stage: str, status: str, detail: str) -> None:
            emit({"type": "step", "id": stage, "label": STAGE_LABEL.get(stage, stage), "status": status, "detail": detail,
                  "t": round(time.time() - t0, 1)})
        p = plan(args["goal"], use_llm=False, progress=progress)  # 설명은 채팅 답에서 — 두 번 부르지 않는다
        p["version"] = len(plans) + 1
        plans.append(p)
        emit({"type": "plan", "plan": p})
        return _slim(p)
    if name == "exclude_dataset":
        from pds.strategy.plan import exclude
        if not plans:
            return json.dumps({"error": "먼저 plan_strategy를 불러야 한다"})
        p = exclude(plans[-1], args["id"], args["reason"])
        plans[-1] = p
        emit({"type": "plan", "plan": p})
        return json.dumps({"ok": True, "remaining": [(d["id"], d["role"]) for d in p["datasets"]]}, ensure_ascii=False)
    if name == "search_datasets":
        if args["tier"] == "catalog":
            res = [{"id": r["id"], "title": r["title"], "agency": r["agency_name"], "tier": "catalog", "note": "미검증 단서"}
                   for r, _ in ix.search_catalog(args["query"], 8)]
        else:
            res = [{"id": d["id"], "title": d["title"], "tier": d["tier"], "sector": d["sector"], "summary": (d.get("summary_user") or "")[:200]}
                   for d, _ in ix.search_datasets(args["query"], 8, tiers=(args["tier"],))]
        return json.dumps(res, ensure_ascii=False)
    if name == "get_dataset":
        d = ix.datasets.get(args["id"])
        if not d:
            r = ix.catalog[ix.catalog["id"] == args["id"]] if ix.catalog is not None else None
            if r is not None and len(r):
                from pds.strategy.plan import jsonable
                return json.dumps(jsonable({"tier": "catalog", **r.iloc[0].to_dict(), "note": "지식 체계 밖(미검증) — 포털 메타만"}),
                                  ensure_ascii=False, default=str)
            return json.dumps({"error": "없는 id"})
        edges = [{"id": e["id"], "rel": e["rel"], "other": e["dst"] if e["src"] == d["id"] else e["src"], "on": e.get("on"),
                  "match_rate": (e.get("verified") or {}).get("match_rate")} for e in ix.edges if d["id"] in (e["src"], e["dst"])][:12]
        out = {k: d.get(k) for k in ("id", "tier", "title", "sector", "agency", "kind", "channel", "portal_url", "summary_user", "limits")}
        out["services"] = [{k: s.get(k) for k in ("op", "endpoint", "params", "approval")} for s in (d.get("services") or [])[:4]]
        out["fields"] = [{k: f.get(k) for k in ("name", "title", "semantic_type", "code_list")} for f in (d.get("schema") or {}).get("fields", [])[:40]]
        out["claims"] = [{"id": c["id"], "kind": c["kind"], "value": c["value"][:240],
                          "grounded": any(e["type"] in GROUNDED for e in c["evidence"])} for c in d.get("claims") or []]
        out["edges"] = edges
        return json.dumps(out, ensure_ascii=False, default=str)
    if name == "find_code_list":
        kw = args["keyword"].lower()
        res = [{"id": c["id"], "name": c["name"], "completeness": c["completeness"], "rows": c["rows"], "aliases": c.get("aliases", [])[:3]}
               for c in ix.codes.values() if kw in c["name"].lower() or kw in c["id"] or any(kw in str(a).lower() for a in c.get("aliases", []))]
        return json.dumps(res[:10], ensure_ascii=False)
    if name == "lookup_code":
        return json.dumps(ix.code_values(args["code_list"], args["q"], 20), ensure_ascii=False, default=str)
    return json.dumps({"error": f"모르는 도구 {name}"})


def _create(c, msgs: list) -> object:
    kw = {"output_config": {"effort": "low"}} if "haiku" not in MODEL else {}  # Haiku는 effort 미지원
    return c.beta.messages.create(model=MODEL, max_tokens=8000, system=CHAT_SYSTEM, tools=TOOLS, **FALLBACK, **kw, messages=msgs)


def chat(history: list[dict], max_turns: int = 6, emit: Emit | None = None) -> dict:
    """history: [{role: user|assistant, content: str}] (웹 클라이언트가 들고 있는 텍스트 대화). 반환: 답·전략·도구 기록·사용량.
    emit: 진행 이벤트 콜백 — {type: step|plan, …} (SSE로 화면에 단계·전략을 먼저 보낸다)."""
    msgs = [{"role": m["role"], "content": m["content"]} for m in history if m.get("content")]
    plans, trace = [], []
    usage = {"model": MODEL, "calls": 0, "input": 0, "output": 0, "cache_read": 0, "cache_write": 0}
    emit = emit or (lambda _e: None)
    t0 = time.time()
    c = client()
    for turn in range(max_turns):
        sid = "understand" if turn == 0 else f"write{turn}"
        label = "질문 이해" if turn == 0 else "설명 작성"
        emit({"type": "step", "id": sid, "label": label, "status": "running", "detail": "", "t": round(time.time() - t0, 1)})
        r = _create(c, msgs)
        u = r.usage  # 비용 추적 — 응답마다 누적
        usage["calls"] += 1
        usage["input"] += u.input_tokens or 0
        usage["output"] += u.output_tokens or 0
        usage["cache_read"] += getattr(u, "cache_read_input_tokens", 0) or 0
        usage["cache_write"] += getattr(u, "cache_creation_input_tokens", 0) or 0
        if r.stop_reason == "refusal":
            emit({"type": "step", "id": sid, "label": label, "status": "failed", "detail": "처리할 수 없는 요청", "t": round(time.time() - t0, 1)})
            return {"reply": "이 요청은 처리할 수 없습니다.", "plans": plans, "trace": trace, "stop": "refusal", "usage": usage}
        calls = [b for b in r.content if getattr(b, "type", "") == "tool_use"]
        detail = "도구 " + ", ".join(TOOL_LABEL.get(b.name, b.name) for b in calls) if calls else ""
        if turn and calls:  # 설명 도중 도구를 더 부르면 검토 단계로 표시
            label = "검토 · 수정"
        emit({"type": "step", "id": sid, "label": label, "status": "done", "detail": detail, "t": round(time.time() - t0, 1)})
        if not calls:
            return {"reply": _text(r), "plans": plans, "trace": trace, "stop": r.stop_reason, "usage": usage}
        msgs.append({"role": "assistant", "content": r.content})
        results = []
        for b in calls:
            try:
                out = run_tool(b.name, dict(b.input), plans, emit, t0)
                results.append({"type": "tool_result", "tool_use_id": b.id, "content": out})
            except Exception as e:  # noqa: BLE001 — 도구 오류는 is_error로 돌려준다
                out = f"{type(e).__name__}: {str(e)[:300]}"
                results.append({"type": "tool_result", "tool_use_id": b.id, "content": out, "is_error": True})
            trace.append({"tool": b.name, "input": dict(b.input), "chars": len(out)})
        msgs.append({"role": "user", "content": results})
    return {"reply": "도구 호출이 너무 길어져 멈췄습니다. 질문을 좁혀 주세요.", "plans": plans, "trace": trace, "stop": "max_turns", "usage": usage}
