"""멀티헤드 전략 — 질문을 주제(헤드)로 나눠 따로 넓게 찾고, 주제마다 다시 줄 세운 뒤, 주제 사이 연결 가능성으로 대표를 다시 고른다.

  1 분해 (LLM 1회)      질문 → 헤드 1~4개 {이름, 한 행이 무엇인지, 필수/보조, 검색어, 필드에 쓰일 말}
  2 수집 (헤드마다)      검증·선정: BM25 + 의미 검색 · 포털 목록 9.6만: BM25(제목·설명·응답 필드) — 검색어마다, RRF로 합쳐 헤드당 POOL개
                         제외 규칙에 걸린 목록 데이터도 후보에 든다 (제외 = 검증 순서일 뿐)
  3 재순위 (LLM, 병렬)   헤드 조건(대상·단위·한 행) 기준 0~3점 — 다른 헤드도 함께 보여 줘 '이 헤드 몫'만 고르게
  4 연결 검토 (규칙)     헤드 사이 데이터 쌍: 선언된 조인(실측) > 같은 키(semantic_type) > 같은 단위로 집계(grain, 목록은 응답 필드로 추정)
  5 대표 재구성          점수 = 관련도 × (0.6 + 0.4·다른 헤드와의 연결) × 층 가중 — 이어지지 않는 1위보다 이어지는 2위가 대표가 될 수 있다
  6 출력                 heads(헤드별 대표·상위 후보·연결) · links(대표끼리 잇는 법) — 플래너가 datasets·joins·leads로 옮긴다
LLM은 데이터를 지어내지 않는다 — 번호로 준 후보에 점수만 매기고, 모르는 번호는 버린다. 실패하면 None (플래너는 기존 검색으로).
"""
from __future__ import annotations

import json
import os
import re
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor

import networkx as nx

from pds.service import index as sindex
from pds.strategy import region as rgn

MODEL = os.environ.get("PDS_HEADS_MODEL") or "claude-sonnet-5-5"  # 2026-10-07 포털 비교: 재순위 Haiku 38% · Sonnet 54% (상위 10 정답)
POOL = 45            # 헤드마다 재순위에 넘기는 후보 수
PER_Q = 30           # 검색어·경로마다 가져오는 수
TOP = 8              # 헤드마다 남기는 상위 후보
TIER_W = {"verified": 1.0, "candidate": 0.85, "catalog": 0.8}
TIER_NAME = {"verified": "검증", "candidate": "선정", "catalog": "목록"}

DECOMPOSE_SYS = """공공데이터를 찾는 질문을 '필요한 데이터 주제(헤드)'로 나눈다. 주제마다 따로 검색하고, 나중에 서로 잇는다.
- 헤드는 1~4개. 질문이 한 대상만 묻으면 1개, 원인·결과·조건처럼 다른 데이터가 필요하면 나눈다 (예: 작황 / 기상).
  지역·시점은 대개 헤드가 아니라 연결 축이다. 지역 자체가 분석 대상(경계·인구 등)일 때만 헤드로.
- name: 짧은 이름 (예: "작황", "기상")
- need: 이 헤드 데이터의 한 행이 무엇이어야 하는지 (예: "시험지역·연도·품종별 벼 수량·생육")
- must: 질문에 답하려면 꼭 있어야 하면 true, 있으면 좋은 보조면 false
- queries: 포털 데이터 제목에 쓰일 법한 검색어 2~5개 (서로 다른 표현·상위어·기관 용어. 예: "벼 작황", "작황 성적", "농작물 생육 조사")
- fields: 그 데이터의 필드(열) 이름에 있을 법한 말 0~6개 (예: "10a당수량", "등숙비율", "출수기")
- axes: 헤드 사이를 이을 축 — space(지역)·time(시점)·entity(같은 대상, 예: 사업장·필지·품종) 중 필요한 것과 한 줄 설명
지명(성수동·부산 등)은 검색어에 넣지 않는다 — 지역은 따로 거른다."""

DECOMPOSE_SCHEMA = {
    "type": "object",
    "properties": {
        "heads": {"type": "array", "items": {"type": "object", "properties": {
            "name": {"type": "string"}, "need": {"type": "string"}, "must": {"type": "boolean"},
            "queries": {"type": "array", "items": {"type": "string"}}, "fields": {"type": "array", "items": {"type": "string"}}},
            "required": ["name", "need", "must", "queries", "fields"], "additionalProperties": False}},
        "axes": {"type": "array", "items": {"type": "object", "properties": {
            "kind": {"type": "string", "enum": ["space", "time", "entity"]}, "note": {"type": "string"}},
            "required": ["kind", "note"], "additionalProperties": False}},
    },
    "required": ["heads", "axes"], "additionalProperties": False,
}

