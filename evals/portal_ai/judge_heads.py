"""멀티헤드 전략 판정 — ours_heads/{id}.json을 기존 판정(judge/)과 같은 기준(Opus)으로 잰다 → judge_heads/{id}.json · heads_report.json

  1) 관련성: 멀티헤드 순위 목록 상위 8 + 채팅 답이 인용한 데이터 중 아직 판정 안 된 것만 0~2점 (judge.py와 같은 지침)
  2) 답 비교: 멀티헤드 채팅 답 ↔ 포털 답, 멀티헤드 ↔ 기존 우리 답 (A/B 무작위)
  3) 지표: 상위 5 핵심(2점) 비율 · 무관(0점) 비율 — 포털 / 기존 전략 / 멀티헤드 순위 / 기존·멀티헤드 채팅 인용
  python -X utf8 -m evals.portal_ai.judge_heads [--workers 4]
"""
from __future__ import annotations

import argparse
import json
import pathlib
import random
import re
from concurrent.futures import ThreadPoolExecutor

from evals.portal_ai.judge import ANS_SYS, REL_SYS, _ask, describe
from pds.service import index

ROOT = pathlib.Path(__file__).resolve().parent
OUT = ROOT / "judge_heads"
CITE = re.compile(r"\[\[(\d+)\]\]")


def ranked(rec: dict) -> list[str]:
    """헤드를 돌아가며 — 대표, 그다음 2점 이상을 점수순. 화면 '주제별' 탭에서 위에 보이는 순서."""
    heads = (rec.get("plan") or {}).get("heads") or []
    per = [[h["rep"]] * bool(h["rep"]) + [p["id"] for p in sorted(h["picks"], key=lambda p: -p["score"]) if p["score"] >= 2 and p["id"] != h["rep"]]
           for h in heads]
    out = []
    for k in range(max((len(x) for x in per), default=0)):
        for x in per:
            if k < len(x) and x[k] not in out:
                out.append(x[k])
    return out


def cited(rec: dict) -> list[str]:
    return list(dict.fromkeys(CITE.findall(((rec.get("chat") or {}).get("reply")) or "")))


def _text(reply: str, ix, cat, ptext) -> str:
    return CITE.sub(lambda m: f"[{describe(m.group(1), ix, cat, ptext).split(' | ')[0]}]", reply or "")


def ab(q: str, x: str, y: str, seed: str) -> tuple[str, dict]:
    """x·y를 무작위 A/B로 — 반환: 승자('x'|'y'|'tie'), 점수."""
    flip = random.Random(seed).random() < 0.5
    A, B = (y, x) if flip else (x, y)
    r = _ask(ANS_SYS, f"질문: {q}\n\n=== 답 A ===\n{A}\n\n=== 답 B ===\n{B}")
    side = {"A": "y" if flip else "x", "B": "x" if flip else "y"}
    inv = {v: k for k, v in side.items()}
    return side.get(r.get("winner"), "tie"), {"x": r.get(inv["x"]), "y": r.get(inv["y"]), "why": r.get("why"),
                                               "x_missing": r.get(f"{inv['x']}_missing"), "y_missing": r.get(f"{inv['y']}_missing")}


def one(qid: str, ix, cat) -> str:
    f = OUT / f"{qid}.json"
    if f.exists():
        return f"{qid} 건너뜀"
    new = json.loads((ROOT / "ours_heads" / f"{qid}.json").read_text(encoding="utf-8"))
    old = json.loads((ROOT / "ours" / f"{qid}.json").read_text(encoding="utf-8"))
    p = json.loads((ROOT / "portal" / f"{qid}.json").read_text(encoding="utf-8"))
    j = json.loads((ROOT / "judge" / f"{qid}.json").read_text(encoding="utf-8"))
    ptext = {c["id"]: f"{c['title']} | {c['text'][:350]}" for c in p["cards"] if c.get("id")}
    rel = dict(j["relevance"])
    todo = [i for i in dict.fromkeys(ranked(new)[:8] + cited(new) + cited(old)) if i not in rel]
    if todo:
        labels = {f"D{k + 1}": i for k, i in enumerate(random.Random(qid).sample(todo, len(todo)))}
        r = _ask(REL_SYS, f"질문: {new['q']}\n\n" + "\n".join(f"{lb}: {describe(i, ix, cat, ptext)}" for lb, i in labels.items()))
        rel |= {labels[k]: v for k, v in r.items() if k in labels}
    portal_ans = "\n\n".join(f"[{c['title']}]\n{c['text']}" for c in p["cards"])
    new_ans = _text((new.get("chat") or {}).get("reply"), ix, cat, ptext)
    old_ans = _text((old.get("chat") or {}).get("reply"), ix, cat, ptext)
    w1, s1 = ab(new["q"], new_ans, portal_ans, qid + "p")
    w2, s2 = ab(new["q"], new_ans, old_ans, qid + "o")
    res = {"id": qid, "q": new["q"], "relevance": rel, "new_extra": todo,
           "vs_portal": {"winner": {"x": "heads", "y": "portal"}.get(w1, "tie"), **s1},
           "vs_old": {"winner": {"x": "heads", "y": "old"}.get(w2, "tie"), **s2}}
    f.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    return f"{qid} 포털전 {res['vs_portal']['winner']} · 기존전 {res['vs_old']['winner']}"


