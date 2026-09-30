-- Phase 1: 벌크 메타 카탈로그 · 3축 분류 · 1차 점수
-- 스키마는 실행 시 search_path로 정한다 (POSTGRES_SCHEME). 여기서는 한정하지 않는다.
-- 스냅샷 단위로 적재한다. 같은 snapshot_date를 다시 적재하면 교체.

create table if not exists pds_catalog_dataset (
    snapshot_date     date        not null,
    id                text        not null,          -- 포털 목록키
    list_type         text        not null,          -- FILE | API | STD
    api_type          text,                          -- REST | SOAP | LINK
    title             text        not null,
    file_title        text,
    brm               text,
    brm_field         text,                          -- 정책분야
    brm_area          text,                          -- 정책영역
    agency_code       text,
    agency_name       text,
    dept              text,
    legal_basis       text,                          -- 보유근거
    collect_method    text,
    update_cycle      text,
    next_reg_date     date,
    media_type        text,
    row_count         bigint,
    formats           text,
    keywords          text,
    usage_count       bigint,                        -- 다운로드/활용신청 건수
    view_count        bigint,
    registered_at     date,
    modified_at       date,
    data_limit        text,
    provide_form      text,
    description       text,
    notes             text,
    spatial_scope     text,
    temporal_scope    text,
    fee               text,
    license           text,
    traffic_raw       text,
    daily_traffic_dev integer,
    approval_raw      text,
    approval_dev      text,                          -- auto | review
    approval_ops      text,
    national_key      boolean     not null default false,
    standard          boolean     not null default false,
    std_id            text,
    url               text,
    request_vars      text,                          -- 쉼표 구분 (15121937)
    output_cols       text,                          -- 쉼표 구분 (15121937 또는 제공 표준 항목)
    service_type      text,
    primary key (snapshot_date, id)
);

create table if not exists pds_dataset_class (
    snapshot_date       date not null,
    id                  text not null,
    sector              text,               -- 대화 전: BRM 정책영역. 대화 후: knowledge/sectors 슬러그
    sector_rule         text,               -- 부문 재배치 규칙 id (sector_map.yaml)
    sector_field        text,
    subsector           text,               -- 세부 부문 slug (subsectors.yaml)
    subsector_name      text,
    subsector_depth     text,               -- front | back
    cycle_override      text,               -- event 등
    last_event          text,
    cross_cutting       boolean,            -- 부문을 넘는 공통 마스터 (행정표준코드 등)
    sector_area         text,
    agency_tier         text,               -- 중앙행정기관|광역자치단체|기초자치단체|교육청|공공기관|기타
    coverage            text,               -- 기관 계층으로 본 포괄 범위
    admin_unit          text,               -- 가장 세밀한 공간 단위
    admin_unit_conf     text,               -- high|medium|low
    admin_unit_evidence text,
    admin_unit_method   text,               -- rule|llm|human
    excluded_by         text,               -- 제외 규칙 id (knowledge/sectors/exclusions.yaml), null = 대상
    primary key (snapshot_date, id)
);

create table if not exists pds_dataset_score (
    snapshot_date       date not null,
    id                  text not null,
    api_kind_label      text,
    s_usage             real,
    s_designation       real,
    s_api_kind          real,
    s_freshness         real,
    s_meta_fill         real,
    s_granularity       real,
    granularity_ev      text,
    s_coverage          real,
    coverage_ev         text,
    s_linkable          real,
    linkable_ev         text,
    prelim_score        real,
    rank_overall        integer,
    rank_in_sector      integer,
    rank_in_sector_tier integer,
    top100_available    boolean,
    imputed             text,               -- 대체값을 넣은 항목 (외부 링크 API)
    weights             jsonb,
    primary key (snapshot_date, id)
);

create table if not exists pds_std_dataset (
    std_id        text primary key,
    name          text,
    scope         text,
    laws          text,
    owner         text,
    provider      text,
    system        text,
    update_cycle  text
);

create table if not exists pds_std_item (
    std_id     text not null,
    item_no    integer not null,
    item_name  text,
    required   text,
    item_desc  text,
    allowed    text,
    unit       text,
    example    text,
    primary key (std_id, item_no)
);

create index if not exists pds_catalog_dataset_brm_idx on pds_catalog_dataset (snapshot_date, brm);
create index if not exists pds_dataset_score_rank_idx on pds_dataset_score (snapshot_date, prelim_score desc);