RERANK_SYS = """공공데이터 질문 하나를 여러 주제(헤드)로 나눠 찾고 있다. 지금 볼 헤드의 후보 목록에 0~3점을 매긴다.
3 = 이 헤드가 요구하는 대상을 직접 담음 (need의 한 행과 맞음) · 2 = 이 헤드 몫으로 쓸 만함 (대리 지표·가까운 대상)
1 = 주제만 스침 · 0 = 무관하거나 다른 헤드 몫
- 전국 단위 원장·표준데이터를 한 지역 한정 데이터보다, 개별 건(시설·거래·관측·시험) 데이터를 집계 통계보다 높게.
  질문에 지역이 없으면 한 시도·시군구만 다루는 데이터는 최대 2점 (같은 대상의 전국 데이터가 있으면 그것이 3점).
- 같은 내용의 판(시군구판·연도판)이 여러 개면 가장 넓은 것 하나만 3점, 나머지는 2점 이하.
- 제목 글자만 겹치고 대상이 다르면 0점. 다른 헤드가 맡을 데이터는 이 헤드에서 0~1점.
- [검증]·[선정]·[목록]은 우리가 확인했는지 여부일 뿐 관련성과 무관하다. 목록(미검증)이어도 대상이 맞으면 3점.
1점 이상만 최대 12개, 점수 높은 순으로. why는 10~25자."""

RERANK_SCHEMA = {
    "type": "object",
    "properties": {"picks": {"type": "array", "items": {"type": "object", "properties": {
        "n": {"type": "integer"}, "score": {"type": "integer"}, "why": {"type": "string"}},
        "required": ["n", "score", "why"], "additionalProperties": False}}},
    "required": ["picks"], "additionalProperties": False,
}


def _ask(system: str, user: str, schema: dict, max_tokens: int = 2500) -> dict | None:
    from pds.service import llm
    r = llm.client().beta.messages.create(model=MODEL, max_tokens=max_tokens, system=system, **llm.FALLBACK,
                                          output_config={"effort": "low", "format": {"type": "json_schema", "schema": schema}},
                                          messages=[{"role": "user", "content": user}])
    if r.stop_reason == "refusal":
        return None
    return json.loads(llm._text(r))


# ─────────────────────────── 1 분해
def decompose(goal: str, region_names: list[str]) -> dict | None:
    out = _ask(DECOMPOSE_SYS, goal, DECOMPOSE_SCHEMA, 1500)
    if not out or not out.get("heads"):
        return None
    for h in out["heads"][:4]:
        qs = []
        for q in h["queries"][:5]:
            for n in region_names:
                q = q.replace(n, " ")
            q = re.sub(r"\s+", " ", q).strip()
            if q:
                qs.append(q)
        h["queries"] = qs or [h["name"]]
        h["fields"] = [f for f in h["fields"][:6] if f.strip()]
    out["heads"] = out["heads"][:4]
    return out


# ─────────────────────────── 2 수집
def _rrf(lists: list[list[str]], k: int = 60) -> list[str]:
    sc: dict[str, float] = defaultdict(float)
    for lst in lists:
        for r, i in enumerate(lst):
            sc[i] += 1 / (k + r + 1)
    return [i for i, _ in sorted(sc.items(), key=lambda x: -x[1])]


def _cat_rows(ix, q: str, k: int) -> list[dict]:
    if ix.cat_bm25 is None:
        return []
    out = []
    for i, _ in ix.cat_bm25.search(q, k * 3):
        r = ix.catalog.iloc[i]
        if r["id"] in ix.datasets:  # 검증·선정에 있으면 그쪽으로 (중복 방지)
            continue
        out.append(r.to_dict())
        if len(out) >= k:
            break
    return out


