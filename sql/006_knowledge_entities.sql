-- 지식 엔티티 (KNOWLEDGE-SPEC §3, §5). knowledge/*.yaml에서 빌드되는 파생물 — 손으로 고치지 않는다. pds kload 때 통째로 교체.
create table if not exists pds_k_dataset (
    id          text primary key,
    tier        text not null,                 -- verified | candidate (catalog 층은 pds_catalog_dataset + 뷰)
    title       text not null,
    sector      text not null,
    kind        text,
    channel     text,
    family      text,
    summary     text,
    review      text,                          -- draft | approved | null
    doc         jsonb not null                 -- Dataset yaml 전체
);
create table if not exists pds_k_claim (
    id          text primary key,
    dataset_id  text not null,
    kind        text not null,
    value       text not null,
    grounded    boolean not null,
    rank        text,
    evidence    jsonb not null
);
create index if not exists pds_k_claim_ds_idx on pds_k_claim (dataset_id, kind);
create table if not exists pds_k_edge (
    id          text primary key,
    src         text not null,
    dst         text not null,
    rel         text not null,
    relationship text,
    via_mapping text,
    transform   text,
    confidence  real,
    match_rate  real,
    source      text,
    doc         jsonb not null
);
create index if not exists pds_k_edge_src_idx on pds_k_edge (src, rel);
create index if not exists pds_k_edge_dst_idx on pds_k_edge (dst, rel);
create table if not exists pds_k_key (id text primary key, name text, doc jsonb not null);
create table if not exists pds_k_mapping (id text primary key, left_key text, right_key text, match_rate real, rows integer, doc jsonb not null);
create table if not exists pds_k_code (id text primary key, name text, completeness text, key text, rows integer, doc jsonb not null);
create table if not exists pds_k_code_value (code_list text not null, code text not null, name text, valid boolean, primary key (code_list, code));
create table if not exists pds_k_context (id text primary key, dimension text, question text, doc jsonb not null);
create table if not exists pds_k_recipe (id text primary key, context text, status text, doc jsonb not null);
create table if not exists pds_k_build (built_at timestamptz not null default now(), git_commit text, counts jsonb not null);
-- 3층 커버리지 (§2): 포털 전체 카탈로그에 지식 층을 붙인다. yaml이 있으면 그 tier, 없으면 catalog.
create or replace view pds_k_catalog_tier as
select c.id, c.title, coalesce(k.tier, 'catalog') as tier, k.sector as knowledge_sector, k.summary
from pds_catalog_dataset c left join pds_k_dataset k on k.id = c.id;
