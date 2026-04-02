-- SecondMind Supabase-Only AI Memory MVP
-- Run this in Supabase SQL Editor.

begin;

create extension if not exists pgcrypto;
create extension if not exists vector;

-- -------------------------------------------------------------------
-- Existing transcript table hardening
-- -------------------------------------------------------------------
alter table if exists public.transcripts
  add column if not exists user_id text,
  add column if not exists device_code text,
  add column if not exists language text,
  add column if not exists duration_seconds double precision;

create index if not exists idx_transcripts_user_created_at
  on public.transcripts(user_id, created_at desc);

-- -------------------------------------------------------------------
-- Enums
-- -------------------------------------------------------------------
do $$
begin
  create type public.ai_job_status as enum ('pending', 'processing', 'done', 'failed');
exception when duplicate_object then null;
end $$;

do $$
begin
  create type public.ai_item_type as enum ('task', 'idea', 'decision', 'reminder');
exception when duplicate_object then null;
end $$;

do $$
begin
  create type public.ai_item_status as enum ('open', 'in_progress', 'done', 'archived');
exception when duplicate_object then null;
end $$;

-- -------------------------------------------------------------------
-- AI pipeline + memory tables
-- -------------------------------------------------------------------
create table if not exists public.ai_pipeline_jobs (
  id uuid primary key default gen_random_uuid(),
  transcript_id bigint not null references public.transcripts(id) on delete cascade,
  status public.ai_job_status not null default 'pending',
  attempts integer not null default 0,
  next_run_at timestamptz not null default now(),
  locked_at timestamptz,
  last_error text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (transcript_id)
);

create index if not exists idx_ai_pipeline_jobs_status_next
  on public.ai_pipeline_jobs(status, next_run_at);

create table if not exists public.memory_items (
  id uuid primary key default gen_random_uuid(),
  transcript_id bigint not null references public.transcripts(id) on delete cascade,
  user_id text not null,
  device_code text,
  item_type public.ai_item_type not null,
  title text not null,
  details text,
  priority smallint check (priority between 1 and 5),
  due_at timestamptz,
  happened_at timestamptz,
  status public.ai_item_status not null default 'open',
  confidence numeric(4,3) check (confidence between 0 and 1),
  source_quote text,
  source_start_seconds double precision,
  source_end_seconds double precision,
  created_at timestamptz not null default now()
);

create index if not exists idx_memory_items_user_type_created
  on public.memory_items(user_id, item_type, created_at desc);

create index if not exists idx_memory_items_user_status
  on public.memory_items(user_id, status);

create index if not exists idx_memory_items_transcript
  on public.memory_items(transcript_id);

create table if not exists public.entities (
  id uuid primary key default gen_random_uuid(),
  user_id text not null,
  name text not null,
  normalized_name text not null,
  entity_type text not null check (entity_type in ('person', 'project', 'org', 'place', 'topic', 'time')),
  created_at timestamptz not null default now(),
  unique (user_id, normalized_name, entity_type)
);

create index if not exists idx_entities_user_norm
  on public.entities(user_id, normalized_name);

create table if not exists public.memory_item_entities (
  memory_item_id uuid not null references public.memory_items(id) on delete cascade,
  entity_id uuid not null references public.entities(id) on delete cascade,
  role text not null default 'mentioned',
  created_at timestamptz not null default now(),
  primary key (memory_item_id, entity_id, role)
);

create index if not exists idx_memory_item_entities_entity
  on public.memory_item_entities(entity_id);

create table if not exists public.daily_summaries (
  id uuid primary key default gen_random_uuid(),
  user_id text not null,
  summary_date date not null,
  summary_json jsonb not null,
  created_at timestamptz not null default now(),
  unique (user_id, summary_date)
);

create table if not exists public.ai_pipeline_logs (
  id bigserial primary key,
  transcript_id bigint references public.transcripts(id) on delete cascade,
  stage text not null,
  level text not null check (level in ('info', 'warn', 'error')),
  message text not null,
  payload jsonb,
  created_at timestamptz not null default now()
);

-- -------------------------------------------------------------------
-- Utility trigger
-- -------------------------------------------------------------------
create or replace function public.set_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

drop trigger if exists trg_ai_pipeline_jobs_updated_at on public.ai_pipeline_jobs;
create trigger trg_ai_pipeline_jobs_updated_at
before update on public.ai_pipeline_jobs
for each row execute function public.set_updated_at();

