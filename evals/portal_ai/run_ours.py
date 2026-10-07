"""우리 답 수집 — 질문마다 전략(LLM 없이)과 채팅 답(도구 호출 포함)을 evals/portal_ai/ours/{id}.json에 남긴다.

  python -X utf8 evals/portal_ai/run_ours.py [--workers 3] [--out ours_heads --chat-only]
이미 있는 파일은 건너뛴다 (중단돼도 이어서). --chat-only: 전략을 따로 부르지 않고 채팅이 부른 전략(첫 버전)을 쓴다 (멀티헤드는 LLM을 쓰므로 두 번 부르지 않게).
"""
from __future__ import annotations

import argparse
import json
import pathlib
import time
from concurrent.futures import ThreadPoolExecutor

import yaml

ROOT = pathlib.Path(__file__).resolve().parent
OUT = ROOT / "ours"
CHAT_ONLY = False


def _heads(p: dict) -> dict:
    return {"heads": [{"name": h["name"], "must": h["must"], "rep": h["rep"],
                       "picks": [{k: x.get(k) for k in ("id", "tier", "title", "score")} for x in h["picks"]]} for h in p.get("heads") or []],
            "head_links": [{k: l.get(k) for k in ("heads", "kind", "label")} for l in p.get("head_links") or []]}


def one(item: dict) -> str:
    f = OUT / f"{item['id']}.json"
    if f.exists():
        return f"{item['id']} 건너뜀"
    from pds.service import llm
    from pds.strategy.plan import jsonable, plan
    t0 = time.time()

    def summ(p: dict) -> dict:
        return {"datasets": [{"id": d["id"], "title": d["title"], "role": d.get("role")} for d in p["datasets"]],
                "leads": [{"id": x["id"], "title": x["title"]} for x in p.get("unverified_leads") or []],
                "joins": len(p.get("joins") or []), "gaps": p.get("gaps"), "context": p.get("context"), "source": p.get("source"), **_heads(p)}
    rec = {**item}
    if not CHAT_ONLY:
        rec["plan"] = summ(plan(item["q"], use_llm=False))
    try:
        out = llm.chat([{"role": "user", "content": item["q"]}])
        plans = out.get("plans") or []
        last = plans[-1] if plans else {}
        if CHAT_ONLY and plans:
            rec["plan"] = summ(plans[0])
        rec["chat"] = {"reply": out.get("reply"), "trace": out.get("trace"), "usage": out.get("usage"),
                       "datasets": [{"id": d["id"], "title": d["title"]} for d in last.get("datasets") or []],
                       "leads": [{"id": x["id"], "title": x["title"]} for x in last.get("unverified_leads") or []]}
    except Exception as e:  # noqa: BLE001
        rec["chat"] = {"error": f"{type(e).__name__}: {str(e)[:300]}"}
    rec["elapsed_s"] = round(time.time() - t0, 1)
    f.write_text(json.dumps(jsonable(rec), ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    return f"{item['id']} {rec['elapsed_s']}s"


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--out", default="ours")
    ap.add_argument("--chat-only", action="store_true")
    a = ap.parse_args()
    OUT = ROOT / a.out
    CHAT_ONLY = a.chat_only
    OUT.mkdir(exist_ok=True)
    items = yaml.safe_load((ROOT / "questions.yaml").read_text(encoding="utf-8"))
    from pds.service import index
    index.get()  # 색인을 먼저 올린다 (스레드마다 만들지 않게)
    with ThreadPoolExecutor(a.workers) as ex:
        for msg in ex.map(one, items):
            print(msg, flush=True)
