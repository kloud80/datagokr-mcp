"""LLM 초안 — summary_user·limits·synonyms (KNOWLEDGE-SPEC §7-7). 구름 승인 전까지 review.summary = draft.

입력은 근거 있는 claim(id 포함)·포털 설명·필드·코드표뿐이고, 출력은 JSON 스키마로 고정한다. 입력에 없는 사실은 쓰지 않게 지시하고,
인용한 claim id가 실제로 없으면 버린다(원칙 §10-2). 승인된(approved) 초안은 다시 돌려도 덮어쓰지 않는다.
실행: Message Batches API (비동기, 50% 비용) — submit → poll → apply. 배치 id는 probe/llm/에 남는다.
모델: claude-opus-5-5 (기본), effort medium.
"""
from __future__ import annotations

import datetime as dt
import json
import time
from functools import lru_cache

import anthropic
from anthropic.types.message_create_params import MessageCreateParamsNonStreaming
from anthropic.types.messages.batch_create_params import Request

from pds import config
from pds.schema import Dataset, GROUNDED
from pds.schema import store

MODEL = "claude-opus-5-5"
LOG = config.ROOT / "probe" / "llm"
PROMPT = config.ROOT / "prompts" / "dataset_summary.md"

SCHEMA = {
    "type": "object",
    "properties": {
        "summary_user": {"type": "string", "description": "한국어 3문장: ①무엇을 담은 데이터인가 ②누가 어떤 질문에 쓰나 ③무엇과 이어 쓰나(키·연계)"},
        "limits": {"type": "string", "description": "한국어 1~3문장: 이 데이터로 못 하는 것·주의점 (실측 근거가 있는 것만)"},
        "synonyms": {"type": "array", "items": {"type": "string"}, "description": "사람이 검색할 때 쓸 말 3~8개"},
        "cited_claims": {"type": "array", "items": {"type": "string"}, "description": "근거로 삼은 claim id"},
    },
    "required": ["summary_user", "limits", "synonyms", "cited_claims"],
    "additionalProperties": False,
}


def _client() -> anthropic.Anthropic:
    return anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY) if config.ANTHROPIC_API_KEY else anthropic.Anthropic()


def _system() -> list[dict]:
    return [{"type": "text", "text": PROMPT.read_text(encoding="utf-8"), "cache_control": {"type": "ephemeral"}}]


@lru_cache
def _code_names() -> dict:
    return {c["id"]: c["name"] for c, _ in store.iter_raw("code")}


def _input(d: dict) -> str:
    codes = _code_names()
    claims = [c for c in d.get("claims") or [] if any(e["type"] in GROUNDED for e in c["evidence"])]
    fields = (d.get("schema") or {}).get("fields") or []
    lines = [f"# {d['title']}", f"- 기관: {d['agency']['name']} · 부문: {d['sector']} · 형태: {d['kind']} · 경로: {d['channel']}",
             f"- 세부 부문: {(d.get('classification') or {}).get('subsector_name', '')}"]
    if d.get("description_portal"):
        lines.append(f"- 포털 설명: {d['description_portal'][:900]}")
    lines.append("\n## 근거 있는 claim")
    lines += [f"- [{c['id']}] ({c['kind']}) {c['value'][:400]}" for c in claims]
    lines.append("\n## 필드 (이름 · 명세상 의미 · 코드표)")
    for f in fields[:45]:
        cl = f" · 코드표 {codes.get(f['code_list'], f['code_list'])}" if f.get("code_list") else ""
        st = f" · 키 {f['semantic_type']}" if f.get("semantic_type") else ""
        lines.append(f"- {f['name']} · {f.get('title') or ''}{st}{cl}")
    return "\n".join(lines)


def targets(force: bool = False) -> list[dict]:
    out = []
    for d, _ in store.iter_raw("dataset"):
        if d.get("tier") != "verified":
            continue
        rv = (d.get("review") or {}).get("summary")
        if rv == "approved" or (rv == "draft" and not force):
            continue
        out.append(d)
    return out


def submit(force: bool = False, limit: int | None = None) -> dict:
    ds = targets(force)[:limit]
    reqs = [Request(custom_id=d["id"].replace(":", "_"), params=MessageCreateParamsNonStreaming(
        model=MODEL, max_tokens=4000, system=_system(), output_config={"effort": "medium", "format": {"type": "json_schema", "schema": SCHEMA}},
        messages=[{"role": "user", "content": _input(d)}])) for d in ds]
    if not reqs:
        return {"submitted": 0}
    batch = _client().messages.batches.create(requests=reqs)
    LOG.mkdir(parents=True, exist_ok=True)
    rec = {"batch_id": batch.id, "model": MODEL, "n": len(reqs), "at": dt.datetime.now().isoformat(timespec="seconds"),
           "ids": [d["id"] for d in ds]}
    (LOG / f"summary_batch_{batch.id}.json").write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
    return rec


def wait(batch_id: str, every: int = 30) -> dict:
    c = _client()
    while True:
        b = c.messages.batches.retrieve(batch_id)
        if b.processing_status == "ended":
            return {"succeeded": b.request_counts.succeeded, "errored": b.request_counts.errored, "expired": b.request_counts.expired}
        time.sleep(every)


def apply(batch_id: str) -> dict:
    c = _client()
    ok, bad, usage = 0, {}, {"input": 0, "output": 0, "cache_read": 0}
    by_id = {d["id"].replace(":", "_"): (d, p) for d, p in store.iter_raw("dataset")}
    for r in c.messages.batches.results(batch_id):
        if r.result.type != "succeeded":
            bad[r.custom_id] = r.result.type
            continue
        msg = r.result.message
        usage["input"] += msg.usage.input_tokens
        usage["output"] += msg.usage.output_tokens
        usage["cache_read"] += msg.usage.cache_read_input_tokens or 0
        if msg.stop_reason == "refusal":
            bad[r.custom_id] = "refusal"
            continue
        text = next((b.text for b in msg.content if b.type == "text"), "")
        try:
            out = json.loads(text)
        except json.JSONDecodeError:
            bad[r.custom_id] = "json"
            continue
        d, path = by_id[r.custom_id]
        claim_ids = {x["id"] for x in d.get("claims") or []}
        cited = [x for x in out.get("cited_claims") or [] if x in claim_ids]
        d["summary_user"] = out["summary_user"].strip()
        d["limits"] = out["limits"].strip()
        d["synonyms"] = list(dict.fromkeys((d.get("synonyms") or []) + [s.strip() for s in out.get("synonyms") or [] if s.strip()]))[:15]
        d["review"] = {"summary": "draft", "by": f"llm:{MODEL}", "at": dt.date.today().isoformat(), "batch": batch_id,
                       "cited_claims": cited, "dropped_citations": len(out.get("cited_claims") or []) - len(cited)}
        Dataset.model_validate(d)
        store.dump(d, path, header=f"Dataset {d['id']} — KNOWLEDGE-SPEC §3.1. summary_user·limits는 LLM 초안(review.summary=draft) — 승인 전")
        ok += 1
    return {"applied": ok, "failed": bad, "usage": usage}


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "apply":
        print(apply(sys.argv[2]))
    else:
        rec = submit(limit=int(sys.argv[1]) if len(sys.argv) > 1 else None)
        print(rec.get("batch_id"), rec.get("n"))
        if rec.get("batch_id"):
            print(wait(rec["batch_id"]))
            print(apply(rec["batch_id"]))
