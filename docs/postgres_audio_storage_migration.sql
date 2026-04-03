-- Run on PostgreSQL before using DB-stored audio in existing deployments.

begin;

alter table if exists capture_sessions
  add column if not exists audio_blob_wav bytea,
  add column if not exists audio_blob_content_type varchar(64),
  add column if not exists audio_blob_size_bytes integer;

alter table if exists audio_chunks
  add column if not exists pcm_data bytea;

alter table if exists audio_chunks
  alter column object_key drop not null;

commit;
