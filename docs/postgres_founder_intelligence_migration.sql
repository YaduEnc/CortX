CREATE TABLE IF NOT EXISTS founder_idea_clusters (
  id varchar(36) PRIMARY KEY,
  user_id varchar(36) NOT NULL REFERENCES app_users(id) ON DELETE CASCADE,
  title varchar(255) NOT NULL,
  normalized_title varchar(255) NOT NULL,
  summary text NULL,
  problem_statement text NULL,
  proposed_solution text NULL,
  target_user text NULL,
  status varchar(32) NOT NULL DEFAULT 'emerging',
  confidence double precision NULL,
  novelty_score double precision NULL,
  conviction_score double precision NULL,
  mention_count integer NOT NULL DEFAULT 1,
  first_seen_at timestamptz NOT NULL DEFAULT now(),
  last_seen_at timestamptz NOT NULL DEFAULT now(),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_founder_idea_clusters_user_status
  ON founder_idea_clusters(user_id, status);
CREATE INDEX IF NOT EXISTS ix_founder_idea_clusters_user_last_seen
  ON founder_idea_clusters(user_id, last_seen_at);
CREATE INDEX IF NOT EXISTS ix_founder_idea_clusters_normalized_title
  ON founder_idea_clusters(normalized_title);

CREATE TABLE IF NOT EXISTS founder_idea_memories (
  id varchar(36) PRIMARY KEY,
  idea_cluster_id varchar(36) NOT NULL REFERENCES founder_idea_clusters(id) ON DELETE CASCADE,
  user_id varchar(36) NOT NULL REFERENCES app_users(id) ON DELETE CASCADE,
  session_id varchar(36) NOT NULL REFERENCES capture_sessions(id) ON DELETE CASCADE,
  transcript_id varchar(36) NOT NULL REFERENCES transcripts(id) ON DELETE CASCADE,
  relevance_score double precision NULL,
  role varchar(32) NOT NULL DEFAULT 'evidence',
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uq_founder_idea_memory_session UNIQUE (idea_cluster_id, session_id)
);

CREATE INDEX IF NOT EXISTS ix_founder_idea_memories_session
  ON founder_idea_memories(session_id);
CREATE INDEX IF NOT EXISTS ix_founder_idea_memories_idea
  ON founder_idea_memories(idea_cluster_id);

CREATE TABLE IF NOT EXISTS founder_idea_actions (
  id varchar(36) PRIMARY KEY,
  idea_cluster_id varchar(36) NOT NULL REFERENCES founder_idea_clusters(id) ON DELETE CASCADE,
  user_id varchar(36) NOT NULL REFERENCES app_users(id) ON DELETE CASCADE,
  title varchar(255) NOT NULL,
  details text NULL,
  status varchar(32) NOT NULL DEFAULT 'open',
  priority integer NULL,
  due_at timestamptz NULL,
  source varchar(64) NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  completed_at timestamptz NULL
);

CREATE INDEX IF NOT EXISTS ix_founder_idea_actions_user_status
  ON founder_idea_actions(user_id, status);
CREATE INDEX IF NOT EXISTS ix_founder_idea_actions_idea
  ON founder_idea_actions(idea_cluster_id);
CREATE INDEX IF NOT EXISTS ix_founder_idea_actions_due
  ON founder_idea_actions(due_at);

CREATE TABLE IF NOT EXISTS founder_signals (
  id varchar(36) PRIMARY KEY,
  user_id varchar(36) NOT NULL REFERENCES app_users(id) ON DELETE CASCADE,
  idea_cluster_id varchar(36) NULL REFERENCES founder_idea_clusters(id) ON DELETE SET NULL,
  session_id varchar(36) NULL REFERENCES capture_sessions(id) ON DELETE CASCADE,
  transcript_id varchar(36) NULL REFERENCES transcripts(id) ON DELETE CASCADE,
  signal_type varchar(32) NOT NULL,
  title varchar(255) NOT NULL,
  summary text NULL,
  strength double precision NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_founder_signals_user_type_created
  ON founder_signals(user_id, signal_type, created_at);
CREATE INDEX IF NOT EXISTS ix_founder_signals_idea
  ON founder_signals(idea_cluster_id);

CREATE TABLE IF NOT EXISTS weekly_founder_memos (
  id varchar(36) PRIMARY KEY,
  user_id varchar(36) NOT NULL REFERENCES app_users(id) ON DELETE CASCADE,
  week_start date NOT NULL,
  headline text NULL,
  memo_text text NULL,
  top_ideas_json jsonb NULL,
  top_risks_json jsonb NULL,
  top_actions_json jsonb NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uq_weekly_founder_memo_user_week UNIQUE (user_id, week_start)
);

CREATE INDEX IF NOT EXISTS ix_weekly_founder_memos_user_week
  ON weekly_founder_memos(user_id, week_start);
