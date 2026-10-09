import { useState } from 'react'
import { AgentAlert, AgentChip, AgentTable, AgentTabs } from '@bv-ds/ui'
import { Credit } from './Credit'

// MCP 가이드 — 원격(이 서버의 /mcp)과 내 컴퓨터(stdio) 두 가지로 붙는 법, 도구, 인증 정책.

const ORIGIN = typeof window !== 'undefined' ? window.location.origin : 'http://bv.bigvalue.co.kr:9001'
const MCP_URL = `${ORIGIN}/mcp`

function Code({ children, lang }: { children: string; lang?: string }) {
  const [ok, setOk] = useState(false)
  return (
    <div className="doc-code">
      <div className="doc-code-bar"><span>{lang}</span>
        <button type="button" onClick={() => { void navigator.clipboard?.writeText(children).then(() => { setOk(true); setTimeout(() => setOk(false), 1200) }) }}>{ok ? '복사됨' : '복사'}</button>
      </div>
      <pre>{children}</pre>
    </div>
  )
}

export function Mcp() {
  return (
    <div className="doc-page">
      <header className="doc-top">
        <a className="doc-back" href="#/">← 공공데이터 전략 도우미</a>
        <h1 className="doc-title">MCP</h1>
        <a className="doc-small" href="#/docs">Docs</a>
        <a className="doc-small" href="#/wiki">Wiki</a>
      </header>
      <div className="doc-single">
        <section className="doc-section">
          <h2 className="doc-h2"><span className="doc-num">M</span>MCP로 쓰기</h2>
          <p className="doc-lead">
            이 시스템의 지식(검증된 공공데이터·선언된 조인·코드표)을 Claude·Cursor 같은 AI 도구에서 직접 쓸 수 있습니다.
            AI가 목표를 받으면 <b>plan_public_data_strategy</b>로 데이터 조합·조인 경로를 받아 답하고,
            핵심 데이터는 <b>get_dataset</b>으로 실측 필드(빈 값 비율·유니크 수·표본값)와 검증 행 수·검증일을 확인합니다.
            조인은 선언·실측된 것만 돌려주고, 채우지 못한 부분(공백·시간 단위 불일치)은 gaps로 밝힙니다.
          </p>
          <div className="doc-cards-stack">
            <div className="doc-card"><AgentChip variant="live">원격</AgentChip><b className="doc-mono">{MCP_URL}</b><p>Streamable HTTP · 상태 없음 · JSON 응답. 설치 없이 주소만 넣으면 됩니다.</p></div>
            <div className="doc-card"><AgentChip variant="primary">내 컴퓨터</AgentChip><b className="doc-mono">python -m pds mcp</b><p>저장소를 받아 stdio로 실행. 설명(explain)까지 쓰려면 이쪽 + 내 Claude 키.</p></div>
            <div className="doc-card"><AgentChip variant="neutral">REST API</AgentChip><b className="doc-mono">{ORIGIN}/api/…</b><p>MCP가 아닌 일반 HTTP. 레퍼런스: <a href="/api/reference" target="_blank" rel="noreferrer">/api/reference</a></p></div>
          </div>
        </section>

        <section className="doc-section">
          <h2 className="doc-h2"><span className="doc-num">1</span>연결하기</h2>
          <AgentTabs label="클라이언트별 설정" items={[
            { id: 'cc', label: 'Claude Code', content: <Code lang="bash">{`claude mcp add --transport http datagokr ${MCP_URL}
# 확인
claude mcp list`}</Code> },
            { id: 'desktop', label: 'Claude Desktop', content: <>
              <p className="doc-p">Claude Desktop 설정 파일(<code className="pds-code">claude_desktop_config.json</code>)에 넣습니다. 원격 주소는 <code className="pds-code">mcp-remote</code>로 잇습니다(Node 필요).</p>
              <Code lang="json">{`{
  "mcpServers": {
    "datagokr": {
      "command": "npx",
      "args": ["-y", "mcp-remote", "${MCP_URL}", "--allow-http"]
    }
  }
}`}</Code></> },
            { id: 'cursor', label: 'Cursor · VS Code', content: <Code lang="json">{`// Cursor: ~/.cursor/mcp.json  ·  VS Code: .vscode/mcp.json ("servers" 키)
{
  "mcpServers": {
    "datagokr": { "url": "${MCP_URL}" }
  }
}`}</Code> },
            { id: 'local', label: '내 컴퓨터(stdio)', content: <Code lang="bash">{`git clone https://github.com/kloud80/datagokr-mcp && cd datagokr-mcp
python -m venv .venv && .venv/Scripts/activate   # macOS·Linux: source .venv/bin/activate
pip install -e . && python -m pds setup --no-db
# Claude Desktop 설정
{ "mcpServers": { "datagokr": { "command": "<경로>/.venv/Scripts/python.exe",
    "args": ["-m", "pds", "mcp"], "cwd": "<경로>/datagokr-mcp" } } }`}</Code> },
            { id: 'curl', label: 'curl로 시험', content: <Code lang="bash">{`curl -s -X POST ${MCP_URL} \\
  -H 'content-type: application/json' -H 'accept: application/json, text/event-stream' \\
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"search_datasets","arguments":{"query":"응급실","tier":"verified","limit":5,"scope":"national"}}}'`}</Code> },
          ]} />
        </section>

        <section className="doc-section">
          <h2 className="doc-h2"><span className="doc-num">2</span>도구</h2>
          <AgentTable caption="MCP 도구" columns={[{ key: 'n', label: '도구' }, { key: 'a', label: '인자' }, { key: 'd', label: '하는 일' }]}
            rows={[
              { key: 1, n: <code className="pds-code">plan_public_data_strategy</code>, a: 'goal, detail=summary|full, include_code=false', d: '목표 → 검증 데이터·역할·근거, 선언된 조인(실측률), 파이프라인, 주제별 후보, 공백, 미검증 단서. 기본은 요약판(약 2만 자), 실행 코드는 include_code, 전체는 detail=full. join_counts는 데이터끼리 직접 조인과 코드표·지적도 정규화를 나눠 셉니다' },
              { key: 2, n: <code className="pds-code">search_datasets</code>, a: 'query, tier, limit=10, sector, agency, scope=any|national|regional', d: '세 층 검색(verified·candidate·catalog). 기관·필드 요약·실측 행 수·검증일 포함. 검색어에 지역이 없으면 전국 데이터를 앞에 두고, scope=national이면 지자체·지역판을 뺍니다' },
              { key: 3, n: <code className="pds-code">get_dataset</code>, a: 'id, max_fields=60', d: '호출 방법, 실측 필드(빈 값 비율·유니크 수·값 범위·표본값), 검증 결과(행 수·검증일·최신 데이터일), 집계 단위(grain), 조인 키, 근거 claim, 연결된 Edge' },
              { key: 4, n: <code className="pds-code">list_code_lists</code>, a: 'keyword', d: '코드표 찾기 (지목·용도지역·법정동·기관코드·HS…)' },
              { key: 5, n: <code className="pds-code">lookup_code</code>, a: 'code_list, q', d: '코드값 ↔ 이름 (예: bjd_cd, 성수동)' },
            ]} />
          <p className="doc-p">리소스 <code className="pds-code">dataset://{'{id}'}</code> 는 데이터 설명서(Markdown), 프롬프트 <code className="pds-code">plan_with_public_data</code>는 전략 → 상세 확인 → 공백까지 밝히는 답의 순서를 안내합니다.
            도구는 모두 읽기 전용(readOnlyHint)으로 표시되고, 없는 id·코드표나 빈 목표처럼 잘못 부르면 빈 결과가 아니라 <b>오류(isError)</b>로 돌려줍니다.</p>
          <h3 className="doc-h3">이렇게 물어보세요</h3>
          <ul className="doc-facts">
            <li>"datagokr로 성수동 상권 변화를 월 단위로 추적하는 방법 찾아줘"</li>
            <li>"아파트 실거래가와 공시지가를 필지 단위로 비교하는 파이썬 코드 만들어줘"</li>
            <li>"응급실 병상 실시간 데이터 호출 방법과 필수 파라미터 알려줘"</li>
          </ul>
        </section>

        <section className="doc-section">
          <h2 className="doc-h2"><span className="doc-num">3</span>인증과 이용 정책</h2>
          <AgentAlert tone="info" title="원격 MCP에는 인증이 없습니다">
            도구가 모두 <b>읽기 전용</b>이고(지식 체계 조회), 사용자 키를 받거나 보관하지 않으며, LLM 비용이 드는 설명(explain)은 공개 서버에서 꺼 두었기 때문입니다.
            실제 데이터 호출은 생성된 코드를 <b>각자의 data.go.kr 키</b>로 실행합니다.
          </AgentAlert>
          <ul className="doc-facts">
            <li>전략 도구는 주제 분해·재순위에 LLM을 쓰므로 <b>IP당 시간당 60회</b>로 제한합니다(넘으면 도구 오류로 알림). 테스트 서버라 가용성은 보장하지 않습니다.</li>
            <li>주제 분해 결과는 목표 문장·지식 버전별로 저장해 둡니다 — 같은 질문은 같은 답을 받고, 두 번째부터는 빠릅니다.</li>
            <li>서비스 개선을 위해 도구 호출(도구 이름·인자·시간)을 서버에 기록하고 사용 통계(GA4)로 집계합니다. IP는 해시로만 남깁니다.</li>
            <li>설명(explain=true)과 채팅 화면의 LLM 답변이 필요하면 저장소를 받아 내 Claude 키로 실행하세요.</li>
            <li>HTTP(비암호화) 주소라 일부 클라이언트는 https만 허용합니다 — 그때는 mcp-remote의 <code className="pds-code">--allow-http</code> 또는 내 컴퓨터(stdio) 방식을 쓰세요.</li>
          </ul>
        </section>
        <Credit />
      </div>
    </div>
  )
}
