"""SQLAlchemy engine + session management.

SQLite by default (fully offline, single file under ProgramData). Foreign keys
are enforced via a connection pragma. ``session_scope`` gives an atomic
unit-of-work: commit on success, rollback on any exception -- this is how the
service layer guarantees the "all-or-nothing" posting rules.
"""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker, Session

from zenith.core import paths


class Base(DeclarativeBase):
    pass


class Database:
    def __init__(self, url: str | None = None):
        if url is None:
            url = f"sqlite:///{paths.db_path()}"
        self.url = url
        self.engine = create_engine(url, future=True)
        self._enable_sqlite_fk()
        self._Session = sessionmaker(bind=self.engine, expire_on_commit=False, future=True)

    def _enable_sqlite_fk(self) -> None:
        if self.url.startswith("sqlite"):
            @event.listens_for(self.engine, "connect")
            def _fk_on(dbapi_conn, _):  # pragma: no cover - trivial
                cur = dbapi_conn.cursor()
                cur.execute("PRAGMA foreign_keys=ON")
                cur.close()

    def create_all(self) -> None:
        # Import models so they register on the metadata before create_all.
        from zenith.db import models  # noqa: F401
        Base.metadata.create_all(self.engine)

    def session(self) -> Session:
        return self._Session()


_DB: Database | None = None


def get_database(url: str | None = None) -> Database:
    global _DB
    if _DB is None or url is not None:
        _DB = Database(url)
    return _DB


def reset_database_singleton() -> None:
    """Testing helper -- drop the cached singleton."""
    global _DB
    _DB = None


@contextmanager
def session_scope(db: Database | None = None):
    db = db or get_database()
    session = db.session()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
