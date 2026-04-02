# Supabase-Only AI Pipeline Runbook (LM Studio)

This runbook is the MVP path:

`audio + transcript in Supabase -> ai_pipeline_jobs -> LM Studio worker -> memory tables -> RPC query APIs`

## 1) Prerequisites

1. Supabase project is active.
2. `audio-recordings` bucket is private.
3. Transcript rows are already being inserted into `public.transcripts`.
4. LM Studio server is running and reachable from worker host.

## 2) Apply SQL Pack

Run this file in Supabase SQL Editor:

- `supabase/sql/001_ai_memory_mvp.sql`

What it creates:

1. AI pipeline tables (`ai_pipeline_jobs`, `ai_pipeline_logs`).
2. Memory tables (`memory_items`, `entities`, `memory_item_entities`, `daily_summaries`).
3. Job RPC helpers:
   - `claim_ai_pipeline_job()`
   - `complete_ai_pipeline_job(...)`
   - `retry_failed_ai_jobs()`
   - `purge_memory_for_transcript(...)`
4. Query RPCs:
   - `api_memory_tasks(...)`
   - `api_memory_ideas(...)`
   - `api_memory_discussions(...)`
   - `fn_daily_summary_v1(...)`
5. Trigger to auto-enqueue AI jobs for new transcript inserts.

## 3) Backfill Existing Data

If old transcript rows do not have `user_id`, set it first:

```sql
update public.transcripts
set user_id = 'YOUR_USER_ID_OR_EMAIL'
where user_id is null;
```

Backfill jobs for existing rows:

```sql
insert into public.ai_pipeline_jobs (transcript_id, status)
select t.id, 'pending'::public.ai_job_status
from public.transcripts t
left join public.ai_pipeline_jobs j on j.transcript_id = t.id
where j.transcript_id is null
  and coalesce(trim(t.transcript), '') <> '';
```

Check queue:

```sql
select status, count(*) from public.ai_pipeline_jobs group by status order by status;
```

## 4) Install Worker Dependencies

Add dependency in your Python environment:

```bash
pip install -r requirements.txt
```

## 5) Configure Worker Environment

Export env vars on worker machine:

```bash
export SUPABASE_URL="https://<project-ref>.supabase.co"
export SUPABASE_SERVICE_ROLE_KEY="<service-role-key>"
export LM_STUDIO_BASE_URL="http://127.0.0.1:1234/v1"
export LM_STUDIO_MODEL="qwen2.5-7b-instruct"
export AI_PIPELINE_POLL_SECONDS="2"
export AI_PIPELINE_REQUEST_TIMEOUT_SECONDS="180"
export AI_PIPELINE_MAX_ITEMS_PER_TYPE="12"
```

## 6) Run Worker

```bash
python3 scripts/supabase_ai_worker.py
```

Expected logs:

1. Worker starts and prints LM Studio endpoint/model.
2. Jobs move from `pending` -> `processing` -> `done`.
3. `memory_items` and `entities` begin filling.

## 7) Validate Output

SQL checks:

```sql
select status, count(*) from public.ai_pipeline_jobs group by status order by status;
select count(*) from public.memory_items;
select count(*) from public.entities;
```

RPC checks:

```sql
select * from public.api_memory_tasks('YOUR_USER_ID_OR_EMAIL', 'open', 20);
select * from public.api_memory_ideas('YOUR_USER_ID_OR_EMAIL', 7, 50);
select * from public.api_memory_discussions('YOUR_USER_ID_OR_EMAIL', 'Aman', 30, 20);
select public.fn_daily_summary_v1('YOUR_USER_ID_OR_EMAIL'::text);
```

## 8) Retry Failed Jobs

```sql
select public.retry_failed_ai_jobs();
```

Then keep worker running; it will pick retried jobs.

## 9) Security Rules (Must Keep)

1. Keep Supabase bucket private.
2. Keep `SUPABASE_SERVICE_ROLE_KEY` only on worker/backend.
3. Never store service keys in ESP firmware or mobile app.
4. Rotate any leaked keys immediately.

