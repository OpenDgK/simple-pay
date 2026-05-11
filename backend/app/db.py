from __future__ import annotations

import time
from collections.abc import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import settings


class Base(DeclarativeBase):
    pass


engine_kwargs = {
    "future": True,
}
if settings.database_url.startswith("sqlite"):
    engine_kwargs["connect_args"] = {"check_same_thread": False}
else:
    engine_kwargs.update({"pool_pre_ping": True, "pool_recycle": 1800})

engine = create_engine(settings.database_url, **engine_kwargs)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, autoflush=False, future=True)


def wait_for_database(timeout_seconds: int = 60) -> None:
    deadline = time.time() + timeout_seconds
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return
        except Exception as exc:  # pragma: no cover - depends on container startup timing
            last_error = exc
            time.sleep(2)
    raise RuntimeError(f"database is not ready: {last_error}")


def init_db() -> None:
    from . import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    _run_lightweight_migrations()


def _column_exists(conn, table: str, column: str) -> bool:
    if settings.database_url.startswith("sqlite"):
        rows = conn.execute(text(f"PRAGMA table_info({table})")).mappings().all()
        return any(row["name"] == column for row in rows)
    row = conn.execute(text(f"SHOW COLUMNS FROM `{table}` LIKE :column"), {"column": column}).first()
    return row is not None


def _add_column_if_missing(conn, table: str, column: str, definition: str) -> None:
    if not _column_exists(conn, table, column):
        conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {definition}"))


def _run_lightweight_migrations() -> None:
    with engine.begin() as conn:
        _add_column_if_missing(conn, "orders", "email_sent_at", "DATETIME NULL")
        _add_column_if_missing(conn, "orders", "email_error", "TEXT NULL")


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
