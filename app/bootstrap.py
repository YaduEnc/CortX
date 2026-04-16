import logging

from app import models as _models  # noqa: F401
from app.core.logging import setup_logging
from app.db.base import Base
from app.db.session import engine
from app.services.storage import get_storage
from sqlalchemy import text

logger = logging.getLogger(__name__)


def main() -> None:
    setup_logging()
    Base.metadata.create_all(bind=engine)
    with engine.begin() as conn:
        conn.execute(
            text(
                "ALTER TABLE app_user_preferences "
                "ADD COLUMN IF NOT EXISTS tts_provider VARCHAR(32) NOT NULL DEFAULT 'elevenlabs'"
            )
        )
        conn.execute(
            text("ALTER TABLE app_user_preferences ALTER COLUMN tts_provider SET DEFAULT 'elevenlabs'")
        )
        conn.execute(
            text(
                "UPDATE app_user_preferences "
                "SET tts_provider = 'elevenlabs' "
                "WHERE tts_provider IS DISTINCT FROM 'elevenlabs'"
            )
        )
        # Add translation columns to transcripts table
        conn.execute(
            text("ALTER TABLE transcripts ADD COLUMN IF NOT EXISTS original_text TEXT")
        )
        conn.execute(
            text("ALTER TABLE transcripts ADD COLUMN IF NOT EXISTS original_language TEXT")
        )
        conn.execute(
            text("ALTER TABLE transcript_segments ADD COLUMN IF NOT EXISTS original_text TEXT")
        )
    try:
        get_storage().ensure_bucket()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Object storage unavailable during bootstrap; DB audio flows still work: %s", exc)


if __name__ == "__main__":
    main()
