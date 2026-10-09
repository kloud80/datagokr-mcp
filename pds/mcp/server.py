"""MCP 서버 (KNOWLEDGE-SPEC §4, BUILD-PLAN Phase 4 `pds-strategy`) — `python -m pds mcp` (stdio) 또는 `--http`.

도구 (모두 읽기 전용 — 지식 체계만 읽고 사용자 키를 다루지 않는다)
  plan_public_data_strategy(goal, detail, include_code)  목표 → 전략. 기본은 요약판, detail=full이면 데이터 카드·후보 전체
  search_datasets(query, tier, limit, sector, agency, scope)  verified · candidate · catalog 검색 (필드 요약·실측 행 수 포함)
  get_dataset(id)                    상세 — 호출 방법·실측 필드(빈 값 비율·유니크·표본값)·검증 행 수·집계 단위·근거 claim·Edge
  list_code_lists(keyword) · lookup_code(code_list, q)   코드표
잘못 부르면(없는 id·코드표, 빈 목표) 오류(isError)로 돌려준다 — '결과 없음'(빈 배열)과 구분된다.
리소스  dataset://{id}  설명서 markdown · 프롬프트  plan_with_public_data
키 서버(Phase 6 pds-keys)와 분리 — 이 서버는 사용자 키를 보지 않는다.
"""
from __future__ import annotations

import json
import os
from typing import Annotated, Literal

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import Field

from pds import config
from pds.schema import GROUNDED  # 실측·법령·검토결정만 근거 — 포털 등록값(portal_meta)만 있는 진술은 grounded가 아니다
from pds.service import index as sindex

server = MCPServer(name="datagokr-mcp", title="공공데이터 전략 (data.go.kr)", version="0.2.0",
                   instructions="data.go.kr 공공데이터를 목표에 맞게 고르고 잇는 전략 도구. 조인은 선언·실측된 것만 돌려준다. "
                                "verified=검증(실제 호출로 행·필드를 실측), candidate=선정·미검증, catalog=포털 목록 단서(직접 확인). "
                                "먼저 plan_public_data_strategy로 조합을 받고, 데이터 한 건의 실측 필드는 get_dataset으로 본다.")

READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)


def _dump(x) -> str:
    return json.dumps(x, ensure_ascii=False, default=str)


# ─────────────────────────── 전략
@server.tool(title="공공데이터 전략 짜기", annotations=READ_ONLY, structured_output=False,
             description="목표(자연어)에 맞는 공공데이터 조합·조인 경로·파이프라인을 만든다. 기본(detail=summary)은 요약판 "
                         "(데이터·조인·주제별 상위 후보·근거·공백, 약 1~2만 자). include_code=true면 실행 코드, detail=full이면 데이터 카드·후보 전체. "
                         "join_counts는 데이터끼리 직접 조인과 코드표·지적도(허브) 정규화를 나눠 센다. gaps는 목표 중 채우지 못한 부분(단위 불일치 포함). "
                         "외부 사이트 가입이 따로 필요한 데이터는 external_signup으로 알린다.")
def plan_public_data_strategy(
    goal: Annotated[str, Field(description="하고 싶은 일을 자연어로. 지역·대상·시간 단위를 적을수록 정확하다 (예: 성수동 카페 개폐업을 월 단위로 보고 싶다)")],
    detail: Annotated[Literal["summary", "full"], Field(description="summary=요약판(기본), full=전략 응답 전체(데이터 카드·후보·코드 포함, 5~6만 자)")] = "summary",
    include_code: Annotated[bool, Field(description="summary에 실행 코드(파이썬)를 붙인다")] = False,
    explain: Annotated[bool, Field(description="LLM이 근거 claim을 인용해 이유를 쓴다 (공개 서버에서는 꺼져 있다)")] = False,
) -> str:
    from pds.service.llm import slim_plan
    from pds.strategy.plan import plan
    if len(goal.strip()) < 2:
        raise ToolError("goal이 비었다 — 하고 싶은 일을 한 문장으로 적어야 한다")
    if len(goal) > 2000:
        raise ToolError("goal이 너무 길다 (2,000자 이하)")
    allow = os.environ.get("PDS_MCP_ALLOW_LLM", "1" if os.environ.get("PDS_MCP_STDIO") else "0") == "1"  # 공개 서버에선 설명 LLM 차단
    p = plan(goal.strip(), use_llm=explain and allow)
    if detail == "full":
        return _dump(p)
    out = slim_plan(p)
    out["pipeline"] = p["pipeline"]
    out["knowledge_version"] = p.get("knowledge_version")
    out["more"] = "데이터 한 건의 실측 필드·호출 방법은 get_dataset(id), 전체 응답은 detail=full"
    if include_code:
        out["code"] = p.get("code")
    return _dump(out)


