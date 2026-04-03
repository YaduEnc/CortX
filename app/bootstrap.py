import logging

from app import models as _models  # noqa: F401
from app.core.logging import setup_logging
from app.db.base import Base
from app.db.session import engine
from app.services.storage import get_storage

logger = logging.getLogger(__name__)


def main() -> None:
    setup_logging()
    Base.metadata.create_all(bind=engine)
    try:
        get_storage().ensure_bucket()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Object storage unavailable during bootstrap; DB audio flows still work: %s", exc)


if __name__ == "__main__":
    main()
