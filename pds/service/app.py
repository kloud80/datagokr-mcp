"""서비스 API + 웹 채팅 — `python -m pds serve` (기본 http://127.0.0.1:8765).

  GET  /                     웹 채팅 — frontend/ 빌드(web/dist, BV 디자인 시스템)
  POST /api/chat             {messages:[{role,content}]} → {reply, plans, trace, usage}
  POST /api/chat/stream      같은 입력 → SSE: step(단계 진행) · plan(전략 먼저) · done(답) · error
  POST /api/plan             {goal, use_llm?} → 전략 응답 (KNOWLEDGE-SPEC §4)
  GET  /api/search?q=&tier=  검색 (verified · candidate · catalog)
  GET  /api/datasets         목록 — agency·sector·data_type·purpose·tier·channel·scope로 거른 전체를 offset·limit 쪽으로 (total·facets)
  GET  /api/datasets/{id}    Dataset 상세 + 설명서(markdown)
  GET  /api/codes            코드표 목록 · /api/codes/{id}?q= 코드 조회
  GET  /api/stats            지식 체계 규모
  GET  /api/reference        API 레퍼런스 (Swagger) · /mcp 원격 MCP (streamable HTTP)
  GET  /api/docs             Docs 화면용 집계 (사상·구성·관계·커버리지) · /api/docs/datasets 데이터별 표 한 쪽
  GET  /api/wiki/...         위키 — search · facets · datasets/{id} · keys · keys/{key} · codes · codes/{id} · proposals (제안 POST, 승인 POST …/{id}/review)
키는 서버의 .env에만 있다 — 응답·로그에 키를 싣지 않는다.
"""
from __future__ import annotations

import json
import os
import queue
import threading
import time
from contextlib import asynccontextmanager

import uuid

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from pds import config
from pds.service import index as sindex
from pds.strategy.plan import jsonable

@asynccontextmanager
async def lifespan(_app):
    sindex.get()  # 색인을 먼저 올려 첫 요청이 기다리지 않게
    import threading

    def _warm():  # Docs 집계·의미 검색 벡터도 미리 (첫 요청이 오래 걸리지 않게)
        from pds.service import docs, semantic
        docs.build()
        semantic.warm()
    threading.Thread(target=_warm, daemon=True).start()
    from pds.mcp.server import server as mcp_server
    async with mcp_server.session_manager.run():  # /mcp (원격 MCP) 세션 관리자 — 마운트한 앱의 lifespan은 따로 돌지 않는다
        yield


app = FastAPI(title="bigvalue-opendata", version="0.2.0", description="data.go.kr 공공데이터 전략 시스템 — 목표 → 데이터·조인·코드",
              lifespan=lifespan, docs_url="/api/reference", redoc_url=None, openapi_url="/api/openapi.json")  # 화면의 #/docs와 겹치지 않게
_CORS = [o.strip() for o in os.environ.get("PDS_CORS_ORIGINS", "").split(",") if o.strip()]
if _CORS:  # 화면은 같은 출처에서 서빙하므로 기본은 CORS를 열지 않는다 — 다른 출처에서 부를 때만 PDS_CORS_ORIGINS로 지정
    app.add_middleware(CORSMiddleware, allow_origins=_CORS, allow_methods=["GET", "POST"], allow_headers=["*"])
app.add_middleware(GZipMiddleware, minimum_size=2000)

# ── 화면 전용 API — 채팅·피드백·위키·Docs 집계·통계는 이 사이트 화면에서만 부른다 (외부 공개 API가 아니다)
#   화면(/)을 열 때 서명된 쿠키를 주고, 화면 전용 API는 그 쿠키 + 같은 출처 요청만 받는다. 명세(/api/reference)에도 싣지 않는다.
#   공개 API는 /api/plan · /api/search · /api/datasets(/{id}(/dossier)) · /api/codes(/{id}) 와 /mcp.
UI_ONLY = ("/api/chat", "/api/feedback", "/api/docs", "/api/stats", "/api/wiki/")
UI_COOKIE = "pds_ui"
UI_TTL = 7 * 24 * 3600