# ─────────────────────────── 검색
def _txt(v, n: int = 200) -> str | None:
    """포털 메타 칸 — 비었거나 NaN이면 None."""
    return None if v is None or v != v or str(v).strip() in ("", "nan", "None") else str(v)[:n]


def _field_brief(d: dict, k: int = 12) -> list[str]:
    return [f.get("title") or f.get("name") for f in ((d.get("schema") or {}).get("fields") or [])[:k]]


@server.tool(title="데이터셋 검색", annotations=READ_ONLY, structured_output=False,
             description="데이터셋을 키워드로 찾는다. tier=verified(검증)·candidate(선정·미검증)·catalog(포털 목록 단서). "
                         "query에 지역 이름이 없으면 전국 데이터를 앞에 둔다. scope=national이면 전국 데이터만, regional이면 지자체·지역판만. "
                         "결과에 기관·지역·필드 요약·실측 행 수·검증일이 붙는다.")
def search_datasets(
    query: Annotated[str, Field(description="찾을 말 (예: 음식점 인허가, 버스 도착, 아파트 실거래)")],
    tier: Annotated[Literal["verified", "candidate", "catalog"], Field(description="verified=검증, candidate=선정·미검증, catalog=포털 목록 단서")] = "verified",
    limit: Annotated[int, Field(ge=1, le=30, description="결과 개수 (1~30)")] = 10,
    sector: Annotated[str | None, Field(description="분야로 거르기 (부분 일치, 예: 교통, 부동산)")] = None,
    agency: Annotated[str | None, Field(description="제공 기관 이름으로 거르기 (부분 일치, 예: 국토교통부, 서울특별시)")] = None,
    scope: Annotated[Literal["any", "national", "regional"], Field(description="any=전체, national=전국 데이터만, regional=지자체·지역판만")] = "any",
) -> str:
    from pds.strategy import region as rgn
    if not query.strip():
        raise ToolError("query가 비었다")
    ix = sindex.get()

    def keep(d: dict, ag: str) -> bool:
        if agency and agency not in ag:
            return False
        if scope != "any":
            local = rgn.dataset_region(d) is not None
            if (scope == "national") == local:
                return False
        return True

    national_first = scope == "any" and not rgn.goal_regions(query)["sido"]  # 지역을 말하지 않았으면 전국 데이터를 앞에 — 지역판이 상위를 채우지 않게
    pool = limit * 6 if (sector or agency or scope != "any" or national_first) else limit
    res = []
    if tier == "catalog":
        for r, _ in ix.search_catalog(query, pool):
            if not keep({"agency_name": r.get("agency_name"), "title": r.get("title")}, r.get("agency_name") or ""):
                continue
            if sector and sector not in str(r.get("sector") or ""):
                continue
            res.append({"id": r["id"], "title": r["title"], "agency": r.get("agency_name"), "tier": "catalog",
                        "type": r.get("list_type") or r.get("api_type"), "sector": r.get("sector"),
                        "description": _txt(r.get("description")), "fields": _txt(r.get("output_cols")),
                        "note": "미검증 단서 — 포털에서 직접 확인 (get_dataset으로 포털 메타)"})
    else:
        for d, _ in ix.search_datasets(query, pool, tiers=(tier,)):
            ag = (d.get("agency") or {}).get("name") or ""
            if (sector and sector not in (d.get("sector") or "")) or not keep(d, ag):
                continue
            v = d.get("verification") or {}
            res.append({"id": d["id"], "title": d["title"], "tier": d["tier"], "sector": d["sector"], "agency": ag,
                        "region": rgn.dataset_region(d) or "전국", "summary": (d.get("summary_user") or "")[:200],
                        "fields": _field_brief(d), "grain": d.get("grain"),
                        "verified": {"rows": v.get("rows"), "probed_at": v.get("probed_at"), "verdict": v.get("verdict")} if v else None})
    if national_first:
        res.sort(key=lambda r: r.get("region") not in (None, "전국") or (r["tier"] == "catalog" and rgn.dataset_region(
            {"agency_name": r.get("agency"), "title": r.get("title")}) is not None))  # 안정 정렬 — 같은 무리 안에서는 검색 순위 유지
    return _dump(res[:limit])


