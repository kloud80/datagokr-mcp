"""관련성·답 품질 판정 (Opus, 일회성) — report.json + portal/ours → judge/{id}.json

  1) 데이터 관련성: 질문마다 포털 추천 5개 + 우리 전략·채팅 데이터를 섞어(출처 숨김) 0~2점
     2 = 질문의 핵심 대상을 직접 담음 · 1 = 보조로 쓸 만함 · 0 = 관련 없음
  2) 답 비교: 포털 답(추천 카드 글)과 우리 채팅 답을 A/B로 무작위 배치해 기준별 1~5점과 승자
  python -X utf8 evals/portal_ai/judge.py [--workers 4]
"""
from __future__ import annotations

import argparse
import json
import pathlib
import random
import re
from concurrent.futures import ThreadPoolExecutor

import pandas as pd

from pds import config
from pds.service import index, llm

ROOT = pathlib.Path(__file__).resolve().parent
OUT = ROOT / "judge"
MODEL = "claude-opus-5-5"

REL_SYS = """너는 공공데이터 전문가다. 사용자의 질문과 공공데이터 후보 목록을 보고, 각 데이터가 질문에 얼마나 쓸모 있는지 판정한다.
2 = 질문의 핵심 대상(무엇을·어디서·언제)을 직접 담고 있어 바로 분석에 쓸 수 있다
1 = 핵심은 아니지만 보조·맥락으로 쓸 만하다
0 = 질문과 관련이 없거나, 이름만 비슷하고 실제로는 쓸 수 없다 (예: 다른 기관의 내부 재무표, 엉뚱한 지역 한정)
제목·기관·설명만 보고 판단한다. JSON만 출력: {"D1": [점수, "한 줄 이유"], ...}"""

ANS_SYS = """너는 공공데이터 활용 컨설턴트다. 같은 질문에 대한 두 답(A, B)을 비교한다. 두 답의 출처는 알려주지 않는다.
기준마다 1~5점:
 relevance   추천 데이터가 질문의 핵심 대상에 맞는가
 coverage    질문이 요구하는 여러 측면(예: 날씨+작황)을 빠짐없이 덮는가
 actionable  데이터를 어떻게 잇고 받고 분석하는지 바로 실행할 수 있게 알려주는가
 honesty     없는 것을 있다고 하거나 과장하지 않는가, 한계를 정확히 말하는가
그리고 사용자가 실제로 더 도움을 받을 답을 고른다.
JSON만 출력: {"A": {"relevance":n,"coverage":n,"actionable":n,"honesty":n}, "B": {...}, "winner": "A"|"B"|"tie",
"A_missing": "A가 놓친 핵심 (짧게)", "B_missing": "B가 놓친 핵심 (짧게)", "why": "두세 문장"}"""


def _json(text: str) -> dict:
    k = text.find("{")  # 첫 JSON 객체만 (뒤에 덧붙은 설명은 버린다)
    if k < 0:
        return {}
    try:
        return json.JSONDecoder().raw_decode(text[k:])[0]
    except ValueError:
        return {}


def _ask(system: str, user: str) -> dict:
    r = llm.client().beta.messages.create(model=MODEL, max_tokens=4000, system=system, **llm.FALLBACK,
                                          messages=[{"role": "user", "content": user}])
    return _json(llm._text(r))


def describe(i: str, ix, cat: dict, portal_text: dict) -> str:
    d = ix.datasets.get(i)
    r = cat.get(i)
    if r is not None:
        return f"{r['title']} | {r['agency_name']} | {(r['description'] or '')[:350]}"
    if d:
        return f"{d['title']} | {d['agency']['name']} | {(d.get('description_portal') or d.get('summary_user') or '')[:350]}"
    return portal_text.get(i) or i


def one(row: dict, ix, cat: dict) -> str:
    f = OUT / f"{row['id']}.json"
    if f.exists():
        return f"{row['id']} 건너뜀"
    p = json.loads((ROOT / "portal" / f"{row['id']}.json").read_text(encoding="utf-8"))
    o = json.loads((ROOT / "ours" / f"{row['id']}.json").read_text(encoding="utf-8"))
    ptext = {c["id"]: f"{c['title']} | {c['text'][:350]}" for c in p["cards"] if c.get("id")}
    ptext |= {s["id"]: s["title"] for s in p["side"] if s.get("id") and s["id"] not in ptext}
    ids = list(dict.fromkeys(row["portal_top"] + row["ours_plan"][:8] + row["ours_chat"][:8]))
    rnd = random.Random(row["id"])
    shuffled = ids[:]
    rnd.shuffle(shuffled)
    labels = {f"D{k + 1}": i for k, i in enumerate(shuffled)}
    rel = _ask(REL_SYS, f"질문: {row['q']}\n\n" + "\n".join(f"{lb}: {describe(i, ix, cat, ptext)}" for lb, i in labels.items()))
    scores = {labels[k]: v for k, v in rel.items() if k in labels}
    portal_ans = "\n\n".join(f"[{c['title']}]\n{c['text']}" for c in p["cards"])
    ours_ans = re.sub(r"\[\[(\d+)\]\]", lambda m: f"[{describe(m.group(1), ix, cat, ptext).split(' | ')[0]}]", (o.get("chat") or {}).get("reply") or "")
    a_is_portal = rnd.random() < 0.5
    A, B = (portal_ans, ours_ans) if a_is_portal else (ours_ans, portal_ans)
    ans = _ask(ANS_SYS, f"질문: {row['q']}\n\n=== 답 A ===\n{A}\n\n=== 답 B ===\n{B}")
    side = {"A": "portal" if a_is_portal else "ours", "B": "ours" if a_is_portal else "portal"}
    res = {"id": row["id"], "q": row["q"], "relevance": scores,
           "answer": {"portal": ans.get(next(k for k, v in side.items() if v == "portal")), "ours": ans.get(next(k for k, v in side.items() if v == "ours")),
                      "winner": side.get(ans.get("winner"), "tie"),
                      "portal_missing": ans.get(f"{next(k for k, v in side.items() if v == 'portal')}_missing"),
                      "ours_missing": ans.get(f"{next(k for k, v in side.items() if v == 'ours')}_missing"), "why": ans.get("why")}}
    f.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    return f"{row['id']} 승자 {res['answer']['winner']}"


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=4)
    a = ap.parse_args()
    OUT.mkdir(exist_ok=True)
    ix = index.get()
    c = ix.catalog
    cat = {r["id"]: r for r in c[["id", "title", "agency_name", "description"]].to_dict("records")} if c is not None else {}
    rows = json.loads((ROOT / "report.json").read_text(encoding="utf-8"))["rows"]
    with ThreadPoolExecutor(a.workers) as ex:
        for msg in ex.map(lambda r: one(r, ix, cat), rows):
            print(msg, flush=True)