def report() -> dict:
    rows = []
    for f in sorted(OUT.glob("q*.json")):
        jh = json.loads(f.read_text(encoding="utf-8"))
        qid = jh["id"]
        new = json.loads((ROOT / "ours_heads" / f"{qid}.json").read_text(encoding="utf-8"))
        old = json.loads((ROOT / "ours" / f"{qid}.json").read_text(encoding="utf-8"))
        rep = json.loads((ROOT / "report.json").read_text(encoding="utf-8"))
        r0 = next(r for r in rep["rows"] if r["id"] == qid)
        rel = {k: (v[0] if isinstance(v, list) else v) for k, v in jh["relevance"].items()}
        lists = {"portal_top5": r0["portal_top"][:5], "old_plan_top5": r0["ours_plan"][:5], "heads_top5": ranked(new)[:5],
                 "old_chat_cited": cited(old), "heads_chat_cited": cited(new)}
        rows.append({"id": qid, "lists": lists, "rel": rel, "vs_portal": jh["vs_portal"]["winner"], "vs_old": jh["vs_old"]["winner"],
                     "scores_portal": jh["vs_portal"], "gold": [i for i, v in rel.items() if v == 2]})
    agg = {}
    for name in ("portal_top5", "old_plan_top5", "heads_top5", "old_chat_cited", "heads_chat_cited"):
        n = c2 = c0 = 0
        for r in rows:
            for i in r["lists"][name]:
                if i in r["rel"]:
                    n += 1
                    c2 += r["rel"][i] == 2
                    c0 += r["rel"][i] == 0
        agg[name] = {"n": n, "core": round(c2 / max(n, 1), 3), "irrelevant": round(c0 / max(n, 1), 3)}
    # 판정된 핵심(2점) 전체 중 멀티헤드 순위 상위 10이 덮는 비율
    cov = [(len(set(r["gold"]) & set(ranked(json.loads((ROOT / 'ours_heads' / f"{r['id']}.json").read_text(encoding='utf-8')))[:10])), len(r["gold"])) for r in rows]
    from collections import Counter
    out = {"n": len(rows), "precision": agg,
           "heads_top10_gold_coverage": round(sum(a for a, _ in cov) / max(sum(b for _, b in cov), 1), 3),
           "vs_portal": dict(Counter(r["vs_portal"] for r in rows)), "vs_old": dict(Counter(r["vs_old"] for r in rows))}
    crit = {}
    for who in ("x", "y"):
        for k in ("relevance", "coverage", "actionable", "honesty"):
            vs = [(r["scores_portal"].get(who) or {}).get(k) for r in rows]
            vs = [v for v in vs if isinstance(v, (int, float))]
            crit.setdefault({"x": "heads", "y": "portal"}[who], {})[k] = round(sum(vs) / max(len(vs), 1), 2)
    out["criteria_vs_portal"] = crit
    (ROOT / "heads_report.json").write_text(json.dumps({"summary": out, "rows": rows}, ensure_ascii=False, indent=1), encoding="utf-8")
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--report-only", action="store_true")
    a = ap.parse_args()
    OUT.mkdir(exist_ok=True)
    if not a.report_only:
        ix = index.get()
        c = ix.catalog
        cat = {r["id"]: r for r in c[["id", "title", "agency_name", "description"]].to_dict("records")}
        ids = sorted(f.stem for f in (ROOT / "ours_heads").glob("q*.json") if (ROOT / "judge" / f.name).exists())
        with ThreadPoolExecutor(a.workers) as ex:
            for msg in ex.map(lambda q: one(q, ix, cat), ids):
                print(msg, flush=True)
    print(json.dumps(report(), ensure_ascii=False, indent=1))
