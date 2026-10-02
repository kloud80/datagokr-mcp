"""서비스 API + 웹 채팅 — `python -m pds serve` (기본 http://127.0.0.1:8765).

  GET  /                     웹 채팅 — frontend/ 빌드(web/dist, BV 디자인 시스템)
  POST /api/chat             {messages:[{role,content}]} → {reply, plans, trace, usage}
  POST /api/chat/stream      같은 입력 → SSE: step(단계 진행) · plan(전략 먼저) · done(답) · error
  POST /api/plan             {goal, use_llm?} → 전략 응답 (KNOWLEDGE-SPEC §4)
  GET  /api/search?q=&tier=  검색 (verified · candidate · catalog)
  GET  /api/datasets/{id}    Dataset 상세 + 설명서(markdown)
  GET  /api/codes            코드표 목록 · /api/codes/{id}?q= 코드 조회
  GET  /api/stats            지식 체계 규모
키는 서버의 .env에만 있다 — 응답·로그에 키를 싣지 않는다.
"""
from __future__ import annotations

import json
import queue
import threading
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from pds import config
from pds.service import index as sindex
from pds.strategy.plan import jsonable

@asynccontextmanager
async def lifespan(_app):
    sindex.get()  # 색인을 먼저 올려 첫 요청이 기다리지 않게
    yield


app = FastAPI(title="datagokr-mcp", version="0.1.0", description="data.go.kr 공공데이터 전략 시스템 — 목표 → 데이터·조인·코드",
              lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
WEB = config.ROOT / "web"
DIST = WEB / "dist"  # cd frontend && npm run build
if (DIST / "assets").is_dir():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")


class ChatIn(BaseModel):
    messages: list[dict]


class PlanIn(BaseModel):
    goal: str
    use_llm: bool = True


@app.get("/")
def home():
    built = DIST / "index.html"
    if not built.exists():
        return PlainTextResponse("웹 화면이 빌드되지 않았습니다 — cd frontend && npm install && npm run build", status_code=503)
    return FileResponse(built)


@app.post("/api/chat")
def api_chat(body: ChatIn):
    from pds.service import llm
    t0 = time.time()
    msgs = [m for m in body.messages if m.get("role") in ("user", "assistant") and isinstance(m.get("content"), str)][-20:]
    if not msgs or msgs[-1]["role"] != "user":
        raise HTTPException(400, "마지막 메시지는 user여야 한다")
    out = llm.chat(msgs)
    out["elapsed_s"] = round(time.time() - t0, 1)
    return jsonable(out)


@app.post("/api/chat/stream")
def api_chat_stream(body: ChatIn):
    """채팅을 스레드에서 돌리며 진행 이벤트를 SSE로 흘린다 — 25초 동안 스피너 대신 단계와 전략 카드가 먼저 보이게."""
    from pds.service import llm
    msgs = [m for m in body.messages if m.get("role") in ("user", "assistant") and isinstance(m.get("content"), str)][-20:]
    if not msgs or msgs[-1]["role"] != "user":
        raise HTTPException(400, "마지막 메시지는 user여야 한다")
    q: queue.Queue = queue.Queue()
    t0 = time.time()

    def work():
        try:
            out = llm.chat(msgs, emit=q.put)
            out["elapsed_s"] = round(time.time() - t0, 1)
            q.put({"type": "done", **out})
        except Exception as e:  # noqa: BLE001 — 오류도 이벤트로 알린다
            q.put({"type": "error", "detail": f"{type(e).__name__}: {str(e)[:300]}"})

    threading.Thread(target=work, daemon=True).start()

    def gen():
        while True:
            try:
                ev = q.get(timeout=15)
            except queue.Empty:
                yield ": keep-alive\n\n"  # 프록시가 연결을 끊지 않게
                continue
            yield f"data: {json.dumps(jsonable(ev), ensure_ascii=False, default=str)}\n\n"
            if ev["type"] in ("done", "error"):
                return

    return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.post("/api/plan")
def api_plan(body: PlanIn):
    from pds.strategy.plan import plan
    return plan(body.goal, use_llm=body.use_llm)


@app.get("/api/search")
def api_search(q: str, tier: str = "verified", k: int = 10):
    ix = sindex.get()
    if tier == "catalog":
        return jsonable([{"id": r["id"], "title": r["title"], "agency": r["agency_name"], "tier": "catalog", "score": round(s, 2),
                      "portal_url": r.get("url")} for r, s in ix.search_catalog(q, k)])
    return [{"id": d["id"], "title": d["title"], "tier": d["tier"], "sector": d["sector"], "summary": d.get("summary_user"), "score": round(s, 2)}
            for d, s in ix.search_datasets(q, k, tiers=(tier,))]


@app.get("/api/datasets/{dsid}")
def api_dataset(dsid: str):
    ix = sindex.get()
    d = ix.datasets.get(dsid)
    if not d:
        raise HTTPException(404, "지식 체계에 없는 id (catalog 층은 /api/search?tier=catalog)")
    md = config.ROOT / "docs" / "dossiers" / f"{d.get('family') or dsid}.md"
    edges = [e for e in ix.edges if dsid in (e["src"], e["dst"])]
    return jsonable({"dataset": d, "edges": edges, "dossier_md": md.read_text(encoding="utf-8") if md.exists() else None})


@app.get("/api/datasets/{dsid}/dossier", response_class=PlainTextResponse)
def api_dossier(dsid: str):
    d = sindex.get().datasets.get(dsid)
    md = config.ROOT / "docs" / "dossiers" / f"{(d or {}).get('family') or dsid}.md"
    if not md.exists():
        raise HTTPException(404, "설명서 없음 — python -m pds.dossier.render")
    return md.read_text(encoding="utf-8")


@app.get("/api/codes")
def api_codes(q: str | None = None):
    ix = sindex.get()
    res = [{"id": c["id"], "name": c["name"], "completeness": c["completeness"], "rows": c["rows"], "key": c.get("key")} for c in ix.codes.values()]
    if q:
        res = [r for r in res if q.lower() in (r["id"] + r["name"]).lower()]
    return res


@app.get("/api/codes/{cid}")
def api_code(cid: str, q: str | None = None, limit: int = 50):
    ix = sindex.get()
    if cid not in ix.codes:
        raise HTTPException(404, "없는 코드표")
    return {"code_list": ix.codes[cid], "values": ix.code_values(cid, q, limit)}


@app.get("/api/stats")
def api_stats():
    ix = sindex.get()
    from collections import Counter
    return {"datasets": dict(Counter(d["tier"] for d in ix.datasets.values())), "catalog": len(ix.catalog) if ix.catalog is not None else 0,
            "edges": dict(Counter(e["rel"] for e in ix.edges)), "measured_edges": sum(1 for e in ix.edges if e.get("verified")),
            "contexts": len(ix.contexts), "recipes": len(ix.recipes), "code_lists": len(ix.codes), "keys": len(ix.keys),
            "mappings": {m["id"]: m["match_rate"] for m in ix.mappings.values()}}
