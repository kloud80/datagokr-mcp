"""지식 색인 — 서비스(API·채팅·MCP)가 쓰는 메모리 색인. knowledge/*.yaml(verified·candidate)과 카탈로그(catalog 층 9.6만)를 한 번 읽어 캐시한다.

검색은 글자 2-gram + 단어 BM25 (형태소 분석기 없이 한국어 복합어에 강하다). KNOWLEDGE-SPEC의 bge-m3 임베딩은 이 search() 뒤에 끼우면 된다.
캐시: data/processed/service_index.pkl — knowledge/ 파일 수정 시각이 바뀌면 다시 만든다.
"""
from __future__ import annotations

import math
import pickle
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from functools import lru_cache

import pandas as pd

from pds import config
from pds.schema import GROUNDED
from pds.schema import store

CACHE = config.PROCESSED / "service_index.pkl"
TOKEN = re.compile(r"[가-힣]+|[A-Za-z]+|\d+")


def tokens(text: str) -> list[str]:
    out = []
    for w in TOKEN.findall(str(text or "").lower()):
        out.append(w)
        if re.match(r"[가-힣]", w) and len(w) > 2:
            out += [w[i:i + 2] for i in range(len(w) - 1)]
    return out


class BM25:
    def __init__(self, docs: list[str], k1: float = 1.4, b: float = 0.75):
        self.k1, self.b = k1, b
        self.post: dict[str, list[tuple[int, int]]] = defaultdict(list)
        self.len = []
        for i, d in enumerate(docs):
            tf = Counter(tokens(d))
            self.len.append(sum(tf.values()))
            for t, n in tf.items():
                self.post[t].append((i, n))
        self.n = len(docs)
        self.avg = (sum(self.len) / self.n) if self.n else 1

    def search(self, q: str, k: int = 10, allow: set[int] | None = None) -> list[tuple[int, float]]:
        sc: dict[int, float] = defaultdict(float)
        for t in set(tokens(q)):
            p = self.post.get(t)
            if not p:
                continue
            idf = math.log(1 + (self.n - len(p) + 0.5) / (len(p) + 0.5))
            for i, tf in p:
                if allow is not None and i not in allow:
                    continue
                sc[i] += idf * tf * (self.k1 + 1) / (tf + self.k1 * (1 - self.b + self.b * self.len[i] / self.avg))
        return sorted(sc.items(), key=lambda x: -x[1])[:k]


@dataclass
class Index:
    datasets: dict[str, dict] = field(default_factory=dict)
    edges: list[dict] = field(default_factory=list)
    contexts: list[dict] = field(default_factory=list)
    recipes: dict[str, dict] = field(default_factory=dict)
    codes: dict[str, dict] = field(default_factory=dict)     # 머리글만 (values 제외)
    gaps: list[dict] = field(default_factory=list)
    keys: dict[str, dict] = field(default_factory=dict)
    mappings: dict[str, dict] = field(default_factory=dict)
    ds_ids: list[str] = field(default_factory=list)
    ds_bm25: BM25 | None = None
    ctx_bm25: BM25 | None = None
    gap_bm25: BM25 | None = None
    catalog: pd.DataFrame | None = None
    cat_bm25: BM25 | None = None
    stamp: float = 0.0

    # ─────────── 검색
    def search_datasets(self, q: str, k: int = 8, tiers: tuple[str, ...] = ("verified", "candidate")) -> list[tuple[dict, float]]:
        allow = {i for i, d in enumerate(self.ds_ids) if self.datasets[d]["tier"] in tiers}
        return [(self.datasets[self.ds_ids[i]], s) for i, s in self.ds_bm25.search(q, k, allow)]

    def search_contexts(self, q: str, k: int = 3) -> list[tuple[dict, float]]:
        return [(self.contexts[i], s) for i, s in self.ctx_bm25.search(q, k)]

    def search_gaps(self, q: str, k: int = 2) -> list[tuple[dict, float]]:
        return [(self.gaps[i], s) for i, s in self.gap_bm25.search(q, k)] if self.gap_bm25 else []

    def search_catalog(self, q: str, k: int = 5, exclude: set[str] | None = None) -> list[tuple[dict, float]]:
        if self.cat_bm25 is None:
            return []
        exclude = exclude or set()
        out = []
        for i, s in self.cat_bm25.search(q, k * 4):
            r = self.catalog.iloc[i]
            if r["id"] in exclude or r["id"] in self.datasets:
                continue
            out.append((r.to_dict(), s))
            if len(out) >= k:
                break
        return out

    # ─────────── 조회
    def grounded_claims(self, dsid: str, kinds: tuple[str, ...] | None = None) -> list[dict]:
        d = self.datasets.get(dsid) or {}
        return [c for c in d.get("claims") or [] if (kinds is None or c["kind"] in kinds)
                and any(e["type"] in GROUNDED for e in c["evidence"])]

    def code_values(self, cid: str, q: str | None = None, limit: int = 50) -> list[dict]:
        c = self.codes.get(cid)
        if not c:
            return []
        if c.get("file"):
            t = pd.read_parquet(config.KNOWLEDGE / c["file"])
            vals = t.rename(columns=str).to_dict("records")
        else:
            full = next((x for x, _ in store.iter_raw("code") if x["id"] == cid), {})
            vals = full.get("values") or []
        if q:
            ql = q.lower()
            vals = [v for v in vals if ql in str(v.get("code", "")).lower() or ql in str(v.get("name", "")).lower()]
        return [{k: (str(v) if k == "valid" else v) for k, v in x.items()} for x in vals[:limit]]