def gather(head: dict, region: dict, items: dict, whole: list[str] | None = None) -> list[str]:
    """헤드 하나의 후보 풀 (id 목록). items에 id → 항목(검증·선정은 dataset dict, 목록은 catalog 행)을 채운다.
    whole: 질문 전체로 찾은 검증 상위(기존 검색·맥락 멤버) — 헤드마다 넣어 두고 재순위가 이 헤드 몫인지 가린다 (분해가 놓친 표현 보완)."""
    from pds.service import semantic
    ix = sindex.get()
    lists = [list(whole)] if whole else []
    for q in head["queries"]:
        lists.append([d["id"] for d, _ in ix.search_datasets(q, PER_Q, tiers=("verified",), graded=False)])
        lists.append([d["id"] for d, _ in ix.search_datasets(q, 8, tiers=("candidate",), graded=False)])
        cat = _cat_rows(ix, q, PER_Q)
        for r in cat:
            items.setdefault(r["id"], {**r, "tier": "catalog"})
        lists.append([r["id"] for r in cat])
    sem_q = f"{head['name']}: {head['need']}"
    lists.append([d["id"] for d, _ in semantic.search(sem_q, PER_Q, tiers=("verified", "candidate"))])
    if head["fields"]:  # 필드에 쓰일 말 — 목록의 응답 필드로
        cat = _cat_rows(ix, " ".join(head["fields"]), PER_Q)
        for r in cat:
            items.setdefault(r["id"], {**r, "tier": "catalog"})
        lists.append([r["id"] for r in cat])
    pool = []
    order = _rrf(lists)
    if whole:  # 질문 전체 검색 상위 8은 순위 합치기에서 밀려도 재순위까지는 간다
        order = list(dict.fromkeys(order[:POOL - 8] + list(whole)[:8] + order[POOL - 8:]))
    for i in order:
        it = items.get(i) or ix.datasets.get(i)
        if it is None:
            continue
        items.setdefault(i, it)
        if rgn.mismatch(_region_view(it), region):
            continue
        pool.append(i)
        if len(pool) >= POOL:
            break
    return pool


def _region_view(it: dict) -> dict:
    return it if it["tier"] != "catalog" else {"agency_name": it.get("agency_name"), "title": it.get("title")}


# ─────────────────────────── 4에 쓰는 항목 메타 (검증 = 실측 grain·필드, 목록 = 응답 필드로 추정)
SPACE_RX = [("point", re.compile(r"위도|경도|좌표|latitude|longitude|\blat\b|\blon\b", re.I)), ("parcel", re.compile(r"pnu|필지고유번호", re.I)),
            ("point", re.compile(r"도로명주소|지번주소|소재지주소|소재지|주소")), ("bjd", re.compile(r"법정동")),
            ("emd", re.compile(r"읍면동|행정동")), ("sgg", re.compile(r"시군구|시군|구군|시험지역|지역코드|지역명")),
            ("sido", re.compile(r"시도명|시도코드|광역"))]
TIME_RX = [("realtime", re.compile(r"실시간|관측시각|측정시각|정시")), ("day", re.compile(r"일자|일시|날짜|년월일|기준일|조사일|관측일")),
           ("month", re.compile(r"년월|월별|기준월")), ("quarter", re.compile(r"분기")), ("year", re.compile(r"연도|년도|기준년"))]
TITLE_SPACE = [("point", re.compile(r"주소|위치|좌표|소재지")), ("emd", re.compile(r"읍면동별|행정동별")),
               ("sgg", re.compile(r"시군구별|시군별|지역별")), ("sido", re.compile(r"시도별|광역시도별"))]
# 필드 메타가 없는 관측망 데이터(종관기상 등) — 제목으로 지점 기반임을 안다. 지점은 지점정보(좌표)로 위치를 얻는다
STATION_TITLE = re.compile(r"기상관측|종관|ASOS|AWS|관측자료|관측데이터|기상자료|측정망|측정소|관측소|기상정보", re.I)
KEY_RX = {"bizno": re.compile(r"사업자\s*등록\s*번호|사업자번호"), "corp_rgst_no": re.compile(r"법인\s*등록\s*번호"),
          "pnu": re.compile(r"pnu|필지고유번호", re.I), "bjd_cd": re.compile(r"법정동\s*코드"),
          "sgg_cd": re.compile(r"시군구\s*코드"), "agri_item_cd": re.compile(r"품목\s*코드|품종\s*코드|작물\s*코드"),
          "station": re.compile(r"지점\s*(번호|코드)|관측소\s*코드|측정소\s*코드|stn", re.I)}


_CAT_POS: dict[float, dict[str, int]] = {}


def _cat_row(dsid: str) -> dict | None:
    ix = sindex.get()
    if ix.catalog is None:
        return None
    pos = _CAT_POS.get(ix.stamp)
    if pos is None:
        pos = _CAT_POS[ix.stamp] = {i: n for n, i in enumerate(ix.catalog["id"])}
    n = pos.get(dsid)
    return ix.catalog.iloc[n].to_dict() if n is not None else None