-- -------------------------------------------------------------------
-- Job lifecycle helpers
-- -------------------------------------------------------------------
create or replace function public.enqueue_transcript_ai_job(p_transcript_id bigint)
returns void
language plpgsql
security definer
set search_path = public
as $$
begin
  insert into public.ai_pipeline_jobs(transcript_id, status, next_run_at)
  values (p_transcript_id, 'pending', now())
  on conflict (transcript_id)
  do update
  set status = case
      when public.ai_pipeline_jobs.status = 'done' then public.ai_pipeline_jobs.status
      else 'pending'
    end,
    next_run_at = now(),
    last_error = null;
end;
$$;

create or replace function public.claim_ai_pipeline_job()
returns setof public.ai_pipeline_jobs
language plpgsql
security definer
set search_path = public
as $$
begin
  return query
  with candidate as (
    select j.id
    from public.ai_pipeline_jobs j
    where j.status = 'pending'
      and j.next_run_at <= now()
      and (j.locked_at is null or j.locked_at < (now() - interval '10 minutes'))
    order by j.created_at asc
    limit 1
    for update skip locked
  )
  update public.ai_pipeline_jobs j
  set status = 'processing',
      attempts = j.attempts + 1,
      locked_at = now(),
      last_error = null
  from candidate c
  where j.id = c.id
  returning j.*;
end;
$$;

create or replace function public.complete_ai_pipeline_job(
  p_job_id uuid,
  p_success boolean,
  p_error text default null
)
returns public.ai_pipeline_jobs
language plpgsql
security definer
set search_path = public
as $$
declare
  v_job public.ai_pipeline_jobs;
begin
  if p_success then
    update public.ai_pipeline_jobs
    set status = 'done',
        locked_at = null,
        next_run_at = now(),
        last_error = null
    where id = p_job_id
    returning * into v_job;
  else
    update public.ai_pipeline_jobs
    set status = 'failed',
        locked_at = null,
        last_error = p_error,
        next_run_at = now() + (interval '30 seconds' * power(2, least(attempts, 6)))
    where id = p_job_id
    returning * into v_job;
  end if;

  return v_job;
end;
$$;

create or replace function public.retry_failed_ai_jobs()
returns integer
language plpgsql
security definer
set search_path = public
as $$
declare
  v_count integer;
begin
  update public.ai_pipeline_jobs
  set status = 'pending',
      next_run_at = now(),
      locked_at = null
  where status = 'failed'
    and attempts < 5
    and next_run_at <= now();

  get diagnostics v_count = row_count;
  return v_count;
end;
$$;

create or replace function public.purge_memory_for_transcript(p_transcript_id bigint)
returns void
language plpgsql
security definer
set search_path = public
as $$
begin
  delete from public.memory_item_entities mie
  using public.memory_items mi
  where mie.memory_item_id = mi.id
    and mi.transcript_id = p_transcript_id;

  delete from public.memory_items
  where transcript_id = p_transcript_id;
end;
$$;

-- -------------------------------------------------------------------
-- Auto enqueue on transcript insert
-- -------------------------------------------------------------------
create or replace function public.trg_enqueue_ai_on_transcript()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
  if new.transcript is not null and length(trim(new.transcript)) > 0 then
    perform public.enqueue_transcript_ai_job(new.id);
  end if;
  return new;
end;
$$;

drop trigger if exists trg_enqueue_ai_on_transcript_insert on public.transcripts;
create trigger trg_enqueue_ai_on_transcript_insert
after insert on public.transcripts
for each row execute function public.trg_enqueue_ai_on_transcript();

-- -------------------------------------------------------------------
-- Query RPCs
-- -------------------------------------------------------------------
drop function if exists public.api_memory_tasks(text, text, int);
create or replace function public.api_memory_tasks(
  p_user_id text,
  p_status text default 'open',
  p_limit int default 20
)
returns table (
  item_id uuid,
  transcript_id bigint,
  item_type text,
  title text,
  details text,
  priority smallint,
  due_at timestamptz,
  confidence numeric,
  created_at timestamptz
)
language sql
stable
as $$
  select
    mi.id,
    mi.transcript_id,
    mi.item_type::text,
    mi.title,
    mi.details,
    mi.priority,
    mi.due_at,
    mi.confidence,
    mi.created_at
  from public.memory_items mi
  where mi.user_id = p_user_id
    and mi.item_type = 'task'
    and (
      p_status = 'all'
      or mi.status::text = p_status
      or (p_status = 'open' and mi.status in ('open', 'in_progress'))
    )
  order by coalesce(mi.priority, 3) asc, coalesce(mi.due_at, mi.created_at) asc
  limit greatest(1, least(p_limit, 100));
