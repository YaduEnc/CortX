-- AI Assistant MVP tables (intent + tasks + reminders + plan)

create table if not exists ai_extractions (
  id varchar(36) primary key,
  user_id varchar(36) not null references app_users(id) on delete cascade,
  session_id varchar(36) not null references capture_sessions(id) on delete cascade,
  transcript_id varchar(36) not null unique references transcripts(id) on delete cascade,
  status varchar(32) not null default 'queued',
  intent text null,
  intent_confidence double precision null,
  summary text null,
  plan_json jsonb null,
  model_name varchar(255) null,
  raw_json jsonb null,
  error_message text null,
  created_at timestamptz not null default now(),
  started_at timestamptz null,
  completed_at timestamptz null,
  updated_at timestamptz not null default now()
);

create index if not exists ix_ai_extractions_user_status on ai_extractions(user_id, status);
create index if not exists ix_ai_extractions_session on ai_extractions(session_id);

create table if not exists ai_items (
  id varchar(36) primary key,
  extraction_id varchar(36) not null references ai_extractions(id) on delete cascade,
  user_id varchar(36) not null references app_users(id) on delete cascade,
  session_id varchar(36) not null references capture_sessions(id) on delete cascade,
  transcript_id varchar(36) not null references transcripts(id) on delete cascade,
  item_type varchar(32) not null,
  title varchar(255) not null,
  details text null,
  due_at timestamptz null,
  timezone varchar(64) null,
  priority integer null,
  status varchar(32) not null default 'open',
  source_segment_start_seconds double precision null,
  source_segment_end_seconds double precision null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  completed_at timestamptz null
);

create index if not exists ix_ai_items_user_type_status on ai_items(user_id, item_type, status);
create index if not exists ix_ai_items_extraction on ai_items(extraction_id);
create index if not exists ix_ai_items_due on ai_items(due_at);