def _ui_secret() -> bytes:
    if os.environ.get("PDS_UI_SECRET"):
        return os.environ["PDS_UI_SECRET"].encode()
    f = config.ROOT / "data" / "cache" / "ui_secret"  # 재시작해도 열린 화면의 쿠키가 살아 있게 파일로 (git 밖)
    if not f.exists():
        import secrets
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(secrets.token_hex(32), encoding="utf-8")
    return f.read_text(encoding="utf-8").strip().encode()


def _ui_token(ts: int | None = None) -> str:
    import hashlib
    import hmac
    ts = ts or int(time.time())
    return f"{ts}.{hmac.new(_ui_secret(), str(ts).encode(), hashlib.sha256).hexdigest()[:32]}"


def _ui_ok(token: str | None) -> bool:
    import hmac
    try:
        ts = int((token or "").split(".", 1)[0])
    except ValueError:
        return False
    return 0 <= time.time() - ts <= UI_TTL and hmac.compare_digest(_ui_token(ts), token or "")


def _issue_ui_cookie(req: Request, res) -> None:
    https = req.url.scheme == "https" or req.headers.get("x-forwarded-proto") == "https"
    res.set_cookie(UI_COOKIE, _ui_token(), max_age=UI_TTL, httponly=True, samesite="strict", secure=https, path="/api")


def _same_origin(req: Request) -> bool:
    site = req.headers.get("sec-fetch-site")
    if site and site not in ("same-origin", "none"):
        return False
    origin = req.headers.get("origin")
    return not origin or origin.split("://", 1)[-1] == req.headers.get("host", "")


@app.middleware("http")
async def _ui_only_gate(req: Request, call_next):
    if req.url.path.startswith(UI_ONLY) and not (_ui_ok(req.cookies.get(UI_COOKIE)) and _same_origin(req)):
        return JSONResponse({"detail": "이 경로는 웹 화면 전용이다 — 공개 API는 /api/reference, MCP는 /mcp"}, status_code=403)
    return await call_next(req)
  # Docs 집계(수백 KB)를 압축해서
WEB = config.ROOT / "web"
DIST = WEB / "dist"  # cd frontend && npm run build
if (DIST / "assets").is_dir():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")


class ChatIn(BaseModel):
    messages: list[dict]
    session: str | None = None  # 브라우저가 만든 무작위 id (사용 기록용)


class FeedbackIn(BaseModel):
    turn_id: str
    rating: str  # up · down
    comment: str | None = None
    session: str | None = None


TRUST_PROXY = os.environ.get("PDS_TRUST_PROXY", "0") == "1"  # 리버스 프록시 뒤에서만 X-Forwarded-For를 믿는다 (아니면 호출마다 바꿔 제한을 피할 수 있다)
TRUSTED_PROXIES = {x.strip() for x in os.environ.get("PDS_TRUSTED_PROXIES", "").split(",") if x.strip()}  # 이 IP에서 온 연결만 XFF를 믿는다 (포트가 직접도 열려 있을 때)
PUBLIC_URL = os.environ.get("PDS_PUBLIC_URL", "").rstrip("/")  # 프록시 뒤 공개 주소 (예: https://labs.ai.bigvalue.co.kr) — 안내문의 주소


def _client_ip(xff: str | None, peer: str | None) -> str:
    if xff and (TRUST_PROXY or (peer and peer in TRUSTED_PROXIES)):
        return xff.split(",")[-1].strip()  # 프록시가 붙인 마지막 값 — 앞쪽은 클라이언트가 꾸밀 수 있다
    return peer or ""


def _ip(req: Request) -> str:
    return _client_ip(req.headers.get("x-forwarded-for"), req.client.host if req.client else None)


def _who(req: Request) -> str:
    from pds.service.usage import client_hash
    return client_hash(_ip(req), req.headers.get("user-agent"))


