"""포털 AI(aiAssistant.do) 답과 우리 답 비교 — evals/portal_ai/{portal,ours}/{id}.json → report.json

질문마다
  portal_top   포털 추천 카드 5개 · portal_side 오른쪽 추천데이터 (정확도순 30)
  ours_plan    전략 datasets (검증) · ours_leads 미검증 단서 · ours_chat 채팅 답의 전략 datasets
포털에만 있는 데이터는 우리가 왜 못 냈는지 나눈다:
  retrieval  우리 지식 체계(verified)에 있는데 전략에 안 들어옴 — 검색·선정 문제
  candidate  선정됐으나 미검증
  excluded   프로젝트 제외 규칙 (규칙 id)
  unselected 목록에는 있고 제외도 아닌데 선정 안 됨
  new        우리 목록 스냅샷에 없음 (스냅샷 이후 등록)
관련성 판정(judge)은 따로 — judge.py.
"""
from __future__ import annotations

import json
import pathlib
from collections import Counter

import pandas as pd

from pds import config
from pds.service import index

ROOT = pathlib.Path(__file__).resolve().parent


def why_missing(i: str, ix, cls: dict, cat: set) -> str:
    d = ix.datasets.get(i)
    if d:
        return "retrieval" if d["tier"] == "verified" else "candidate"
    if i not in cat:
        return "new"
    ex = cls.get(i)
    return f"excluded:{ex}" if isinstance(ex, str) else "unselected"


def main() -> dict:
    ix = index.get()
    c = pd.read_parquet(config.PROCESSED / "class.parquet", columns=["id", "excluded_by"])
    cls = dict(zip(c["id"], c["excluded_by"]))
    cat = set(ix.catalog["id"]) if ix.catalog is not None else set()
    rows, agg = [], Counter()
    for f in sorted((ROOT / "portal").glob("q*.json")):
        p = json.loads(f.read_text(encoding="utf-8"))
        of = ROOT / "ours" / f.name
        if not of.exists() or p.get("error"):
            continue
        o = json.loads(of.read_text(encoding="utf-8"))
        top = [x["id"] for x in p["cards"] if x.get("id")]
        side = [x["id"] for x in p["side"] if x.get("id")]
        plan = [x["id"] for x in o["plan"]["datasets"]]
        leads = [x["id"] for x in o["plan"]["leads"]]
        chat = [x["id"] for x in (o.get("chat") or {}).get("datasets") or []]
        ours = set(plan) | set(leads) | set(chat)
        miss = {i: why_missing(i, ix, cls, cat) for i in top if i not in ours}
        for v in miss.values():
            agg[v.split(":")[0]] += 1
        rows.append({"id": p["id"], "q": p["q"], "set": o.get("set"), "portal_top": top, "portal_side": side[:30],
                     "ours_plan": plan, "ours_leads": leads, "ours_chat": chat,
                     "top_in_ours": [i for i in top if i in ours], "top_missing": miss,
                     "top_in_side_of_ours": len(set(side[:30]) & ours)})
    out = {"n": len(rows), "missing_reason": dict(agg), "rows": rows}
    (ROOT / "report.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    return out


if __name__ == "__main__":
    r = main()
    print(r["n"], r["missing_reason"])
