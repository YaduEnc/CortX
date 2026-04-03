-- Idea Graph: Entity tables
-- Run this migration to add entity extraction support

CREATE TABLE IF NOT EXISTS entities (
    id VARCHAR(36) PRIMARY KEY,
    user_id VARCHAR(36) NOT NULL REFERENCES app_users(id) ON DELETE CASCADE,
    entity_type VARCHAR(32) NOT NULL,
    name VARCHAR(255) NOT NULL,
    normalized_name VARCHAR(255) NOT NULL,
    mention_count INTEGER NOT NULL DEFAULT 1,
    first_seen_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    last_seen_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_entities_user_type ON entities(user_id, entity_type);
CREATE INDEX IF NOT EXISTS ix_entities_user_name ON entities(user_id, normalized_name);
CREATE INDEX IF NOT EXISTS ix_entities_normalized_name ON entities(normalized_name);

CREATE TABLE IF NOT EXISTS entity_mentions (
    id VARCHAR(36) PRIMARY KEY,
    entity_id VARCHAR(36) NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    user_id VARCHAR(36) NOT NULL REFERENCES app_users(id) ON DELETE CASCADE,
    session_id VARCHAR(36) NOT NULL REFERENCES capture_sessions(id) ON DELETE CASCADE,
    extraction_id VARCHAR(36) REFERENCES ai_extractions(id) ON DELETE SET NULL,
    context_snippet TEXT,
    confidence FLOAT,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_entity_mentions_entity ON entity_mentions(entity_id);
CREATE INDEX IF NOT EXISTS ix_entity_mentions_session ON entity_mentions(session_id);
CREATE INDEX IF NOT EXISTS ix_entity_mentions_user_session ON entity_mentions(user_id, session_id);