def _limit(req: Request) -> None:
    """LLM 비용이 드는 호출의 시간당 한도 (IP 기준) — pds/service/ratelimit.py."""
    from pds.service import ratelimit
    why = ratelimit.check(_ip(req))
    if why:
        raise HTTPException(429, why)


def _log_chat(out: dict, msgs: list[dict], turn_id: str, session: str | None, who: str, status: str = "ok", error: str | None = None) -> None:
    from pds.service.usage import record
    plans = out.get("plans") or []
    p = plans[-1] if plans else {}
    ids = [d["id"] for d in p.get("datasets") or []]
    record("chat", ga=("chat_answer", {"status": status, "plans": len(plans), "datasets": len(ids), "elapsed_s": out.get("elapsed_s")}),
           turn_id=turn_id, session=session, client_hash=who, question=msgs[-1]["content"] if msgs else None,
           reply=out.get("reply"), plan_ids={"datasets": ids, "excluded": [x["id"] for x in p.get("not_recommended") or []],
                                             "joins": [j["edge"] for j in p.get("joins") or []], "context": p.get("context")},
           trace=out.get("trace"), usage=out.get("usage"), elapsed_s=out.get("elapsed_s"), status=status, error=error,
           args={"turns": len(msgs)})


class PlanIn(BaseModel):
    goal: str
    use_llm: bool = True


@app.get("/", include_in_schema=False)
def home(req: Request):
    built = DIST / "index.html"
    if not built.exists():
        return PlainTextResponse("웹 화면이 빌드되지 않았습니다 — cd frontend && npm install && npm run build", status_code=503)
    res = FileResponse(built)
    _issue_ui_cookie(req, res)
    return res


@app.get("/robots.txt", include_in_schema=False, response_class=PlainTextResponse)
def robots(req: Request):
    """AI 에이전트의 웹 가져오기(robots.txt 확인)가 막히지 않게 — 화면·API·문서 모두 허용 (채팅·전략은 호출 제한이 따로 있다)."""
    base = PUBLIC_URL or str(req.base_url).rstrip("/")
    return f"User-agent: *\nAllow: /\n\n# 에이전트용 안내: {base}/llms.txt\n"


@app.get("/llms.txt", include_in_schema=False, response_class=PlainTextResponse)
def llms(req: Request):
    """에이전트가 처음 읽을 안내 — MCP 주소, REST 엔드포인트, 키 규약."""
    b = PUBLIC_URL or str(req.base_url).rstrip("/")
    return (f"# BigValue 공공데이터 (data.go.kr) — 목표에 맞는 공공데이터 조합·조인·코드\n\n"
            f"- MCP (Streamable HTTP): {b}/mcp — 서버 이름 bigvalue-opendata\n"
            f"- 전략: POST {b}/api/plan  body {{\"goal\": \"하고 싶은 일\", \"use_llm\": false}}\n"
            f"- 검색: GET {b}/api/search?q=검색어\n"
            f"- 데이터 상세: GET {b}/api/datasets/{{id}} · 설명서: GET {b}/api/datasets/{{id}}/dossier\n"
            f"- 코드표: GET {b}/api/codes · {b}/api/codes/{{id}}\n"
            f"- API 레퍼런스: {b}/api/reference · MCP 가이드: {b}/#/mcp\n\n"
            "전략 응답의 credentials.required가 true면 데이터를 받기 전에 사용자에게 키가 필요하다고 알리고, "
            "credentials.env_sample로 .env를 만들어(값은 비움) 사용자가 채우게 한다. 키를 지어내지 않는다.\n")


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    f = DIST / "favicon.ico"
    if not f.exists():
        raise HTTPException(404)
    return FileResponse(f, media_type="image/x-icon")


