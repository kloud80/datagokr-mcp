"""1천 문항 결과 집계 → report.json · report.html (데이터를 넣은 단일 HTML)
  python -X utf8 -m evals.portal_1k.report
"""
from __future__ import annotations

import datetime as dt
import html
import json
import pathlib
import statistics as st
from collections import Counter, defaultdict

import yaml

ROOT = pathlib.Path(__file__).resolve().parent
TYPE_NAME = {"lookup": "단순 조회", "region": "지역 지정", "combine": "데이터 결합", "analysis": "분석·연구", "casual": "일상 말투"}
CRIT = {"relevance": "관련성", "coverage": "측면 포괄", "actionable": "바로 실행", "honesty": "정직성"}


def _load(d: str, i: str) -> dict | None:
    f = ROOT / d / f"{i}.json"
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else None


def _prec(rows: list[dict], key: str) -> dict:
    n = c2 = c0 = 0
    for r in rows:
        for i in r["lists"][key]:
            if i in r["rel"]:
                n += 1
                c2 += r["rel"][i] == 2
                c0 += r["rel"][i] == 0
    return {"n": n, "core": round(c2 / max(n, 1), 3), "irrelevant": round(c0 / max(n, 1), 3)}


def _win(rows: list[dict]) -> dict:
    c = Counter(r["winner"] for r in rows)
    n = len(rows)
    return {"n": n, "ours": c["ours"], "portal": c["portal"], "tie": c["tie"], "ours_rate": round(c["ours"] / max(n, 1), 3)}


def build() -> dict:
    qs = yaml.safe_load((ROOT / "questions.yaml").read_text(encoding="utf-8"))
    rows, missing = [], Counter()
    for q in qs:
        j, p, o = _load("judge", q["id"]), _load("portal", q["id"]), _load("ours", q["id"])
        if not (j and p and o):
            missing["판정 없음" if p and o else "수집 실패"] += 1
            continue
        title = {}
        for c in p.get("cards") or []:
            title[c.get("id")] = c["title"]
        for s in p.get("side") or []:
            title.setdefault(s.get("id"), s["title"])
        for h in (o.get("plan") or {}).get("heads") or []:
            for x in h["picks"]:
                title.setdefault(x["id"], x["title"])
        for x in (o.get("plan") or {}).get("datasets", []) + (o.get("plan") or {}).get("leads", []):
            title.setdefault(x["id"], x["title"])
        a = j["answer"]
        rows.append({"id": q["id"], "q": q["q"], "sector": q["sector"], "type": q.get("type"), "hard": q.get("hard", False),
                     "topic": q.get("topic"), "winner": a["winner"], "why": a.get("why"),
                     "portal_missing": a.get("portal_missing"), "ours_missing": a.get("ours_missing"),
                     "s_portal": a.get("portal") or {}, "s_ours": a.get("ours") or {},
                     "lists": j["lists"], "rel": {k: v for k, v in j["relevance"].items() if isinstance(v, int)},
                     "titles": {i: title.get(i, "") for i in set(sum(j["lists"].values(), []))},
                     "portal_secs": p.get("secs"), "ours_secs": o.get("elapsed_s"), "portal_rejected": p.get("rejected", False),
                     "ours_error": (o.get("chat") or {}).get("error"), "heads": len((o.get("plan") or {}).get("heads") or [])})
    crit = {who: {k: round(st.mean([r[f"s_{who}"][k] for r in rows if isinstance(r[f"s_{who}"].get(k), (int, float))] or [0]), 2)
                  for k in CRIT} for who in ("portal", "ours")}
    by = lambda key: {k: _win(v) for k, v in sorted(_group(rows, key).items(), key=lambda kv: -len(kv[1]))}  # noqa: E731
    out = {
        "generated_at": dt.datetime.now().isoformat(timespec="minutes"), "n_questions": len(qs), "n_judged": len(rows), "missing": dict(missing),
        "overall": _win(rows), "criteria": crit,
        "precision": {"portal_top5": _prec(rows, "portal_top5"), "ours_top5": _prec(rows, "ours_top5"), "ours_cited": _prec(rows, "ours_cited")},
        "by_sector": by("sector"), "by_type": by("type"), "by_hard": by("hard"),
        "by_sector_prec": {s: {"portal": _prec(v, "portal_top5"), "ours": _prec(v, "ours_top5")} for s, v in _group(rows, "sector").items()},
        "time": {"portal_mean": round(st.mean([r["portal_secs"] for r in rows if r["portal_secs"]] or [0]), 1),
                 "ours_mean": round(st.mean([r["ours_secs"] for r in rows if r["ours_secs"]] or [0]), 1)},
        "portal_rejected": sum(r["portal_rejected"] for r in rows), "ours_errors": sum(bool(r["ours_error"]) for r in rows),
    }
    (ROOT / "report.json").write_text(json.dumps({"summary": out, "rows": rows}, ensure_ascii=False, indent=1), encoding="utf-8")
    return {"summary": out, "rows": rows}


def _group(rows, key):
    g = defaultdict(list)
    for r in rows:
        g[r[key]].append(r)
    return g


def render(data: dict, notes: dict | None = None) -> str:
    tpl = (ROOT / "report_template.html").read_text(encoding="utf-8")
    payload = json.dumps({**data, "notes": notes or {}, "type_name": TYPE_NAME, "crit": CRIT}, ensure_ascii=False).replace("</", "<\\/")
    return tpl.replace("/*__DATA__*/null", payload).replace("__GENERATED__", html.escape(data["summary"]["generated_at"]))


if __name__ == "__main__":
    data = build()
    notes_f = ROOT / "notes.json"
    notes = json.loads(notes_f.read_text(encoding="utf-8")) if notes_f.exists() else {}
    (ROOT / "report.html").write_text(render(data, notes), encoding="utf-8")
    print(json.dumps(data["summary"], ensure_ascii=False, indent=1)[:3000])
