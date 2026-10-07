"""단서 재순위 시제품 — 후보 풀(문장 BM25 + 역할별 검색어 BM25)을 LLM이 질문 기준으로 다시 줄 세운다.

정답: judge/{id}.json 관련성 2점. 지표: 상위 10개 안 정답 수 (proto_leads.py와 같은 기준).
  python -X utf8 evals/portal_ai/proto_rerank.py [--model claude-haiku-4-5-20251001] [--pool 60]
"""
from __future__ import annotations

import argparse
import glob
import json
import pathlib
import re
from concurrent.futures import ThreadPoolExecutor

import pandas as pd

from evals.portal_ai.proto_leads import build, rrf
from pds import config
from pds.service import index, llm

ROOT = pathlib.Path(__file__).resolve().parent
SYS = """공공데이터를 찾는 질문과 후보 데이터 목록이 있다. 질문에 답하는 데 직접 쓸 데이터를 쓸모 있는 순서로 최대 10개 고른다.
질문이 여러 역할(예: 날씨 + 작황)을 요구하면 역할마다 가장 좋은 데이터가 위쪽에 고루 들어가게 한다.
전국 단위 원장·표준데이터를 지역 한정 데이터보다, 개별 건(시설·거래·측정) 데이터를 집계 통계보다 앞에 둔다.
번호만 JSON 배열로 출력. 예: [3, 17, 1]"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="claude-haiku-4-5-20251001")
    ap.add_argument("--pool", type=int, default=60, help="검색어마다 가져올 후보 수")
    a = ap.parse_args()
    ix = index.get()
    cat = pd.read_parquet(config.PROCESSED / "catalog.parquet", columns=["id", "output_cols"])
    ix.catalog = ix.catalog.merge(cat, on="id", how="left")
    c = ix.catalog
    ids = c["id"].tolist()
    rich = build(ix)
    fc = json.loads((ROOT / "facets_cache.json").read_text(encoding="utf-8"))

    def line(k: int, i: int) -> str:
        r = c.iloc[i]
        return f"{k}. {r['title']} | {r['agency_name']} | {str(r['description'] or '')[:90]}"

    def one(f: str):
        j = json.loads(pathlib.Path(f).read_text(encoding="utf-8"))
        gold = {i for i, v in j["relevance"].items() if isinstance(v, list) and v[0] == 2} & set(ids)
        if not gold:
            return None
        lists = [[i for i, _ in ix.cat_bm25.search(j["q"], a.pool)]] + [[i for i, _ in rich.search(w, a.pool)] for w in fc.get(j["q"], [])]
        pool = rrf(lists)[:a.pool * 3]
        r = llm.client().beta.messages.create(model=a.model, max_tokens=300, system=SYS, **llm.FALLBACK, messages=[
            {"role": "user", "content": f"질문: {j['q']}\n\n" + "\n".join(line(k + 1, i) for k, i in enumerate(pool))}])
        m = re.search(r"\[[\d,\s]*\]", llm._text(r))
        pick = [pool[k - 1] for k in json.loads(m.group(0)) if 0 < k <= len(pool)][:10] if m else []
        top = {ids[i] for i in pick}
        return j["id"], len(gold), len(gold & top), len(gold & {ids[i] for i in pool})

    files = sorted(glob.glob(str(ROOT / "judge" / "q*.json")))
    with ThreadPoolExecutor(6) as ex:
        rows = [x for x in ex.map(one, files) if x]
    g = sum(x[1] for x in rows)
    print(a.model, f"pool {a.pool}×검색어", f"상위10 {sum(x[2] for x in rows)}/{g} ({sum(x[2] for x in rows) / g:.0%})",
          f"풀 {sum(x[3] for x in rows)}/{g} ({sum(x[3] for x in rows) / g:.0%})")
    (ROOT / f"proto_rerank_{a.model.split('-')[1]}.json").write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
