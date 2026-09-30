-- 세부 부문의 입도 하한 (집계여도 핵심 데이터, 예: 주민등록 인구) 2026-09-28
alter table pds_dataset_class add column if not exists granularity_floor real;