# ─────────────────────────── 상세
def _field_view(f: dict) -> dict:
    st = f.get("stats") or {}
    out = {k: f.get(k) for k in ("name", "title", "type", "semantic_type", "code_list") if f.get(k) is not None}
    if f.get("null_rate") is not None:
        out["null_rate"] = f["null_rate"]
    if st.get("unique") is not None:
        out["unique"] = st["unique"]
    if any(k in st for k in ("min", "max")):
        out["range"] = [st.get("min"), st.get("max")]
    if f.get("sample_values"):
        out["samples"] = [str(s)[:40] for s in f["sample_values"][:3]]
    return out


@server.tool(title="데이터셋 상세", annotations=READ_ONLY, structured_output=False,
             description="데이터셋 한 건 상세 — 호출 방법·실측 필드(빈 값 비율 null_rate·유니크 수·값 범위·표본값)·검증 결과(받은 행 수·검증일·최신 데이터일)·"
                         "집계 단위(grain)·커버리지·조인 키(foreign_keys)·근거 claim·연결 Edge. catalog id는 포털 메타만 준다.")
def get_dataset(
    id: Annotated[str, Field(description="데이터셋 id (포털 목록키, 예: 15154916) — search_datasets·전략 응답의 id")],  # noqa: A002 — MCP 인자 이름
    max_fields: Annotated[int, Field(ge=1, le=200, description="필드를 몇 개까지 보일지")] = 60,
) -> str:
    from pds.strategy.plan import jsonable
    ix = sindex.get()
    dsid = id.strip()
    d = ix.datasets.get(dsid)
    if not d:
        r = ix.catalog[ix.catalog["id"] == dsid] if ix.catalog is not None else None
        if r is not None and len(r):
            return _dump(jsonable({"tier": "catalog", **r.iloc[0].to_dict(), "note": "지식 체계 밖(미검증) — 포털 메타만"}))
        raise ToolError(f"없는 id: {dsid} — search_datasets로 id를 먼저 찾는다")
    sch = d.get("schema") or {}
    fields = sch.get("fields") or []
    v = d.get("verification") or {}
    out = {k: d.get(k) for k in ("id", "tier", "title", "sector", "agency", "kind", "channel", "status", "portal_url", "cycle",
                                 "coverage", "grain", "summary_user", "limits")}
    out["verification"] = {k: v.get(k) for k in ("verdict", "probed_at", "rows", "ops_ok", "latest", "lag_days", "latency_ms")} if v else None
    out["services"] = [{k: s.get(k) for k in ("op", "endpoint", "params", "approval")} for s in (d.get("services") or [])[:4]]
    out["fields_total"] = len(fields)
    out["fields"] = [_field_view(f) for f in fields[:max_fields]]
    out["foreign_keys"] = [{"fields": fk.get("fields"), "key": (fk.get("reference") or {}).get("key"), "evidence": fk.get("evidence")}
                           for fk in sch.get("foreign_keys") or []]
    out["claims"] = [{"kind": c["kind"], "value": c["value"][:240], "grounded": any(e["type"] in GROUNDED for e in c["evidence"])}
                     for c in d.get("claims") or []]
    out["edges"] = [{"rel": e["rel"], "other": e["dst"] if e["src"] == dsid else e["src"], "on": e.get("on"),
                     "match_rate": (e.get("verified") or {}).get("match_rate")} for e in ix.edges if dsid in (e["src"], e["dst"])][:12]
    return _dump(out)


