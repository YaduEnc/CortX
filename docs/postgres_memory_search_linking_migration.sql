begin;

create extension if not exists pg_trgm;

create table if not exists memory_links (
  id varchar(36) primary key,
  user_id varchar(36) not null references app_users(id) on delete cascade,
  session_id varchar(36) not null references capture_sessions(id) on delete cascade,
  link_type varchar(32) not null,
  entity_id varchar(36) null references entities(id) on delete cascade,
  founder_idea_id varchar(36) null references founder_idea_clusters(id) on delete cascade,
  source varchar(32) not null,
  status varchar(32) not null default 'suggested',
  confidence double precision null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint uq_memory_links_session_entity_type unique (session_id, entity_id, link_type),
  constraint uq_memory_links_session_founder_type unique (session_id, founder_idea_id, link_type),
  constraint ck_memory_links_single_target check (
    (entity_id is not null and founder_idea_id is null)
    or
    (entity_id is null and founder_idea_id is not null)
  )
);

create index if not exists ix_memory_links_user_session_status
  on memory_links(user_id, session_id, status);
create index if not exists ix_memory_links_entity
  on memory_links(entity_id);
create index if not exists ix_memory_links_founder
  on memory_links(founder_idea_id);
create index if not exists ix_memory_links_user_type_status
  on memory_links(user_id, link_type, status);

create index if not exists ix_transcripts_full_text_tsv
  on transcripts using gin (to_tsvector('simple', coalesce(full_text, '')));

create index if not exists ix_ai_extractions_summary_intent_tsv
  on ai_extractions using gin (
    to_tsvector(
      'simple',
      coalesce(summary, '') || ' ' || coalesce(intent, '')
    )
  );

create index if not exists ix_ai_items_title_details_tsv
  on ai_items using gin (
    to_tsvector(
      'simple',
      coalesce(title, '') || ' ' || coalesce(details, '')
    )
  );

create index if not exists ix_founder_idea_clusters_search_tsv
  on founder_idea_clusters using gin (
    to_tsvector(
      'simple',
      coalesce(title, '') || ' ' || coalesce(summary, '') || ' ' || coalesce(target_user, '')
    )
  );

create index if not exists ix_founder_idea_clusters_normalized_title_trgm
  on founder_idea_clusters using gin (normalized_title gin_trgm_ops);

commit;
