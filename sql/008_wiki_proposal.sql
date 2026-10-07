-- 위키 수정 제안 — 사용자가 데이터 설명·검색어·주의사항·필드·관계·의견을 제안하고, 승인권자가 반영 여부를 결정한다 (pds/service/wiki.py).
-- 승인된 제안은 knowledge/datasets yaml의 사람 필드나 admin_review claim으로 들어간다 (근거 source: wiki:proposal/{id}).
create table if not exists pds_wiki_proposal (
    id             bigserial primary key,
    dataset_id     text not null,
    kind           text not null,                 -- summary · synonym · limit · field · relation · note
    target         text,                          -- field: 필드 이름 · relation: 상대 데이터 id
    current_value  text,                          -- 제안 당시 값 (summary·limit)
    proposed_value text not null,
    reason         text,
    author         text,                          -- 제안자가 적은 이름 (선택)
    client_hash    text,                          -- 소금 친 IP·UA 해시 (usage.client_hash)
    status         text not null default 'pending' check (status in ('pending', 'approved', 'rejected')),
    reviewer       text,
    review_note    text,
    reviewed_at    timestamptz,
    applied        jsonb,                         -- 반영 결과 {file, field, claim}
    created_at     timestamptz not null default now()
);
create index if not exists pds_wiki_proposal_dataset on pds_wiki_proposal (dataset_id);
create index if not exists pds_wiki_proposal_status on pds_wiki_proposal (status, created_at desc);
