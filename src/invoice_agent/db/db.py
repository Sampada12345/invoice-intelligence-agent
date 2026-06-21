from __future__ import annotations

import os
from contextlib import contextmanager
from functools import lru_cache
from typing import Iterator

from sqlalchemy import MetaData, create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Shared SQLAlchemy declarative base with Alembic-friendly metadata."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


ALEMBIC_TARGET_METADATA = Base.metadata


def _env_flag(name: str, default: bool = False) -> bool:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    return raw_value.strip().lower() in {"1", "true", "yes", "on"}


def normalize_database_url(database_url: str | None = None) -> str:
    """
    Normalize a database URL for cross-environment use.

    Supported examples:
    - sqlite:///./invoice_agent.db
    - postgresql+psycopg://user:pass@localhost:5432/invoice_agent
    - postgresql://user:pass@localhost:5432/invoice_agent
    - postgres://user:pass@localhost:5432/invoice_agent
    """

    url = (
        database_url
        or os.getenv("DATABASE_URL")
        or os.getenv("INVOICE_AGENT_DATABASE_URL")
        or "sqlite:///./invoice_agent.db"
    ).strip()

    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+psycopg://", 1)

    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg://", 1)

    return url


def is_sqlite_url(database_url: str | None = None) -> bool:
    return normalize_database_url(database_url).startswith("sqlite")


@lru_cache(maxsize=4)
def get_engine(database_url: str | None = None, *, echo: bool | None = None) -> Engine:
    """
    Create a cached SQLAlchemy engine.

    The engine supports SQLite for local development and PostgreSQL for
    production deployments.
    """

    url = normalize_database_url(database_url)
    should_echo = _env_flag("SQLALCHEMY_ECHO", default=False) if echo is None else echo

    connect_args: dict[str, object] = {}
    engine_kwargs: dict[str, object] = {
        "echo": should_echo,
        "future": True,
        "pool_pre_ping": True,
    }

    if url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
        engine_kwargs["connect_args"] = connect_args

    return create_engine(url, **engine_kwargs)


@lru_cache(maxsize=4)
def get_session_factory(database_url: str | None = None) -> sessionmaker[Session]:
    """Create a cached session factory for the configured database."""

    return sessionmaker(
        bind=get_engine(database_url),
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
        class_=Session,
    )


def get_db(database_url: str | None = None) -> Iterator[Session]:
    """Yield a SQLAlchemy session for use in request handlers and jobs."""

    session_factory = get_session_factory(database_url)
    session = session_factory()
    try:
        yield session
    finally:
        session.close()


@contextmanager
def session_scope(database_url: str | None = None) -> Iterator[Session]:
    """
    Provide a transactional session scope.

    Commits on success and rolls back on any raised exception.
    """

    session_factory = get_session_factory(database_url)
    session = session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def init_db(database_url: str | None = None) -> None:
    """
    Create all registered tables.

    Importing models locally ensures declarative mappings are registered before
    metadata creation runs.
    """

    from . import models  # noqa: F401

    engine = get_engine(database_url)
    Base.metadata.create_all(bind=engine)