# ─────────────────────────── 코드표
@server.tool(title="코드표 찾기", annotations=READ_ONLY, structured_output=False,
             description="코드표 찾기 (지목·용도지역·법정동·기관코드·국가·통화·항구·HS·NCS …). 결과의 id를 lookup_code의 code_list로 쓴다.")
def list_code_lists(keyword: Annotated[str, Field(description="코드표 이름이나 별칭의 일부 (예: 법정동, 지목, 통화)")]) -> str:
    kw = keyword.strip().lower()
    if not kw:
        raise ToolError("keyword가 비었다")
    ix = sindex.get()
    res = [{"id": c["id"], "name": c["name"], "completeness": c["completeness"], "rows": c["rows"], "aliases": c.get("aliases", [])[:3]}
           for c in ix.codes.values() if kw in c["name"].lower() or kw in c["id"] or any(kw in str(a).lower() for a in c.get("aliases", []))]
    return _dump(res[:10])


@server.tool(title="코드값 조회", annotations=READ_ONLY, structured_output=False,
             description="코드표에서 코드값 또는 이름으로 찾기 (예: code_list=bjd_cd, q=성수동). 없는 코드표는 오류.")
def lookup_code(
    code_list: Annotated[str, Field(description="코드표 id — list_code_lists 결과의 id (예: bjd_cd)")],
    q: Annotated[str, Field(description="찾을 코드값 또는 이름의 일부")],
) -> str:
    ix = sindex.get()
    if code_list not in ix.codes:
        raise ToolError(f"없는 코드표: {code_list} — list_code_lists로 id를 찾는다")
    if not q.strip():
        raise ToolError("q가 비었다")
    return _dump(ix.code_values(code_list, q.strip(), 20))


# ─────────────────────────── 리소스 · 프롬프트
@server.resource("dataset://{dsid}", name="dataset", description="데이터셋 설명서 (markdown)", mime_type="text/markdown")
def dataset_resource(dsid: str) -> str:
    d = sindex.get().datasets.get(dsid) or {}
    md = config.ROOT / "docs" / "dossiers" / f"{d.get('family') or dsid}.md"
    return md.read_text(encoding="utf-8") if md.exists() else _dump(d)


@server.prompt(name="plan_with_public_data", title="공공데이터로 목표 풀기",
               description="목표를 받아 전략 → 상세 확인 → 정직한 답 순서로 도구를 쓰게 하는 지침")
def plan_with_public_data(goal: str) -> str:
    return (f"목표: {goal}\n\n"
            "1. plan_public_data_strategy로 조합을 받는다.\n"
            "2. 핵심 데이터는 get_dataset으로 실측 필드(빈 값 비율·표본값)와 검증 행 수·검증일을 확인한다.\n"
            "3. 답에는 gaps(채우지 못한 부분·단위 불일치)와 join_counts(데이터끼리 직접 조인 수와 코드표 정규화 수)를 그대로 밝힌다.\n"
            "4. candidate·catalog는 미검증 단서라고 말하고, external_signup이 있으면 가입 절차를 알린다.")


def main(http: bool = False, port: int = 8766) -> None:
    if not http:
        os.environ.setdefault("PDS_MCP_STDIO", "1")  # 내 컴퓨터(stdio)에서는 explain 허용
    sindex.get()
    if http:
        server.run(transport="streamable-http", port=port)
    else:
        server.run()


if __name__ == "__main__":
    import sys
    main(http="--http" in sys.argv)
