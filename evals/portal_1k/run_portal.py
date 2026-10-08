"""포털 AI 답 수집 — 화면(aiAssistant.do)이 부르는 순서 그대로 HTTP로 부른다 → portal/{id}.json

  1) /llm/sch/getSummaryQuery.do {prmpt: 질문, history: []} → 질문 요약(JSON 문자열, normalYn=N이면 거부 답)
  2) /llm/sch/stream.do {prmpt: 요약, history: []} → 답(HTML 마크다운, 추천 카드 h4) 스트림
  3) /llm/sch/search.do {prmpt: 요약} → 오른쪽 추천데이터 30개(정확도순)
화면이 대화 기록을 남기는 insertInteraction은 부르지 않는다. 동시 3개 + 질문 사이 쉼으로 서버 부담을 줄인다.
  python -X utf8 -m evals.portal_1k.run_portal [--workers 3]
"""
from __future__ import annotations

import argparse
import html
import json
import pathlib
import re
import time
from concurrent.futures import ThreadPoolExecutor

import httpx
import yaml

ROOT = pathlib.Path(__file__).resolve().parent
OUT = ROOT / "portal"
BASE = "https://www.data.go.kr"
H = {"User-Agent": "Mozilla/5.0", "Referer": BASE + "/tcs/dss/aiAssistant.do", "Origin": BASE}
CARD = re.compile(r"<h4[^>]*>(.*?)</h4>(.*?)(?=<h4|\Z)", re.S)
LINK = re.compile(r'<a[^>]*href="[^"]*/data/(\d+)/[^"]*"[^>]*>(.*?)</a>', re.S)


def _plain(s: str) -> str:
    return html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", s))).strip()


def parse_cards(answer: str) -> list[dict]:
    out = []
    for head, body in CARD.findall(answer or ""):
        m = LINK.search(head)
        body = re.split(r"추천 질문", body)[0]
        out.append({"id": m.group(1) if m else None, "title": _plain(m.group(2) if m else head), "text": _plain(body)})
    return out


def ask(c: httpx.Client, q: str) -> dict:
    t0 = time.time()
    r = c.post(BASE + "/llm/sch/getSummaryQuery.do", json={"prmpt": q, "history": []})
    r.raise_for_status()
    summary = r.json()
    sj = json.loads(summary) if isinstance(summary, str) else summary
    if sj.get("normalYn") == "N":
        return {"secs": round(time.time() - t0), "summary": sj, "rejected": True, "answer": sj.get("answer"), "cards": [], "side": []}
    acc = ""
    with c.stream("POST", BASE + "/llm/sch/stream.do", json={"prmpt": summary, "history": []}) as s:
        for line in s.iter_lines():
            line = line.strip()
            if not line.startswith("data:"):
                continue
            try:
                d = json.loads(line[5:].strip())
            except ValueError:
                continue
            if (d.get("message") or {}).get("content") and d.get("stopReason") != "stop":
                acc += d["message"]["content"]
    side = []
    if acc and not acc.startswith("추천드릴 데이터가 없습니다"):
        r = c.post(BASE + "/llm/sch/search.do", json={"prmpt": summary})
        if r.status_code == 200:
            side = [{"id": x.get("docId"), "title": (x.get("content") or "")[:80], "score": x.get("score"),
                     "svc": (x.get("metadata") or {}).get("svcType")} for x in r.json()]
    return {"secs": round(time.time() - t0), "summary": sj, "rejected": False, "answer": acc, "cards": parse_cards(acc), "side": side}


def one(item: dict) -> str:
    f = OUT / f"{item['id']}.json"
    if f.exists():
        return f"{item['id']} 건너뜀"
    err = None
    for k in range(3):
        try:
            with httpx.Client(headers=H, timeout=180) as c:
                c.get(BASE + "/tcs/dss/aiAssistant.do")
                rec = {**item, **ask(c, item["q"])}
            break
        except Exception as e:  # noqa: BLE001
            err = f"{type(e).__name__}: {str(e)[:200]}"
            time.sleep(10 * (k + 1))
    else:
        return f"{item['id']} 실패 {err}"
    f.write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
    time.sleep(2)
    return f"{item['id']} {rec['secs']}s 카드 {len(rec['cards'])} 추천 {len(rec['side'])}" + (" 거부" if rec["rejected"] else "")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()
    OUT.mkdir(exist_ok=True)
    items = yaml.safe_load((ROOT / "questions.yaml").read_text(encoding="utf-8"))
    if a.limit:
        items = items[:a.limit]
    with ThreadPoolExecutor(a.workers) as ex:
        for msg in ex.map(one, items):
            print(msg, flush=True)
