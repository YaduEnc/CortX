from app import models as _models  # noqa: F401
from app.core.logging import setup_logging
from app.db.base import Base
from app.db.session import engine
from app.services.storage import get_storage


def main() -> None:
    setup_logging()
    Base.metadata.create_all(bind=engine)
    get_storage().ensure_bucket()


if __name__ == "__main__":
    main()
