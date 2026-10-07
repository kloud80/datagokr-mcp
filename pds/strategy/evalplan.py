"""전략 플래너 평가 — evals/plan_recall.yaml의 정답표로 검색·조합이 좋은 데이터를 놓치는지 잰다.

  풀 재현율   검색 단계(조합 전 후보 풀)에 정답 묶음이 들어왔나
  전략 재현율 최종 datasets(핵심+참고)에 들어왔나
  1순위 적중  primary가 정답 묶음 중 하나인가
python -m pds eval-plan [--rerank] [--heads] [--show]
  --heads: 멀티헤드 전략 (LLM) — 풀 = 헤드별 상위 후보 전체
"""
from __future__ import annotations

import time

import yaml

from pds import config

EVAL = config.ROOT / "evals" / "plan_recall.yaml"


def _hit(groups: list[list], ids: set[str]) -> int:
    return sum(any(str(x) in ids for x in g) for g in groups)


def run(rerank: bool = False, show: bool = False, heads: bool = False) -> dict:
    from pds.strategy.plan import plan, select
    items = yaml.safe_load(EVAL.read_text(encoding="utf-8"))
    tot = {"groups": 0, "pool": 0, "plan": 0, "primary": 0, "nice": 0, "nice_hit": 0, "size": 0, "n": len(items), "sec": 0.0}
    for it in items:
        t0 = time.time()
        if heads:
            p = plan(it["q"], use_llm=False, heads=True)
            pool = {x["id"] for h in p.get("heads") or [] for x in h["picks"]} | {d["id"] for d in p["datasets"]}
        else:
            sel = select(it["q"], rerank=rerank)
            p = plan(it["q"], use_llm=False, rerank=rerank, heads=False)
            pool = {d["id"] for d, _ in sel["scored"]}
        tot["sec"] += time.time() - t0
        got = {d["id"] for d in p["datasets"]}
        must, nice = it["must"], [str(x) for x in it.get("nice") or []]
        hp, hq = _hit(must, pool), _hit(must, got)
        prim = bool(p["datasets"]) and any(p["datasets"][0]["id"] in {str(x) for x in g} for g in must)
        tot["groups"] += len(must)
        tot["pool"] += hp
        tot["plan"] += hq
        tot["primary"] += prim
        tot["nice"] += len(nice)
        tot["nice_hit"] += len(set(nice) & got)
        tot["size"] += len(got)
        if show or hq < len(must):
            miss = [g for g in must if not any(str(x) in got for x in g)]
            print(f"{'✓' if hq == len(must) else '✗'} 풀 {hp}/{len(must)} 전략 {hq}/{len(must)} 1순위{'○' if prim else '×'} "
                  f"{len(got)}개  {it['q'][:40]}" + (f"  놓침 {miss}" if miss else ""))
    g = tot["groups"]
    out = {"풀 재현율": round(tot["pool"] / g, 3), "전략 재현율": round(tot["plan"] / g, 3),
           "1순위 적중": round(tot["primary"] / tot["n"], 3), "nice 적중": round(tot["nice_hit"] / max(tot["nice"], 1), 3),
           "평균 데이터 수": round(tot["size"] / tot["n"], 1), "질문당 초": round(tot["sec"] / tot["n"], 2)}
    print(out)
    return out
