"""사용 기록 — 개선용 로그(서버에만)와 GA4 서버 이벤트.

기록: logs/usage/YYYY-MM-DD.jsonl (항상) + Postgres pds_usage_log (DB 설정이 있으면, sql/007). 둘 다 git 밖.
  · chat     웹 채팅 한 번 — 질문·답·전략 데이터 id·도구 순서·토큰·시간·오류
  · feedback 답에 대한 👍/👎·한 줄 의견
  · mcp      MCP 도구 호출 — 도구 이름·인자·시간 (결과 본문은 남기지 않는다)
  · plan     REST /api/plan 호출
IP는 소금 친 해시로만 (USAGE_SALT, 없으면 기본값). 키·계정 값은 남기지 않는다.

GA4 Measurement Protocol: .env의 GA4_MEASUREMENT_ID·GA4_API_SECRET가 있으면 같은 사건을 GA4 이벤트로도 보낸다
(mcp_tool_call · api_plan · chat_answer · chat_feedback). 없으면 조용히 건너뛴다.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import queue
import threading

from pds import config

LOG_DIR = config.ROOT / "logs" / "usage"
_Q: queue.Queue = queue.Queue(maxsize=10000)
_STARTED = False
_LOCK = threading.Lock()


def client_hash(ip: str | None, ua: str | None) -> str:
    salt = os.environ.get("USAGE_SALT", "datagokr-mcp")
    return hashlib.sha256(f"{salt}|{ip or ''}|{ua or ''}".encode()).hexdigest()[:16]


def _db_insert(recs: list[dict]) -> None:
    if not config.DATABASE_URL:
        return
    from pds import db
    cols = ["at", "kind", "turn_id", "session", "client_hash", "question", "reply", "args", "plan_ids", "trace", "usage",
            "elapsed_s", "status", "error"]
    with db.connect() as c:
        db.migrate(c)
        with c.cursor() as cur:
            cur.executemany(
                f"insert into pds_usage_log ({', '.join(cols)}) values ({', '.join(['%s'] * len(cols))})",
                [tuple(json.dumps(r.get(k), ensure_ascii=False, default=str) if k in ("args", "plan_ids", "trace", "usage") and r.get(k) is not None
                       else r.get(k) for k in cols) for r in recs])
        c.commit()


def _ga(event: str, params: dict, client: str) -> None:
    mid, secret = os.environ.get("GA4_MEASUREMENT_ID"), os.environ.get("GA4_API_SECRET")
    if not (mid and secret):
        return
    import httpx
    body = {"client_id": f"{int(client[:8], 16)}.{int(client[8:16], 16)}" if client else "0.0",
            "events": [{"name": event, "params": {k: v for k, v in params.items() if v is not None} | {"engagement_time_msec": 1}}]}
    httpx.post("https://www.google-analytics.com/mp/collect", params={"measurement_id": mid, "api_secret": secret}, json=body, timeout=10)


def _worker() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    while True:
        batch = [_Q.get()]
        while not _Q.empty() and len(batch) < 100:
            batch.append(_Q.get_nowait())
        day = dt.date.today().isoformat()
        with (LOG_DIR / f"{day}.jsonl").open("a", encoding="utf-8") as f:
            for r in batch:
                f.write(json.dumps({k: v for k, v in r.items() if not k.startswith("_")}, ensure_ascii=False, default=str) + "\n")
        try:
            _db_insert([{k: v for k, v in r.items() if not k.startswith("_")} for r in batch])
        except Exception as e:  # noqa: BLE001 — DB가 없거나 끊겨도 파일 기록은 남는다
            print(f"[usage] DB 기록 실패: {type(e).__name__}: {str(e)[:120]}", flush=True)
        for r in batch:
            ev = r.get("_ga")
            if ev:
                try:
                    _ga(ev[0], ev[1], r.get("client_hash") or "")
                except Exception:  # noqa: BLE001
                    pass


def record(kind: str, ga: tuple[str, dict] | None = None, **fields) -> None:
    """비동기 기록 — 요청을 기다리게 하지 않는다."""
    global _STARTED
    with _LOCK:
        if not _STARTED:
            threading.Thread(target=_worker, daemon=True, name="usage-log").start()
            _STARTED = True
    rec = {"at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "kind": kind, **fields}
    if ga:
        rec["_ga"] = ga
    try:
        _Q.put_nowait(rec)
    except queue.Full:
        pass
