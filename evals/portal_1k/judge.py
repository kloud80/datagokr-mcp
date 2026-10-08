"""1천 문항 판정 (Opus, 일회성) — evals/portal_ai와 같은 지침(REL_SYS·ANS_SYS)으로 → judge/{id}.json

  1) 데이터 관련성 0~2: 포털 상위 5(추천 카드 → 모자라면 오른쪽 추천데이터) + 우리 상위 5(주제별 대표 → 2점 이상 후보)
     + 우리 채팅 답이 인용한 데이터. 출처를 숨기고 섞는다.
  2) 답 비교: 포털 답(카드 글) ↔ 우리 채팅 답, A/B 무작위, 기준별 1~5점과 승자
  python -X utf8 -m evals.portal_1k.judge [--workers 6]
"""
from __future__ import annotations

import argparse
import json
import pathlib
import random
import re
from concurrent.futures import ThreadPoolExecutor

from evals.portal_ai.judge import ANS_SYS, REL_SYS, _ask, describe
from evals.portal_ai.judge_heads import cited, ranked
from pds.service import index

ROOT = pathlib.Path(__file__).resolve().parent
OUT = ROOT / "judge"
CITE = re.compile(r"\[\[(\d+)\]\]")


def portal_top(p: dict, n: int = 5) -> list[str]:
    ids = [c["id"] for c in p.get("cards") or [] if c.get("id")]
    ids += [s["id"] for s in p.get("side") or [] if s.get("id")]
    return list(dict.fromkeys(ids))[:n]


def ours_top(o: dict, n: int = 5) -> list[str]:
    r = ranked(o)
    if not r:  # 주제 분해가 안 된 경우 — 전략 datasets → 단서
        pl = o.get("plan") or {}
        r = [d["id"] for d in pl.get("datasets") or []] + [x["id"] for x in pl.get("leads") or []]
    return list(dict.fromkeys(r))[:n]


def one(qid: str, ix, cat) -> str:
    f = OUT / f"{qid}.json"
    if f.exists():
        return f"{qid} 건너뜀"
    p = json.loads((ROOT / "portal" / f"{qid}.json").read_text(encoding="utf-8"))
    o = json.loads((ROOT / "ours" / f"{qid}.json").read_text(encoding="utf-8"))
    ptext = {c["id"]: f"{c['title']} | {c['text'][:350]}" for c in p.get("cards") or [] if c.get("id")}
    ptext |= {s["id"]: s["title"] for s in p.get("side") or [] if s.get("id") and s["id"] not in ptext}
    lists = {"portal_top5": portal_top(p), "ours_top5": ours_top(o), "ours_cited": cited(o)}
    ids = list(dict.fromkeys(sum(lists.values(), [])))
    rnd = random.Random(qid)
    sh = ids[:]
    rnd.shuffle(sh)
    labels = {f"D{k + 1}": i for k, i in enumerate(sh)}
    rel = {}
    if labels:
        r = _ask(REL_SYS, f"질문: {p['q']}\n\n" + "\n".join(f"{lb}: {describe(i, ix, cat, ptext)}" for lb, i in labels.items()))
        rel = {labels[k]: (v[0] if isinstance(v, list) else v) for k, v in r.items() if k in labels}
    portal_ans = "\n\n".join(f"[{c['title']}]\n{c['text']}" for c in p.get("cards") or []) or _plain_reject(p)
    ours_ans = CITE.sub(lambda m: f"[{describe(m.group(1), ix, cat, ptext).split(' | ')[0]}]", (o.get("chat") or {}).get("reply") or "(답 없음)")
    a_portal = rnd.random() < 0.5
    A, B = (portal_ans, ours_ans) if a_portal else (ours_ans, portal_ans)
    ans = _ask(ANS_SYS, f"질문: {p['q']}\n\n=== 답 A ===\n{A}\n\n=== 답 B ===\n{B}")
    side = {"A": "portal" if a_portal else "ours", "B": "ours" if a_portal else "portal"}
    inv = {v: k for k, v in side.items()}
    res = {"id": qid, "q": p["q"], "lists": lists, "relevance": rel,
           "answer": {"portal": ans.get(inv["portal"]), "ours": ans.get(inv["ours"]), "winner": side.get(ans.get("winner"), "tie"),
                      "portal_missing": ans.get(f"{inv['portal']}_missing"), "ours_missing": ans.get(f"{inv['ours']}_missing"),
                      "why": ans.get("why")}}
    if not ans:
        return f"{qid} 판정 실패"
    f.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    return f"{qid} 승자 {res['answer']['winner']}"


def _plain_reject(p: dict) -> str:
    return f"(추천 데이터 없음) {p.get('answer') or ''}".strip()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=6)
    a = ap.parse_args()
    OUT.mkdir(exist_ok=True)
    ix = index.get()
    cat = {r["id"]: r for r in ix.catalog[["id", "title", "agency_name", "description"]].to_dict("records")}
    ids = sorted(f.stem for f in (ROOT / "ours").glob("k*.json") if (ROOT / "portal" / f.name).exists())
    with ThreadPoolExecutor(a.workers) as ex:
        for msg in ex.map(lambda q: one(q, ix, cat), ids):
            print(msg, flush=True)
