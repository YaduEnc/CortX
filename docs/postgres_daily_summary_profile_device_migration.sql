-- Daily summary + profile preferences + device health migration

begin;

alter table if exists devices
  add column if not exists last_seen_at timestamptz,
  add column if not exists firmware_version varchar(64);

create index if not exists ix_devices_last_seen_at on devices(last_seen_at);

create table if not exists app_user_preferences (
  id varchar(36) primary key,
  user_id varchar(36) not null unique references app_users(id) on delete cascade,
  timezone varchar(64) not null default 'UTC',
  daily_summary_enabled boolean not null default true,
  reminder_notifications_enabled boolean not null default true,
  calendar_export_default_enabled boolean not null default false,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists ix_app_user_preferences_user_id on app_user_preferences(user_id);

insert into app_user_preferences (
  id,
  user_id,
  timezone,
  daily_summary_enabled,
  reminder_notifications_enabled,
  calendar_export_default_enabled,
  created_at,
  updated_at
)
select
  u.id,
  u.id,
  'UTC',
  true,
  true,
  false,
  now(),
  now()
from app_users u
left join app_user_preferences p on p.user_id = u.id
where p.user_id is null;

commit;
