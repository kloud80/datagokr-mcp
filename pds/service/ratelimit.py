"""호출 제한 — LLM 비용이 드는 호출(채팅, 전략: 주제 분해·재순위)을 클라이언트별·전체 시간당 횟수로 막는다.

메모리 안 슬라이딩 창(1시간)이라 서버를 다시 띄우면 비워진다. 한도는 환경변수로:
  PDS_RATE_PER_HOUR (클라이언트별, 기본 60) · PDS_RATE_GLOBAL_PER_HOUR (전체, 기본 2000) · 0이면 제한 없음.
"""
from __future__ import annotations

import os
import threading
import time
from collections import defaultdict, deque

WINDOW = 3600.0
_lock = threading.Lock()
_hits: dict[str, deque] = defaultdict(deque)
_all: deque = deque()


def _limit(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


def check(client: str) -> str | None:
    """허용이면 None을 돌려주고 기록한다. 막히면 사유 문장."""
    per, glob = _limit("PDS_RATE_PER_HOUR", 60), _limit("PDS_RATE_GLOBAL_PER_HOUR", 2000)
    now = time.time()
    with _lock:
        q = _hits[client]
        for d in (q, _all):
            while d and now - d[0] > WINDOW:
                d.popleft()
        if per and len(q) >= per:
            return f"호출 한도 초과 — 한 시간에 {per}회까지 ({int(WINDOW - (now - q[0])) // 60 + 1}분 뒤 다시)"
        if glob and len(_all) >= glob:
            return "서버 전체 호출 한도 초과 — 잠시 뒤 다시"
        q.append(now)
        _all.append(now)
        if len(_hits) > 50_000:  # 오래된 클라이언트 정리
            for k in [k for k, v in _hits.items() if not v]:
                del _hits[k]
    return None