$$;

drop function if exists public.api_memory_ideas(text, int, int);
create or replace function public.api_memory_ideas(
  p_user_id text,
  p_days int default 7,
  p_limit int default 50
)
returns table (
  item_id uuid,
  transcript_id bigint,
  title text,
  details text,
  confidence numeric,
  created_at timestamptz
)
language sql
stable
as $$
  select
    mi.id,
    mi.transcript_id,
    mi.title,
    mi.details,
    mi.confidence,
    mi.created_at
  from public.memory_items mi
  where mi.user_id = p_user_id
    and mi.item_type = 'idea'
    and mi.created_at >= now() - make_interval(days => greatest(1, least(p_days, 90)))
  order by mi.created_at desc
  limit greatest(1, least(p_limit, 100));
$$;

drop function if exists public.api_memory_discussions(text, text, int, int);
create or replace function public.api_memory_discussions(
  p_user_id text,
  p_person text,
  p_days int default 30,
  p_limit int default 30
)
returns table (
  transcript_id bigint,
  audio_file text,
  snippet text,
  created_at timestamptz
)
language sql
stable
as $$
  with person_entities as (
    select e.id
    from public.entities e
    where e.user_id = p_user_id
      and e.entity_type = 'person'
      and e.normalized_name = lower(trim(p_person))
  ),
  linked_transcripts as (
    select distinct mi.transcript_id
    from public.memory_item_entities mie
    join public.memory_items mi on mi.id = mie.memory_item_id
    where mi.user_id = p_user_id
      and mie.entity_id in (select id from person_entities)
  )
  select
    t.id as transcript_id,
    t.audio_file,
    left(t.transcript, 400) as snippet,
    t.created_at
  from public.transcripts t
  where t.user_id = p_user_id
    and t.created_at >= now() - make_interval(days => greatest(1, least(p_days, 365)))
    and (
      t.id in (select transcript_id from linked_transcripts)
      or t.transcript ilike '%' || p_person || '%'
    )
  order by t.created_at desc
  limit greatest(1, least(p_limit, 100));
$$;

drop function if exists public.fn_daily_summary_v1(text, date);
create or replace function public.fn_daily_summary_v1(
  p_user_id text,
  p_day date default (now() at time zone 'utc')::date
)
returns jsonb
language sql
stable
as $$
with caps as (
  select count(*) as captures_count
  from public.transcripts
  where user_id = p_user_id
    and (created_at at time zone 'utc')::date = p_day
),
top_task_rows as (
  select title, priority, due_at, created_at
  from public.memory_items
  where user_id = p_user_id
    and item_type = 'task'
    and status in ('open', 'in_progress')
  order by coalesce(priority, 3), coalesce(due_at, created_at)
  limit 5
),
top_tasks as (
  select coalesce(
    jsonb_agg(
      jsonb_build_object(
        'title', title,
        'priority', priority,
        'due_at', due_at
      )
    ),
    '[]'::jsonb
  ) as data
  from top_task_rows
),
top_idea_rows as (
  select title, created_at
  from public.memory_items
  where user_id = p_user_id
    and item_type = 'idea'
    and created_at >= p_day::timestamptz
    and created_at < (p_day::timestamptz + interval '1 day')
  order by created_at desc
  limit 5
),
top_ideas as (
  select coalesce(
    jsonb_agg(
      jsonb_build_object(
        'title', title,
        'created_at', created_at
      )
    ),
    '[]'::jsonb
  ) as data
  from top_idea_rows
),
pending_decisions as (
  select count(*) as count_pending
  from public.memory_items
  where user_id = p_user_id
    and item_type = 'decision'
    and status in ('open', 'in_progress')
)
select jsonb_build_object(
  'summary_date', p_day,
  'captures_count', (select captures_count from caps),
  'top_tasks', (select data from top_tasks),
  'top_ideas', (select data from top_ideas),
  'pending_decisions', (select count_pending from pending_decisions)
);
$$;

commit;
