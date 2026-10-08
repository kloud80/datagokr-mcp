"""MCP 서버 (KNOWLEDGE-SPEC §4, BUILD-PLAN Phase 4 `pds-strategy`) — `python -m pds mcp` (stdio) 또는 `--http`.

도구
  plan_public_data_strategy(goal)  목표 → 전략 응답 (datasets·joins·pipeline·code·candidates·unverified_leads·gaps·external_signup — 외부 사이트 가입이 따로 필요한 데이터)
  search_datasets(query, tier)     verified · candidate · catalog 검색
  get_dataset(id)                   상세 (호출 방법·필드·근거 claim·Edge)
  list_code_lists(keyword)          코드표 찾기 · lookup_code(code_list, q) 코드 조회
리소스  dataset://{id}  설명서 markdown
키 서버(Phase 6 pds-keys)와 분리 — 이 서버는 사용자 키를 보지 않는다.
"""
from __future__ import annotations

import json

from mcp.server.mcpserver import MCPServer

from pds import config
from pds.service import index as sindex
from pds.service.llm import run_tool

server = MCPServer(name="datagokr-mcp", title="공공데이터 전략 (data.go.kr)", version="0.1.0",
                   instructions="data.go.kr 공공데이터를 목표에 맞게 고르고 잇는 전략 도구. 조인은 선언·실측된 것만 돌려준다. "
                                "verified=검증, candidate=선정·미검증, catalog=단서(직접 확인).")


@server.tool(description="목표(자연어)에 맞는 공공데이터 조합·조인 경로·파이프라인·실행 코드를 만든다. 외부 사이트 가입이 따로 필요한 데이터는 external_signup(사이트·가입 절차)과 각 데이터 access.signup으로 알린다. explain=true면 LLM이 근거 claim을 인용해 이유를 쓴다.")
def plan_public_data_strategy(goal: str, explain: bool = False) -> str:
    import os

    from pds.strategy.plan import plan
    allow = os.environ.get("PDS_MCP_ALLOW_LLM", "1" if os.environ.get("PDS_MCP_STDIO") else "0") == "1"  # 공개 서버에선 LLM 비용 차단
    return json.dumps(plan(goal, use_llm=explain and allow), ensure_ascii=False, default=str)


@server.tool(description="데이터셋 검색. tier: verified | candidate | catalog")
def search_datasets(query: str, tier: str = "verified") -> str:
    return run_tool("search_datasets", {"query": query, "tier": tier}, [])


@server.tool(description="데이터셋 한 건 상세 — 호출 방법·필드·조인 키·근거 claim·연결 Edge")
def get_dataset(id: str) -> str:  # noqa: A002 — MCP 인자 이름
    return run_tool("get_dataset", {"id": id}, [])


@server.tool(description="코드표 찾기 (지목·용도지역·법정동·기관코드·국가·통화·항구·HS·NCS …)")
def list_code_lists(keyword: str) -> str:
    return run_tool("find_code_list", {"keyword": keyword}, [])


@server.tool(description="코드표에서 코드값 또는 이름으로 찾기 (예: code_list=bjd_cd, q=성수동)")
def lookup_code(code_list: str, q: str) -> str:
    return run_tool("lookup_code", {"code_list": code_list, "q": q}, [])


@server.resource("dataset://{dsid}", name="dataset", description="데이터셋 설명서 (markdown)", mime_type="text/markdown")
def dataset_resource(dsid: str) -> str:
    d = sindex.get().datasets.get(dsid) or {}
    md = config.ROOT / "docs" / "dossiers" / f"{d.get('family') or dsid}.md"
    return md.read_text(encoding="utf-8") if md.exists() else json.dumps(d, ensure_ascii=False, default=str)


def main(http: bool = False, port: int = 8766) -> None:
    import os
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