@app.post("/api/chat", include_in_schema=False)
def api_chat(body: ChatIn, req: Request):
    from pds.service import llm
    t0 = time.time()
    msgs = [m for m in body.messages if m.get("role") in ("user", "assistant") and isinstance(m.get("content"), str)][-20:]
    if not msgs or msgs[-1]["role"] != "user":
        raise HTTPException(400, "마지막 메시지는 user여야 한다")
    _limit(req)
    out = llm.chat(msgs)
    out["elapsed_s"] = round(time.time() - t0, 1)
    out["turn_id"] = uuid.uuid4().hex
    _log_chat(out, msgs, out["turn_id"], body.session, _who(req), status=out.get("stop") == "refusal" and "refusal" or "ok")
    return jsonable(out)


@app.post("/api/chat/stream", include_in_schema=False)
def api_chat_stream(body: ChatIn, req: Request):
    """채팅을 스레드에서 돌리며 진행 이벤트를 SSE로 흘린다 — 25초 동안 스피너 대신 단계와 전략 카드가 먼저 보이게."""
    from pds.service import llm
    msgs = [m for m in body.messages if m.get("role") in ("user", "assistant") and isinstance(m.get("content"), str)][-20:]
    if not msgs or msgs[-1]["role"] != "user":
        raise HTTPException(400, "마지막 메시지는 user여야 한다")
    _limit(req)
    q: queue.Queue = queue.Queue()
    t0 = time.time()
    turn_id, who = uuid.uuid4().hex, _who(req)

    def work():
        try:
            out = llm.chat(msgs, emit=q.put)
            out["elapsed_s"] = round(time.time() - t0, 1)
            out["turn_id"] = turn_id
            q.put({"type": "done", **out})
            _log_chat(out, msgs, turn_id, body.session, who, status=out.get("stop") == "refusal" and "refusal" or "ok")
        except Exception as e:  # noqa: BLE001 — 오류도 이벤트로 알린다
            q.put({"type": "error", "detail": f"{type(e).__name__}: {str(e)[:300]}"})
            _log_chat({"elapsed_s": round(time.time() - t0, 1)}, msgs, turn_id, body.session, who, status="error",
                      error=f"{type(e).__name__}: {str(e)[:300]}")

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


@app.post("/api/feedback", include_in_schema=False)
def api_feedback(body: FeedbackIn, req: Request):
    """답에 대한 👍/👎 — 개선용 기록 (pds_usage_log kind=feedback)."""
    from pds.service.usage import record
    if body.rating not in ("up", "down"):
        raise HTTPException(400, "rating은 up 또는 down")
    record("feedback", ga=("chat_feedback", {"rating": body.rating}), turn_id=body.turn_id, session=body.session,
           client_hash=_who(req), args={"rating": body.rating, "comment": (body.comment or "")[:1000]})
    return {"ok": True}


@app.post("/api/plan")
def api_plan(body: PlanIn, req: Request):
    from pds.service.usage import record
    from pds.strategy.plan import plan
    if len(body.goal.strip()) < 2:
        raise HTTPException(400, "goal이 비었다")
    _limit(req)
    t0 = time.time()
    p = plan(body.goal.strip(), use_llm=False)  # 공개 서버에선 LLM 설명을 끈다 (비용)
    record("plan", ga=("api_plan", {"datasets": len(p["datasets"])}), client_hash=_who(req), question=body.goal,
           plan_ids={"datasets": [d["id"] for d in p["datasets"]]}, elapsed_s=round(time.time() - t0, 2), status="ok")
    return p


@app.get("/api/search")
def api_search(q: str, tier: str = "verified", k: int = 10):
    ix = sindex.get()
    if tier == "catalog":
        return jsonable([{"id": r["id"], "title": r["title"], "agency": r["agency_name"], "tier": "catalog", "score": round(s, 2),
                      "portal_url": r.get("url")} for r, s in ix.search_catalog(q, k)])
    return [{"id": d["id"], "title": d["title"], "tier": d["tier"], "sector": d["sector"], "summary": d.get("summary_user"), "score": round(s, 2)}
            for d, s in ix.search_datasets(q, k, tiers=(tier,))]


