-- 시의성(novelty) 축과 세부 부문 가치 원천 (2026-09-28)
alter table pds_dataset_class add column if not exists novelty text;
alter table pds_dataset_class add column if not exists value_source text;
alter table pds_dataset_score add column if not exists s_novelty real;
alter table pds_dataset_score add column if not exists novelty_ev text;
