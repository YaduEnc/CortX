-- SecondMind / CortX
-- Smart action detection schema
--
-- Note:
-- Existing application ids are VARCHAR(36), not native UUID columns.
-- This migration keeps the new tables aligned with the current schema.

CREATE TABLE IF NOT EXISTS contacts (
    id VARCHAR(36) PRIMARY KEY DEFAULT gen_random_uuid()::text,
    user_id VARCHAR(36) NOT NULL REFERENCES app_users(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    name_aliases TEXT[] NOT NULL DEFAULT '{}',
    phone TEXT,
    email TEXT,
    whatsapp_number TEXT,
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_contacts_user_id ON contacts(user_id);
CREATE INDEX IF NOT EXISTS idx_contacts_name_search ON contacts USING gin(name_aliases);

CREATE TABLE IF NOT EXISTS pending_actions (
    id VARCHAR(36) PRIMARY KEY DEFAULT gen_random_uuid()::text,
    user_id VARCHAR(36) NOT NULL REFERENCES app_users(id) ON DELETE CASCADE,
    session_id VARCHAR(36) REFERENCES capture_sessions(id) ON DELETE SET NULL,

    action_type TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',

    contact_id VARCHAR(36) REFERENCES contacts(id) ON DELETE SET NULL,
    recipient_name TEXT NOT NULL,
    recipient_phone TEXT,
    recipient_email TEXT,
    contact_resolved BOOLEAN NOT NULL DEFAULT FALSE,

    draft_subject TEXT,
    draft_body TEXT NOT NULL,
    original_transcript_snippet TEXT,

    confidence_score DOUBLE PRECISION,
    detected_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    acted_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_pending_actions_user_id ON pending_actions(user_id);
CREATE INDEX IF NOT EXISTS idx_pending_actions_status ON pending_actions(status);