@app.get("/api/datasets")
def api_datasets(agency: str | None = None, sector: str | None = None, data_type: str = "any", purpose: str | None = None,
                 tier: str = "verified", channel: str = "any", scope: str = "any", offset: int = 0, limit: int = 50, facets: bool = True):
    """조건에 맞는 데이터셋 목록 전체를 쪽 단위로 — total(전체 수)·items·next_offset·facets(부처·분야·유형별 건수)."""
    from pds.service.listing import list_datasets
    if tier not in ("verified", "candidate", "any", "catalog") or channel not in ("any", "portal", "external") or scope not in ("any", "national", "regional"):
        raise HTTPException(400, "tier는 verified·candidate·any·catalog, channel은 any·portal·external, scope는 any·national·regional")
    try:
        return jsonable(list_datasets(agency, sector, data_type, tier, purpose, channel, scope, max(offset, 0), min(max(limit, 1), 200), facets))
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


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


@app.get("/api/docs", include_in_schema=False)
def api_docs():
    """Docs 화면 — 지식 체계 규모·관계·커버리지 집계와 데이터별 표 (pds/service/docs.py)."""
    from pds.service import docs
    return docs.build()


@app.get("/api/docs/datasets", include_in_schema=False)
def api_docs_datasets(q: str = "", tier: str = "verified", sector: str = "", key: str = "", lv: str = "", sort: str = "rows",
                      page: int = 1, size: int = 25):
    """Docs 데이터 표 한 쪽 (거르기·정렬·쪽 나누기는 서버에서)."""
    from pds.service import docs
    return docs.table(q, tier, sector, key, lv, sort, page, size)


# ── 위키 (pds/service/wiki.py) — 데이터셋 yaml 탐색·관계 따라가기·수정 제안과 승인
class ProposalIn(BaseModel):
    dataset_id: str
    kind: str
    proposed_value: str
    target: str | None = None
    reason: str | None = None
    author: str | None = None


class ReviewIn(BaseModel):
    decision: str  # approve · reject
    note: str | None = None


def _db_call(fn, *a, **kw):
    if not config.DATABASE_URL:
        raise HTTPException(503, "제안 저장소(DB)가 설정되지 않았다")
    try:
        return fn(*a, **kw)
    except (ValueError, LookupError) as e:
        raise HTTPException(404 if isinstance(e, LookupError) else 400, str(e)) from e


def _reviewer(req: Request) -> str:
    from pds.service import wiki
    name = wiki.reviewer_of(req.headers.get("x-wiki-token"))
    if not name:
        raise HTTPException(403, "승인 권한이 없다 — 승인권자 토큰이 필요하다")
    return name


@app.get("/api/wiki/facets", include_in_schema=False)
def api_wiki_facets():
    from pds.service import wiki
    return {**wiki.facets(sindex.get()), "kinds": wiki.KINDS}


@app.get("/api/wiki/search", include_in_schema=False)
def api_wiki_search(q: str = "", sector: str = "", agency: str = "", grade: str = "", key: str = "", linked: bool = False,
                    sort: str = "relevance", page: int = 1, size: int = 30):
    from pds.service import wiki
    return jsonable(wiki.search(sindex.get(), q, sector, agency, grade, key, linked, sort, page, size))


@app.get("/api/wiki/datasets/{dsid}", include_in_schema=False)
def api_wiki_page(dsid: str):
    from pds.service import wiki
    out = wiki.page(sindex.get(), dsid)
    if not out:
        raise HTTPException(404, "지식 체계에 없는 id")
    return jsonable(out)


@app.get("/api/wiki/keys", include_in_schema=False)
def api_wiki_keys(q: str = ""):
    from pds.service import wiki
    return wiki.keys_list(sindex.get(), q)


@app.get("/api/wiki/codes", include_in_schema=False)
def api_wiki_codes(q: str = ""):
    from pds.service import wiki
    return wiki.codes_list(sindex.get(), q)


