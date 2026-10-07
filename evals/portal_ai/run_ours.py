"""우리 답 수집 — 질문마다 전략(LLM 없이)과 채팅 답(도구 호출 포함)을 evals/portal_ai/ours/{id}.json에 남긴다.

  python -X utf8 evals/portal_ai/run_ours.py [--workers 3]
이미 있는 파일은 건너뛴다 (중단돼도 이어서).
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


def one(item: dict) -> str:
    f = OUT / f"{item['id']}.json"
    if f.exists():
        return f"{item['id']} 건너뜀"
    from pds.service import llm
    from pds.strategy.plan import jsonable, plan
    t0 = time.time()
    p = plan(item["q"], use_llm=False)
    rec = {**item, "plan": {"datasets": [{"id": d["id"], "title": d["title"], "role": d.get("role")} for d in p["datasets"]],
                            "leads": [{"id": x["id"], "title": x["title"]} for x in p.get("unverified_leads") or []],
                            "joins": len(p.get("joins") or []), "gaps": p.get("gaps"), "context": p.get("context")}}
    try:
        out = llm.chat([{"role": "user", "content": item["q"]}])
        plans = out.get("plans") or []
        last = plans[-1] if plans else {}
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
    a = ap.parse_args()
    OUT.mkdir(exist_ok=True)
    items = yaml.safe_load((ROOT / "questions.yaml").read_text(encoding="utf-8"))
    from pds.service import index
    index.get()  # 색인을 먼저 올린다 (스레드마다 만들지 않게)
    with ThreadPoolExecutor(a.workers) as ex:
        for msg in ex.map(one, items):
            print(msg, flush=True)
