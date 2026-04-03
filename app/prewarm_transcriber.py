import logging

from app.core.logging import setup_logging
from app.services.transcriber import get_transcriber

logger = logging.getLogger(__name__)


def main() -> None:
    setup_logging()
    transcriber = get_transcriber()
    logger.info("Transcriber ready: model=%s", transcriber.model_name)


if __name__ == "__main__":
    main()