@app.get("/api/wiki/codes/{cid}", include_in_schema=False)
def api_wiki_code(cid: str, q: str | None = None, limit: int = 300):
    from pds.service import wiki
    out = wiki.code_page(sindex.get(), cid, q, min(max(limit, 10), 2000))
    if not out:
        raise HTTPException(404, "없는 코드표")
    return jsonable(out)


@app.get("/api/wiki/keys/{key}", include_in_schema=False)
def api_wiki_key(key: str, page: int = 1):
    from pds.service import wiki
    out = wiki.key_page(sindex.get(), key, page)
    if not out:
        raise HTTPException(404, "없는 키")
    return jsonable(out)


@app.get("/api/wiki/proposals", include_in_schema=False)
def api_wiki_proposals(dataset: str | None = None, status: str | None = None):
    from pds.service import wiki
    return {"rows": _db_call(wiki.proposals, dataset, status), "counts": _db_call(wiki.counts)}


@app.post("/api/wiki/proposals", include_in_schema=False)
def api_wiki_propose(body: ProposalIn, req: Request):
    from pds.service import wiki
    return _db_call(wiki.propose, sindex.get(), body.dataset_id, body.kind, body.proposed_value, body.target, body.reason,
                    body.author, _who(req))


@app.get("/api/wiki/me", include_in_schema=False)
def api_wiki_me(req: Request):
    from pds.service import wiki
    return {"reviewer": wiki.reviewer_of(req.headers.get("x-wiki-token"))}


@app.post("/api/wiki/proposals/{pid}/review", include_in_schema=False)
def api_wiki_review(pid: int, body: ReviewIn, req: Request):
    from pds.service import wiki
    return _db_call(wiki.review, sindex.get(), pid, body.decision, _reviewer(req), body.note)


@app.get("/api/stats", include_in_schema=False)
def api_stats():
    ix = sindex.get()
    from collections import Counter
    return {"datasets": dict(Counter(d["tier"] for d in ix.datasets.values())), "catalog": len(ix.catalog) if ix.catalog is not None else 0,
            "edges": dict(Counter(e["rel"] for e in ix.edges)), "measured_edges": sum(1 for e in ix.edges if e.get("verified")),
            "contexts": len(ix.contexts), "recipes": len(ix.recipes), "code_lists": len(ix.codes), "keys": len(ix.keys),
            "mappings": {m["id"]: m["match_rate"] for m in ix.mappings.values()}}


# ── 원격 MCP (streamable HTTP) — http://<서버>/mcp
#   상태 없는(stateless) JSON 응답. 도구는 지식 체계 읽기만 하고 사용자 키를 다루지 않는다.
#   LLM 비용이 드는 설명(explain=true)은 PDS_MCP_ALLOW_LLM=1일 때만 (기본 꺼짐).
#   모든 경로를 받는 마운트라 맨 끝에 둔다 — 위의 라우트가 먼저 처리된다.
async def _mcp_get(scope, send) -> None:
    """GET /mcp — 상태 없는 서버라 서버→클라이언트 스트림(SSE)을 열지 않는다. 열어 두면 클라이언트·프록시가 시간 초과까지 기다린다.
    MCP 클라이언트(Accept: text/event-stream)·DELETE에는 405(규약상 '스트림 없음'), 브라우저·웹 가져오기에는 안내문."""
    h = dict((k.decode().lower(), v.decode()) for k, v in scope.get("headers") or [])
    if scope["method"] == "DELETE" or "text/event-stream" in h.get("accept", ""):
        await send({"type": "http.response.start", "status": 405, "headers": [(b"allow", b"POST"), (b"content-length", b"0")]})
        await send({"type": "http.response.body", "body": b""})
        return
    base = PUBLIC_URL or ""
    body = ("BigValue 공공데이터 MCP 서버 (Streamable HTTP, 상태 없음)\n"
            f"이 주소({base}/mcp)에 JSON-RPC를 POST로 보낸다. 브라우저로 여는 주소가 아니다.\n"
            f"연결 방법: {base}/#/mcp · 에이전트 안내: {base}/llms.txt\n").encode("utf-8")
    await send({"type": "http.response.start", "status": 200,
                "headers": [(b"content-type", b"text/plain; charset=utf-8"), (b"content-length", str(len(body)).encode())]})
    await send({"type": "http.response.body", "body": b"" if scope["method"] == "HEAD" else body})


