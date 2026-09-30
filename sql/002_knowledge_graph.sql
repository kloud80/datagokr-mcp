-- 지식 그래프 (knowledge/ARCHITECTURE.md §2~3). 컴파일 산출물이므로 kg-load 때 통째로 교체한다.
create table if not exists pds_kg_node (
    node_id     text primary key,          -- <type>:<key>
    type        text not null,
    key         text not null,
    name        text,
    props       jsonb not null default '{}'::jsonb,
    source      text                       -- 원본 파일 또는 'catalog'
);
create index if not exists pds_kg_node_type_idx on pds_kg_node (type);

create table if not exists pds_kg_edge (
    edge_id     bigserial primary key,
    src         text not null,
    dst         text not null,
    type        text not null,
    status      text,                      -- documented|inferred|verified|refuted|decided|computed
    props       jsonb not null default '{}'::jsonb,
    evidence    jsonb not null default '[]'::jsonb,
    source      text
);
create index if not exists pds_kg_edge_src_idx on pds_kg_edge (src, type);
create index if not exists pds_kg_edge_dst_idx on pds_kg_edge (dst, type);

create table if not exists pds_kg_doc (
    doc_id      text primary key,          -- <node_id>#<section>
    node_id     text not null,
    kind        text not null,
    title       text,
    body        text not null,
    source      text,
    hash        text not null
);
create index if not exists pds_kg_doc_node_idx on pds_kg_doc (node_id);

create table if not exists pds_kg_chunk (
    chunk_id    text primary key,          -- <doc_id>~<seq>
    doc_id      text not null,
    seq         integer not null,
    text        text not null,
    hash        text not null              -- 임베딩 캐시 키 (임베딩은 DB 밖: data/embeddings/)
);
create index if not exists pds_kg_chunk_doc_idx on pds_kg_chunk (doc_id);

create table if not exists pds_kg_build (
    built_at    timestamptz not null default now(),
    snapshot    date,
    source_hash text,
    nodes       integer,
    edges       integer,
    docs        integer,
    chunks      integer,
    note        text
);
