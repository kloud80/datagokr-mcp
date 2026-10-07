"""단서(catalog) 검색 개선 시제품 — 지금 방식과 나란히 재서 효과를 본다.

  now      지금: 질문 문장 전체 BM25 (제목×2 + 키워드 + 설명 200자)
  fields   + 응답 필드(output_cols)·설명 400자를 검색 글에 넣음
  facet    fields + 질문을 핵심어(규칙)로 나눠 각각 검색한 뒤 순위 합치기(RRF)
  facet_llm  같은데 역할별 검색어를 Haiku가 나눔
판정: judge/{id}.json의 관련성 2점(핵심) 데이터를 정답으로, 상위 10개 안에 몇 개 들어오나.
"""
from __future__ import annotations

import json
import pathlib
import re
from collections import defaultdict

from pds.service import index
from pds.service.index import BM25
from pds.strategy.fit import STOP

ROOT = pathlib.Path(__file__).resolve().parent
JOSA = re.compile(r"(으로|에서|에게|까지|부터|처럼|하고|이랑|를|을|이|가|은|는|의|에|로|와|과|도|만|랑)$")
MORE_STOP = {"데이터", "정보", "현황", "연구", "분석", "예측", "추정", "확인", "조회", "찾기", "비교", "통해", "이용", "활용", "관계", "영향", "상태",
             "지역", "위치", "목록", "공공", "싶다", "싶어", "보고", "있을까", "있는", "하는", "되는", "미리", "알", "수", "큰", "많이", "주변", "동네"}


def facets(q: str) -> list[str]:
    out = []
    for w in re.findall(r"[가-힣A-Za-z0-9]+", q):
        w = JOSA.sub("", w)
        w = re.sub(r"(데이터|정보)$", "", w) or w
        if len(w) >= 2 and w not in STOP and w not in MORE_STOP:
            out.append(w)
    return list(dict.fromkeys(out))


FACET_SYS = """공공데이터를 찾는 질문을 '필요한 데이터 역할'별 검색어로 나눈다. 역할마다 포털에서 데이터 제목에 쓰일 법한 명사 2~4개로.
예) "날씨데이터를 통해 작황 상태를 예측하는 연구" → ["기상 관측 날씨", "작물 작황 생육 수확량"]
예) "아이 키우기 좋은 동네를 초등학교 통학구역과 학원, 공원으로 비교" → ["초등학교 통학구역", "학원 교습소", "도시공원"]
역할은 1~4개. JSON 배열만 출력."""


def facets_llm(q: str, cache: dict) -> list[str]:
    if q in cache:
        return cache[q]
    from pds.service import llm
    r = llm.client().beta.messages.create(model="claude-haiku-4-5-20251001", max_tokens=300, system=FACET_SYS, **llm.FALLBACK,
                                          messages=[{"role": "user", "content": q}])
    m = re.search(r"\[.*\]", llm._text(r), re.S)
    raw = json.loads(m.group(0)) if m else []
    cache[q] = [" ".join(map(str, x)) if isinstance(x, list) else str(x) for x in raw]
    return cache[q]


def rrf(lists: list[list[int]], k: int = 60) -> list[int]:
    sc: dict[int, float] = defaultdict(float)
    for lst in lists:
        for r, i in enumerate(lst):
            sc[i] += 1 / (k + r + 1)
    return [i for i, _ in sorted(sc.items(), key=lambda x: -x[1])]


def build(ix):
    c = ix.catalog
    text = (c["title"].fillna("") + " " + c["title"].fillna("") + " " + c["keywords"].fillna("") + " "
            + c["description"].fillna("").str[:400] + " " + c["output_cols"].fillna("").str[:400])
    return BM25(text.tolist())


def main():
    import pandas as pd
    from pds import config
    ix = index.get()
    cat = pd.read_parquet(config.PROCESSED / "catalog.parquet", columns=["id", "output_cols"])
    ix.catalog = ix.catalog.merge(cat, on="id", how="left") if "output_cols" not in ix.catalog else ix.catalog
    ids = ix.catalog["id"].tolist()
    rich = build(ix)
    res = defaultdict(lambda: [0, 0])
    cf = ROOT / "facets_cache.json"
    cache = json.loads(cf.read_text(encoding="utf-8")) if cf.exists() else {}
    per = []
    for f in sorted((ROOT / "judge").glob("q*.json")):
        j = json.loads(f.read_text(encoding="utf-8"))
        gold = {i for i, v in j["relevance"].items() if isinstance(v, list) and v and v[0] == 2}
        gold &= set(ids)
        if not gold:
            continue
        now = [ids[i] for i, _ in ix.cat_bm25.search(j["q"], 10)]
        fld = [ids[i] for i, _ in rich.search(j["q"], 10)]
        fs = facets(j["q"])
        fac = [ids[i] for i in rrf([[i for i, _ in rich.search(j["q"], 30)]] + [[i for i, _ in rich.search(w, 30)] for w in fs])[:10]]
        fl = facets_llm(j["q"], cache)
        facl = [ids[i] for i in rrf([[i for i, _ in rich.search(j["q"], 30)]] + [[i for i, _ in rich.search(w, 30)] for w in fl])[:10]]
        row = {"id": j["id"], "gold": len(gold), "facets": fs, "facets_llm": fl}
        for name, got in (("now", now), ("fields", fld), ("facet", fac), ("facet_llm", facl)):
            hit = len(gold & set(got))
            res[name][0] += hit
            res[name][1] += len(gold)
            row[name] = hit
        per.append(row)
    cf.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")
    summary = {k: f"{h}/{t} ({h / t:.0%})" for k, (h, t) in res.items()}
    (ROOT / "proto_leads.json").write_text(json.dumps({"summary": summary, "rows": per}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(summary)


if __name__ == "__main__":
    main()
