-- 서비스 사용 기록 (개선용) — 웹 채팅 대화·피드백, MCP 도구 호출, 전략 API.
-- git에는 올리지 않는 운영 데이터다. IP는 소금 친 해시만 남긴다.
create table if not exists pds_usage_log (
    id          bigserial primary key,
    at          timestamptz not null default now(),
    kind        text not null,              -- chat · mcp · plan · feedback
    turn_id     text,                       -- 채팅 한 번의 답(피드백이 가리킨다)
    session     text,                       -- 브라우저 세션(무작위 id) · MCP 클라이언트 해시
    client_hash text,                       -- sha256(소금 + IP + User-Agent) 앞 16자
    question    text,                       -- 채팅 질문 · MCP 도구 이름
    reply       text,                       -- 채팅 답 (MCP는 비움)
    args        jsonb,                      -- MCP 도구 인자 · 피드백 내용
    plan_ids    jsonb,                      -- 전략에 오른 데이터 id
    trace       jsonb,                      -- 도구 호출 순서
    usage       jsonb,                      -- 토큰·모델
    elapsed_s   real,
    status      text,                       -- ok · error · refusal
    error       text
);
create index if not exists pds_usage_log_at on pds_usage_log (at desc);
create index if not exists pds_usage_log_kind on pds_usage_log (kind, at desc);
create index if not exists pds_usage_log_turn on pds_usage_log (turn_id);
