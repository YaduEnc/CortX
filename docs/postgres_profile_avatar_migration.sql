ALTER TABLE app_users
  ADD COLUMN IF NOT EXISTS avatar_blob BYTEA,
  ADD COLUMN IF NOT EXISTS avatar_content_type VARCHAR(128),
  ADD COLUMN IF NOT EXISTS avatar_file_size_bytes INTEGER,
  ADD COLUMN IF NOT EXISTS avatar_updated_at TIMESTAMPTZ;