class _McpUsage:
    """원격 MCP 요청을 엿보아 tools/call을 기록한다 (본문을 읽은 뒤 그대로 다시 흘려보낸다)."""

    def __init__(self, inner):
        self.inner = inner

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope.get("path") == "/mcp/":  # 끝 '/'를 리다이렉트하지 않는다 — 프록시 뒤에서 http로 돌려보내 POST가 GET으로 바뀌던 것
            scope = dict(scope, path="/mcp", raw_path=b"/mcp")
        if scope["type"] == "http" and scope.get("path") == "/mcp" and scope.get("method") in ("GET", "HEAD", "DELETE"):
            return await _mcp_get(scope, send)
        if scope["type"] != "http" or scope.get("method") != "POST" or not scope.get("path", "").startswith("/mcp"):
            return await self.inner(scope, receive, send)
        chunks, more = [], True
        while more:
            msg = await receive()
            chunks.append(msg.get("body", b""))
            more = msg.get("more_body", False)
        body = b"".join(chunks)
        blocked = _mcp_limited(scope, body)
        if blocked:
            return await _send_json(send, blocked)
        sent = False

        async def replay():
            nonlocal sent
            if not sent:
                sent = True
                return {"type": "http.request", "body": body, "more_body": False}
            return await receive()

        t0 = time.time()
        await self.inner(scope, replay, send)
        try:
            msgs = json.loads(body or b"null")
            for m in msgs if isinstance(msgs, list) else [msgs]:
                if isinstance(m, dict) and m.get("method") == "tools/call":
                    from pds.service.usage import client_hash, record
                    h = dict((k.decode(), v.decode()) for k, v in scope.get("headers") or [])
                    ip = _scope_ip(scope)
                    who = client_hash(ip, h.get("user-agent"))
                    name = (m.get("params") or {}).get("name")
                    record("mcp", ga=("mcp_tool_call", {"tool": name}), session=who, client_hash=who, question=name,
                           args=(m.get("params") or {}).get("arguments"), elapsed_s=round(time.time() - t0, 2), status="ok")
        except Exception:  # noqa: BLE001 — 기록 실패가 응답을 막지 않게
            pass


def _scope_ip(scope) -> str:
    h = dict((k.decode(), v.decode()) for k, v in scope.get("headers") or [])
    return _client_ip(h.get("x-forwarded-for"), (scope.get("client") or ("",))[0])


def _mcp_limited(scope, body: bytes) -> dict | None:
    """전략 도구(주제 분해·재순위에 LLM을 쓴다)만 시간당 한도를 건다. 막히면 도구 오류(isError) 응답 본문."""
    try:
        m = json.loads(body or b"null")
    except ValueError:
        return None
    if not (isinstance(m, dict) and m.get("method") == "tools/call" and (m.get("params") or {}).get("name") == "plan_public_data_strategy"):
        return None
    from pds.service import ratelimit
    why = ratelimit.check(_scope_ip(scope))
    if not why:
        return None
    return {"jsonrpc": "2.0", "id": m.get("id"), "result": {"content": [{"type": "text", "text": why}], "isError": True}}


async def _send_json(send, obj: dict) -> None:
    data = json.dumps(obj, ensure_ascii=False).encode()
    await send({"type": "http.response.start", "status": 200,
                "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(data)).encode())]})
    await send({"type": "http.response.body", "body": data})


def _mount_mcp() -> None:
    from mcp.server.transport_security import TransportSecuritySettings

    from pds.mcp.server import server as mcp_server
    mcp_app = mcp_server.streamable_http_app(streamable_http_path="/mcp", stateless_http=True, json_response=True,
                                             transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False))
    app.mount("/", _McpUsage(mcp_app))


_mount_mcp()