def _ds_text(d: dict) -> str:
    cl = d.get("classification") or {}
    fields = " ".join(f.get("title") or "" for f in (d.get("schema") or {}).get("fields") or [])[:600]
    return " ".join(str(x) for x in [d["title"], d["title"], d.get("summary_user") or "", " ".join(d.get("synonyms") or []),
                                      cl.get("subsector_name") or "", cl.get("why") or "", d["sector"], d["agency"]["name"],
                                      (d.get("description_portal") or "")[:400], fields])


def _stamp() -> float:
    ps = [p for p in config.KNOWLEDGE.rglob("*.yaml")] + [config.KNOWLEDGE / "targets.json"]
    return max(p.stat().st_mtime for p in ps if p.exists())


def build() -> Index:
    ix = Index(stamp=_stamp())
    for d, _ in store.iter_raw("dataset"):
        ix.datasets[d["id"]] = d
    ix.ds_ids = list(ix.datasets)
    ix.ds_bm25 = BM25([_ds_text(ix.datasets[i]) for i in ix.ds_ids])
    ix.edges = store.load("edge")
    ix.contexts = store.load("context")
    ix.ctx_bm25 = BM25([" ".join(str(x) for x in (c["name"], c.get("question") or "", c.get("note") or "")) for c in ix.contexts])
    ix.recipes = {r["id"]: r for r in store.load("recipe")}
    ix.codes = {c["id"]: {k: v for k, v in c.items() if k != "values"} for c in store.load("code")}
    ix.gaps = [g for g in store.load("gap") if g.get("status") != "resolved"]
    ix.gap_bm25 = BM25([f"{g['name']} {g.get('question') or ''} {g['reason']}" for g in ix.gaps]) if ix.gaps else None
    ix.keys = {k["id"]: k for k in store.load("key")}
    ix.mappings = {m["id"]: m for m in store.load("mapping")}
    cat = config.PROCESSED / "catalog.parquet"
    if cat.exists():
        c = pd.read_parquet(cat, columns=["id", "title", "agency_name", "keywords", "description", "url", "api_type", "list_type"])
        cls = pd.read_parquet(config.PROCESSED / "class.parquet", columns=["id", "excluded_by", "sector"])
        c = c.merge(cls, on="id")
        ix.catalog = c.reset_index(drop=True)
        ix.cat_bm25 = BM25((c["title"].fillna("") + " " + c["title"].fillna("") + " " + c["keywords"].fillna("") + " "
                            + c["description"].fillna("").str[:200]).tolist())
    return ix


@lru_cache
def get() -> Index:
    if CACHE.exists():
        try:
            ix = pickle.loads(CACHE.read_bytes())
            if ix.stamp >= _stamp():
                return ix
        except Exception:  # noqa: BLE001 — 캐시가 깨졌으면 다시 만든다
            pass
    ix = build()
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_bytes(pickle.dumps(ix))
    return ix


def reload() -> Index:
    get.cache_clear()
    if CACHE.exists():
        CACHE.unlink()
    return get()
