"""의미 검색 — 질문과 데이터 설명의 '뜻'이 가까운지 (BM25 글자 겹침을 보완).

"법인 상태 추정" ↔ "사업자 휴폐업 조회"처럼 글자는 달라도 뜻이 같은 데이터를 찾는다.
모델: intfloat/multilingual-e5-large (fastembed·ONNX·CPU, 한국어 포함 다국어). PDS_EMBED_MODEL로 바꿀 수 있다.
대상: verified·candidate 층 (카탈로그 9.6만은 CPU로 다 임베딩하기엔 커서 BM25만).
캐시: data/processed/embed_<모델>.npz — 데이터별 설명 글의 해시가 바뀐 것만 다시 계산한다.
fastembed가 없거나 PDS_EMBED=0이면 available()이 False — 플래너는 BM25만으로 돈다 (깃헙에서 받은 사람도 그대로 실행).
"""
from __future__ import annotations

import hashlib
import os
import threading
from functools import lru_cache

import numpy as np

from pds import config

MODEL = os.environ.get("PDS_EMBED_MODEL") or "intfloat/multilingual-e5-large"
_LOCK = threading.Lock()


def available() -> bool:
    if os.environ.get("PDS_EMBED", "1") == "0":
        return False
    try:
        import fastembed  # noqa: F401
    except ImportError:
        return False
    return True


def _cache_path():
    return config.PROCESSED / f"embed_{MODEL.replace('/', '__')}.npz"


def doc_text(d: dict) -> str:
    cl = d.get("classification") or {}
    parts = [d["title"], d.get("summary_user") or "", cl.get("subsector_name") or "", cl.get("why") or "",
             " ".join(d.get("synonyms") or []), (d.get("description_portal") or "")[:300]]
    return " ".join(str(x) for x in parts if x)[:600]


@lru_cache
def _model():
    from fastembed import TextEmbedding
    return TextEmbedding(MODEL, cache_dir=str(config.ROOT / "data" / "models"))


def _embed(texts: list[str]) -> np.ndarray:
    v = np.array(list(_model().embed(texts, batch_size=16)), dtype=np.float32)
    return v / np.linalg.norm(v, axis=1, keepdims=True)


@lru_cache
def _vectors(stamp: float) -> tuple[list[str], np.ndarray]:
    """verified·candidate 데이터의 문서 벡터 — 바뀐 것만 다시 계산해 캐시에 쓴다."""
    from pds.service import index as sindex
    ix = sindex.get()
    ids = [i for i, d in ix.datasets.items() if d["tier"] in ("verified", "candidate")]
    texts = {i: "passage: " + doc_text(ix.datasets[i]) for i in ids}
    hashes = {i: hashlib.sha1(t.encode()).hexdigest()[:16] for i, t in texts.items()}
    old: dict[str, tuple[str, np.ndarray]] = {}
    p = _cache_path()
    if p.exists():
        z = np.load(p, allow_pickle=False)
        old = {i: (h, v) for i, h, v in zip(z["ids"].tolist(), z["hashes"].tolist(), z["vecs"])}
    todo = [i for i in ids if i not in old or old[i][0] != hashes[i]]
    p.parent.mkdir(parents=True, exist_ok=True)
    for k in range(0, len(todo), 200):  # 200건마다 저장 — 처음 계산(CPU 수십 분)이 끊겨도 이어서
        part = todo[k:k + 200]
        for i, v in zip(part, _embed([texts[i] for i in part])):
            old[i] = (hashes[i], v)
        keep = [i for i in old]
        np.savez(p, ids=np.array(keep), hashes=np.array([old[i][0] for i in keep]), vecs=np.stack([old[i][1] for i in keep]))
        print(f"[semantic] 벡터 {min(k + 200, len(todo))}/{len(todo)}", flush=True)
    vecs = np.stack([old[i][1] for i in ids]) if ids else np.zeros((0, 1), np.float32)
    return ids, vecs


def warm() -> None:
    from pds.service import index as sindex
    if available():
        with _LOCK:
            _vectors(sindex.get().stamp)
            _model()  # 질문 임베딩용 모델도 올려 둔다


def search(q: str, k: int = 60, tiers: tuple[str, ...] = ("verified",)) -> list[tuple[dict, float]]:
    """(데이터, 코사인 유사도) — 높은 순. 쓸 수 없으면 빈 목록."""
    return search_floor(q, k, tiers)[0]


def search_floor(q: str, k: int = 60, tiers: tuple[str, ...] = ("verified",)) -> tuple[list[tuple[dict, float]], float]:
    """검색 결과와 그 질문의 바닥 유사도(전체 중앙값) — e5 코사인은 0.75~0.9에 몰려 있어 질문마다 바닥을 빼고 본다."""
    if not available():
        return [], 0.0
    from pds.service import index as sindex
    ix = sindex.get()
    with _LOCK:
        ids, vecs = _vectors(ix.stamp)
        qv = _embed(["query: " + q])[0]
    sims = vecs @ qv
    floor = float(np.median(sims))
    out = []
    for n in np.argsort(-sims):
        d = ix.datasets[ids[n]]
        if d["tier"] in tiers:
            out.append((d, float(sims[n])))
            if len(out) >= k:
                break
    return out, floor