def _cols_meta(cols: str, title: str) -> dict:
    """응답·요청 필드 이름(목록 메타)으로 단위·키를 추정한다."""
    cols = re.sub(r"(^|,)nan(?=,|$)", r"\1", cols)  # 목록의 빈 칸(NaN)
    space = next((k for k, rx in SPACE_RX if rx.search(cols)), None)
    tm = next((k for k, rx in TIME_RX if rx.search(cols)), None)
    keys = {k for k, rx in KEY_RX.items() if rx.search(cols)}
    via = "address" if space == "point" and re.search("주소|소재지", cols) and not re.search("위도|경도|좌표", cols) else None
    if space is None:  # 필드 메타가 없으면 제목으로 ('…주소 등 정보', '시군구별 …')
        space = next((k for k, rx in TITLE_SPACE if rx.search(title)), None)
        via = "address" if space == "point" else None
    if space is None and ("station" in keys or STATION_TITLE.search(title)):
        space, via = "point", "station"
        keys.add("station")
        tm = tm or "day"
    return {"space": space, "time": tm, "space_via": via, "keys": keys, "estimated": True}


def item_meta(it: dict) -> dict:
    """{space, time, space_via, keys, estimated} — 연결 검토용. 검증 데이터는 실측(grain·semantic_type), 없으면 목록 메타로 추정."""
    if it["tier"] != "catalog":
        g = it.get("grain") or {}
        fs = (it.get("schema") or {}).get("fields") or []
        keys = {f.get("semantic_type") for f in fs if f.get("semantic_type")}
        names = " ".join(f"{f.get('name') or ''} {f.get('title') or ''}" for f in fs)
        if KEY_RX["station"].search(names):
            keys.add("station")
        out = {"space": g.get("space"), "time": g.get("time"), "space_via": g.get("space_via"), "category": g.get("category"),
               "keys": keys - {None, "address", "coord"}, "estimated": False}
        if not out["space"]:  # 실측 단위가 없으면 목록 메타·제목으로 보충 (추정 표시)
            r = _cat_row(it["id"])
            cols = f"{r.get('output_cols') or ''},{r.get('request_vars') or ''}" if r else ""
            est = _cols_meta(cols + "," + names, it["title"])
            if est["space"]:
                out.update(space=est["space"], space_via=est["space_via"], time=out["time"] or est["time"], estimated=True)
                out["keys"] |= est["keys"]
        return out
    return _cols_meta(f"{it.get('output_cols') or ''},{it.get('request_vars') or ''}", it.get("title") or "")


# ─────────────────────────── 3 재순위
def _line(n: int, it: dict, meta: dict) -> str:
    if it["tier"] == "catalog":
        desc = str(it.get("description") or "").replace("\n", " ")[:90]
        cols = str(it.get("output_cols") or "")[:120]
        agency = it.get("agency_name")
        ex = ""
    else:
        cl = it.get("classification") or {}
        desc = (it.get("summary_user") or cl.get("why") or "").replace("\n", " ")[:120]
        cols = ",".join((f.get("title") or f.get("name") or "") for f in ((it.get("schema") or {}).get("fields") or [])[:12])
        agency = it["agency"]["name"]
        ex = ""
    unit = "·".join(x for x in (SPACE_LABEL.get(meta.get("space")), TIME_LABEL.get(meta.get("time"))) if x)
    unit = unit + (" (필드명 추정)" if unit and meta.get("estimated") else "")
    return (f"{n}. [{TIER_NAME[it['tier']]}{ex}] {it['title']} | {agency}" + (f" | 단위 {unit}" if unit else "")
            + (f" | 필드 {cols}" if cols else "") + (f" | {desc}" if desc else ""))


SPACE_LABEL = {"point": "지점·좌표/주소", "parcel": "필지", "bjd": "법정동", "emd": "읍면동", "sgg": "시군구", "sido": "시도", "national": "전국"}
TIME_LABEL = {"realtime": "실시간", "day": "일", "month": "월", "quarter": "분기", "year": "연"}


