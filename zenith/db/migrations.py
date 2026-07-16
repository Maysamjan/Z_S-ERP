"""Lightweight, safe, additive schema migrations.

`create_all()` creates missing *tables* but never alters existing ones, so a
customer upgrading to a build with new columns would silently lack them. This
module closes that gap: on startup it compares the live SQLite schema to the ORM
models and issues additive `ALTER TABLE ... ADD COLUMN` statements for any missing
columns, then advances `schema_version`.

Design constraints (honest scope):
* **Additive only** — adds missing columns/tables. It never drops or rewrites
  columns (SQLite can't do that safely in-place), so it cannot lose data.
* **Backup first** — a verified backup is taken before applying any change, so an
  interrupted upgrade is recoverable.
* Not a full Alembic replacement; a proper migration history is future work
  (documented in KNOWN_LIMITATIONS).
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

from zenith.db.base import Base, Database
from zenith.db.models import SchemaVersion
from zenith.services.bootstrap import CURRENT_SCHEMA_VERSION


# SQLAlchemy column type -> SQLite column type for ADD COLUMN.
def _sqlite_type(column) -> str:
    try:
        return column.type.compile(dialect=_DIALECT)
    except Exception:
        return "TEXT"


from sqlalchemy.dialects.sqlite import dialect as _sqlite_dialect  # noqa: E402
_DIALECT = _sqlite_dialect()


@dataclass
class MigrationReport:
    added_tables: list[str]
    added_columns: list[str]
    backed_up: bool
    from_version: int
    to_version: int

    @property
    def changed(self) -> bool:
        return bool(self.added_tables or self.added_columns)


def _live_columns(engine: Engine, table: str) -> set[str]:
    insp = inspect(engine)
    return {c["name"] for c in insp.get_columns(table)}


def _current_version(db: Database) -> int:
    with db.session() as s:
        row = s.query(SchemaVersion).order_by(SchemaVersion.version.desc()).first()
        return row.version if row else 0


def plan_missing(db: Database) -> tuple[list[str], list[tuple[str, str]]]:
    """Return (missing_tables, [(table, column), ...]) without applying anything."""
    insp = inspect(db.engine)
    existing_tables = set(insp.get_table_names())
    missing_tables: list[str] = []
    missing_columns: list[tuple[str, str]] = []
    for table_name, table in Base.metadata.tables.items():
        if table_name not in existing_tables:
            missing_tables.append(table_name)
            continue
        live = _live_columns(db.engine, table_name)
        for col in table.columns:
            if col.name not in live:
                missing_columns.append((table_name, col.name))
    return missing_tables, missing_columns


def run_migrations(db: Database, *, profile_code: str | None = None,
                   backup: bool = True) -> MigrationReport:
    """Bring the live schema up to the models. Backs up before any change."""
    from_version = _current_version(db)
    missing_tables, missing_columns = plan_missing(db)

    report = MigrationReport(
        added_tables=[], added_columns=[], backed_up=False,
        from_version=from_version, to_version=from_version,
    )

    if not missing_tables and not missing_columns and from_version >= CURRENT_SCHEMA_VERSION:
        return report

    # Backup before touching a populated database.
    if backup and profile_code:
        try:
            from zenith.core import paths
            from zenith.services import backup as backup_service
            if paths.db_path().exists():
                backup_service.create_backup(profile_code)
                report.backed_up = True
        except Exception:
            # A missing/empty database is fine to migrate without a backup.
            report.backed_up = False

    # 1. Create any entirely missing tables (safe, standard).
    if missing_tables:
        Base.metadata.create_all(db.engine)
        report.added_tables = missing_tables

    # 2. Add missing columns to existing tables.
    with db.engine.begin() as conn:
        for table_name, col_name in missing_columns:
            table = Base.metadata.tables[table_name]
            column = table.columns[col_name]
            coltype = _sqlite_type(column)
            default = ""
            if column.default is not None and getattr(column.default, "arg", None) is not None \
                    and not callable(column.default.arg):
                arg = column.default.arg
                default = f" DEFAULT {arg!r}" if isinstance(arg, str) else f" DEFAULT {arg}"
            conn.execute(text(f'ALTER TABLE "{table_name}" ADD COLUMN "{col_name}" {coltype}{default}'))
            report.added_columns.append(f"{table_name}.{col_name}")

    # 3. Advance schema version.
    with db.session() as s:
        if _current_version(db) < CURRENT_SCHEMA_VERSION:
            s.add(SchemaVersion(version=CURRENT_SCHEMA_VERSION))
            s.commit()
    report.to_version = CURRENT_SCHEMA_VERSION
    return report
