"""우리 답 수집 (1천 문항) — 지금 쓰는 채팅(멀티헤드 전략 포함)을 그대로 부른다 → ours/{id}.json
evals/portal_ai/run_ours.py의 one()을 그대로 쓰고(채팅이 부른 첫 전략을 기록), 질문·출력 위치만 바꾼다.
  python -X utf8 -m evals.portal_1k.run_ours [--workers 4]
"""
from __future__ import annotations

import argparse
import pathlib
from concurrent.futures import ThreadPoolExecutor

import yaml

from evals.portal_ai import run_ours as base

ROOT = pathlib.Path(__file__).resolve().parent

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=4)
    a = ap.parse_args()
    base.OUT = ROOT / "ours"
    base.CHAT_ONLY = True
    base.OUT.mkdir(exist_ok=True)
    items = yaml.safe_load((ROOT / "questions.yaml").read_text(encoding="utf-8"))
    from pds.service import index
    index.get()
    with ThreadPoolExecutor(a.workers) as ex:
        for msg in ex.map(base.one, items):
            print(msg, flush=True)