def rerank_head(goal: str, head: dict, heads: list[dict], pool: list[str], items: dict, metas: dict) -> list[dict]:
    if not pool:
        return []
    others = [h["name"] for h in heads if h is not head]
    msg = (f"질문: {goal}\n\n지금 헤드: {head['name']} — 한 행: {head['need']}" + (" (필수)" if head["must"] else " (보조)")
           + (f"\n다른 헤드: {', '.join(others)}" if others else "") + "\n\n후보:\n"
           + "\n".join(_line(k + 1, items[i], metas[i]) for k, i in enumerate(pool)))
    try:
        out = _ask(RERANK_SYS, msg, RERANK_SCHEMA, 2500)
    except Exception as e:  # noqa: BLE001 — 한 헤드가 실패해도 나머지는 간다
        print(f"[heads] 재순위 실패 {head['name']}: {type(e).__name__}: {str(e)[:120]}", flush=True)
        out = None
    if not out:  # 실패하면 검색 순서 그대로 (점수 1)
        return [{"id": i, "score": 1, "why": "검색 순위"} for i in pool[:TOP]]
    seen, picks = set(), []
    for p in sorted(out["picks"], key=lambda x: -x["score"]):
        if 0 < p["n"] <= len(pool) and pool[p["n"] - 1] not in seen and p["score"] >= 1:
            seen.add(pool[p["n"] - 1])
            picks.append({"id": pool[p["n"] - 1], "score": max(0, min(3, p["score"])), "why": p["why"].strip()[:60]})
    return picks[:TOP + 4]


# ─────────────────────────── 4 연결 검토
def link(a: str, b: str, items: dict, metas: dict, g: nx.Graph, hubs: dict) -> dict | None:
    """두 데이터를 잇는 가장 좋은 방법 — {kind, strength, label, edges?, estimated}."""
    from pds.strategy.plan import align_pair
    if a in g and b in g:
        def cost(u, v, d):
            return d["weight"] + (0.0 if v in hubs or v in (a, b) else 0.8)
        try:
            path = nx.shortest_path(g, a, b, weight=cost)
        except nx.NetworkXNoPath:
            path = None
        if path and len(path) <= 3 and all(m in hubs for m in path[1:-1]):
            es = [g[x][y]["edge"] for x, y in zip(path, path[1:])]
            via = [hubs[m] for m in path[1:-1]]
            return {"kind": "edge", "strength": 1.0, "edges": es, "estimated": False,
                    "label": "선언된 조인" + (f" (via {', '.join(via)})" if via else "")}
    ma, mb = metas[a], metas[b]
    shared = (ma["keys"] & mb["keys"]) - {"sgg_cd", "bjd_cd"}
    est = ma["estimated"] or mb["estimated"]
    if shared:
        k = sorted(shared)[0]
        return {"kind": "key", "strength": 0.75 if est else 0.9, "estimated": est, "label": f"같은 키 {k}" + (" (필드명으로 추정)" if est else "")}
    al = align_pair({k: ma.get(k) for k in ("space", "time", "space_via", "category")},
                    {k: mb.get(k) for k in ("space", "time", "space_via", "category")})
    if al:
        return {"kind": "aligned", "strength": 0.5 if est else 0.7, "estimated": est, "align": al,
                "label": f"{al['label']} 단위로 집계해 결합" + (" (필드명으로 추정)" if est else "")}
    return None


def _region_w(it: dict, region: dict) -> float:
    """목표에 지역이 없으면 한 시도 데이터는 전국 데이터 뒤로 (×0.6 — 3점 지역 데이터 < 2점 전국 데이터), 목표 지역과 같으면 조금 앞으로."""
    r = rgn.dataset_region(_region_view(it))
    if r is None:
        return 1.0
    return 0.6 if not region["sido"] else (1.1 if r in region["sido"] else 1.0)


