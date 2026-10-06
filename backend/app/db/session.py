from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache
import logging

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings


logger = logging.getLogger(__name__)


class DatabaseConfigurationError(RuntimeError):
    """Raised when PostgreSQL persistence is requested without a database URL."""


def is_database_configured() -> bool:
    return get_settings().sqlalchemy_database_url() is not None


@lru_cache
def get_engine() -> Engine:
    settings = get_settings()
    database_url = settings.sqlalchemy_database_url()
    if database_url is None:
        raise DatabaseConfigurationError("DATABASE_URL is not configured.")

    return create_engine(
        database_url,
        pool_pre_ping=True,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_recycle=settings.db_pool_recycle_seconds,
        connect_args={"connect_timeout": settings.db_connect_timeout_seconds},
    )


@lru_cache
def get_session_factory() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), expire_on_commit=False)


@contextmanager
def database_session() -> Iterator[Session]:
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        logger.exception("Database transaction failed and was rolled back.")
        raise
    finally:
        session.close()
