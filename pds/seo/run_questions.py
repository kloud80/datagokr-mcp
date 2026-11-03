"""롱테일 질문에 답을 받아 둔다 — 지금 쓰는 채팅(멀티헤드 전략 포함)을 그대로 불러 seo/answers/{id}.json (공개 페이지 /data/s/{id}의 재료).

evals/portal_ai/run_ours.py의 one()을 그대로 쓴다 (이미 있는 파일은 건너뛴다 — 중단돼도 이어서).
  python -X utf8 -m pds.seo.run_questions [admin_1 …] [--workers 3]
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor

import yaml

from pds import config

Q = config.ROOT / "pds" / "seo" / "questions"
OUT = config.ROOT / "seo" / "answers"


def items(names: list[str] | None = None) -> list[dict]:
    out = []
    for f in sorted(Q.glob("*.yaml")):
        if not names or f.stem in names:
            out += [{**x, "set": f.stem} for x in yaml.safe_load(f.read_text(encoding="utf-8")) or []]
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("sets", nargs="*")
    ap.add_argument("--workers", type=int, default=3)
    a = ap.parse_args()
    from evals.portal_ai import run_ours as base
    base.OUT = OUT
    base.CHAT_ONLY = True
    OUT.mkdir(parents=True, exist_ok=True)
    from pds.service import index
    index.get()
    with ThreadPoolExecutor(a.workers) as ex:
        for msg in ex.map(base.one, items(a.sets or None)):
            print(msg, flush=True)