# ─────────────────────────── 전체
def run(goal: str, region: dict, say=lambda *_: None, whole: list[str] | None = None) -> dict | None:
    from pds.strategy.plan import HUBS, _graph
    t0 = time.time()
    ix = sindex.get()
    try:
        dec = decompose(goal, region["names"])
    except Exception as e:  # noqa: BLE001
        print(f"[heads] 분해 실패: {type(e).__name__}: {str(e)[:160]}", flush=True)
        return None
    if not dec:
        return None
    heads = dec["heads"]
    say("heads", "done", " · ".join(h["name"] + ("" if h["must"] else "(보조)") for h in heads) + f" ({time.time() - t0:.1f}s)")
    items: dict[str, dict] = {}
    pools = [gather(h, region, items, whole) for h in heads]
    metas = {i: item_meta(items[i]) for p in pools for i in p}
    with ThreadPoolExecutor(len(heads)) as ex:
        ranked = list(ex.map(lambda hp: rerank_head(goal, hp[0], heads, hp[1], items, metas), zip(heads, pools)))
    say("rerank", "done", " · ".join(f"{h['name']} {sum(1 for p in r if p['score'] >= 2)}" for h, r in zip(heads, ranked))
        + f" ({time.time() - t0:.1f}s)")

    # 4·5 연결 검토와 대표 재구성
    g = _graph()
    cache: dict[tuple[str, str], dict | None] = {}

    def lk(a, b):
        if (a, b) not in cache:
            cache[(a, b)] = cache[(b, a)] = link(a, b, items, metas, g, HUBS)
        return cache[(a, b)]

    out_heads = []
    for hi, (h, r) in enumerate(zip(heads, ranked)):
        picks = []
        for p in r[:TOP]:
            links, bonus = [], []
            for hj, r2 in enumerate(ranked):
                if hj == hi:
                    continue
                best = None
                for q in r2[:5]:
                    if q["score"] < 2 or q["id"] == p["id"]:
                        continue
                    l = lk(p["id"], q["id"])
                    if l and (best is None or l["strength"] * q["score"] > best[0]):
                        best = (l["strength"] * q["score"] / 3, q["id"], l)
                if best:
                    links.append({"head": heads[hj]["name"], "id": best[1], **{k: v for k, v in best[2].items() if k != "align"}})
                bonus.append(best[0] if best else 0.0)
            conn = sum(bonus) / len(bonus) if bonus else 1.0
            it = items[p["id"]]
            fit = p["score"] / 3 * (0.6 + 0.4 * conn) * TIER_W[it["tier"]] * _region_w(it, region)
            picks.append({**p, "tier": it["tier"], "title": it["title"],
                          "agency": it["agency"]["name"] if it["tier"] != "catalog" else it.get("agency_name"),
                          "excluded_by": it.get("excluded_by") if isinstance(it.get("excluded_by"), str) else None,
                          "unit": "·".join(x for x in (SPACE_LABEL.get(metas[p["id"]].get("space")), TIME_LABEL.get(metas[p["id"]].get("time"))) if x) or None,
                          "unit_estimated": metas[p["id"]]["estimated"], "links": links, "fit": round(fit, 3)})
        rep = max((p for p in picks if p["score"] >= 2), key=lambda p: p["fit"], default=None)
        out_heads.append({"name": h["name"], "need": h["need"], "must": h["must"], "queries": h["queries"], "fields": h["fields"],
                          "rep": rep["id"] if rep else None, "picks": picks})

    links = []
    reps = [(h["name"], h["rep"]) for h in out_heads if h["rep"]]
    for x in range(len(reps)):
        for y in range(x + 1, len(reps)):
            l = lk(reps[x][1], reps[y][1])
            row = {"heads": [reps[x][0], reps[y][0]], "left": reps[x][1], "right": reps[y][1],
                   **({k: v for k, v in l.items()} if l else {"kind": "none", "strength": 0, "label": "대표끼리는 공통 키·단위 없음"})}
            if not l or l["kind"] == "aligned":  # 대표끼리 약하면 두 주제 상위 후보 쌍에서 더 강하게 이어지는 대안을 찾는다
                hx = next(h for h in out_heads if h["name"] == reps[x][0])
                hy = next(h for h in out_heads if h["name"] == reps[y][0])
                alt = None
                for a in [p for p in hx["picks"] if p["score"] >= 2][:5]:
                    for b in [p for p in hy["picks"] if p["score"] >= 2][:5]:
                        if (a["id"], b["id"]) == (reps[x][1], reps[y][1]) or a["id"] == b["id"]:
                            continue
                        l2 = lk(a["id"], b["id"])
                        if l2 and l2["strength"] > (l["strength"] if l else 0) and (alt is None or l2["strength"] * a["score"] * b["score"] > alt[0]):
                            alt = (l2["strength"] * a["score"] * b["score"], a, b, l2)
                if alt:
                    row["alt"] = {"left": alt[1]["id"], "left_title": alt[1]["title"], "right": alt[2]["id"], "right_title": alt[2]["title"],
                                  **{k: v for k, v in alt[3].items() if k != "align"}}
            links.append(row)
    say("links", "done", f"대표 {len(reps)}/{len(heads)} · 연결 {sum(1 for l in links if l['kind'] != 'none')}/{len(links)} ({time.time() - t0:.1f}s)")
    return {"heads": out_heads, "axes": dec["axes"], "links": links, "items": items, "sec": round(time.time() - t0, 1)}
