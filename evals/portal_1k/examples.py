"""채팅 첫 화면 예시 질문 풀 — 포털 AI 비교 1천 문항 중 우리 추천이 크게 앞선 것 (python -m evals.portal_1k.examples).

고르는 기준: 판정 winner=ours, 핵심 데이터(관련도 2) 수가 포털보다 4개 이상 많고, 답변 점수 합 차이 8 이상.
showcase(★, notes.json)는 기준과 상관없이 넣는다. 화면은 이 풀에서 6개씩 돌려 보여 준다.
출력: frontend/src/examples.json — [{q, portal, ours}] (portal·ours = 핵심 데이터 수)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

D = Path(__file__).parent
OUT = D.parents[1] / "frontend" / "src" / "examples.json"


def build(min_gap: int = 4, min_score: int = 8) -> list[dict]:
    star = {s["id"] for s in json.loads((D / "notes.json").read_text(encoding="utf-8")).get("showcase") or []}
    out = []
    for f in sorted((D / "judge").glob("*.json")):
        j = json.loads(f.read_text(encoding="utf-8"))
        rel, lists, ans = j.get("relevance") or {}, j.get("lists") or {}, j.get("answer") or {}
        core = lambda ids: sum(1 for i in set(ids) if rel.get(i) == 2)  # noqa: E731
        p = core(lists.get("portal_top5") or [])
        o = core((lists.get("ours_top5") or []) + (lists.get("ours_cited") or []))
        score = sum((ans.get("ours") or {}).values()) - sum((ans.get("portal") or {}).values())
        if j["id"] in star or (ans.get("winner") == "ours" and o - p >= min_gap and score >= min_score):
            out.append({"q": j["q"], "portal": p, "ours": o, "gap": o - p, "id": j["id"]})
    out.sort(key=lambda x: -x["gap"])
    return [{k: x[k] for k in ("q", "portal", "ours")} for x in out if len(x["q"]) <= 45]


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    ex = build()
    OUT.write_text(json.dumps(ex, ensure_ascii=False, indent=1), encoding="utf-8")
    print(OUT, len(ex))
