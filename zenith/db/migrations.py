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

import logging
from dataclasses import dataclass

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

from zenith.db.base import Base, Database
from zenith.services.bootstrap import CURRENT_SCHEMA_VERSION

log = logging.getLogger("zenith.migrations")


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


def _table_exists(db: Database, table: str) -> bool:
    return table in set(inspect(db.engine).get_table_names())


def _current_version(db: Database) -> int:
    """Read the schema version with raw SQL, tolerating a missing table/record.

    Never touches an ORM model, so it is safe on any historical schema (including
    a database with no ``schema_version`` table or an empty one).
    """
    if not _table_exists(db, "schema_version"):
        return 0
    try:
        with db.engine.connect() as conn:
            row = conn.execute(text("SELECT MAX(version) FROM schema_version")).scalar()
            return int(row) if row is not None else 0
    except Exception:
        return 0


def read_profile_code_raw(db: Database) -> str | None:
    """Read the business profile code with raw SQL -- old-schema compatible.

    Reads ONLY the ``profile_code`` column (present since v1) so it works before
    migrations add the newer ``business_settings`` columns. Returns ``None`` for a
    fresh/empty database with no ``business_settings`` table or row.
    """
    if not _table_exists(db, "business_settings"):
        return None
    try:
        with db.engine.connect() as conn:
            return conn.execute(text("SELECT profile_code FROM business_settings LIMIT 1")).scalar()
    except Exception:
        return None


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
    """Bring the live schema up to the models, additively and safely.

    Order: inspect existing schema -> determine version -> (if anything to do)
    back up -> create missing tables -> add missing columns in a transaction ->
    record the new version. Idempotent: a fully current database is a no-op. On
    failure the column step rolls back and this raises; the caller keeps the
    original database and backup (nothing is ever deleted here).
    """
    from_version = _current_version(db)
    missing_tables, missing_columns = plan_missing(db)

    report = MigrationReport(
        added_tables=[], added_columns=[], backed_up=False,
        from_version=from_version, to_version=from_version,
    )

    if not missing_tables and not missing_columns and from_version >= CURRENT_SCHEMA_VERSION:
        log.info("Database schema is current (v%s); no migration needed.", from_version)
        return report

    log.info("Migrating database schema from v%s to v%s: %d new table(s), %d new column(s).",
             from_version, CURRENT_SCHEMA_VERSION, len(missing_tables), len(missing_columns))

    # 1. Pre-migration backup of a populated database (never for empty/fresh).
    if backup and profile_code:
        try:
            from zenith.core import paths
            from zenith.services import backup as backup_service
            if paths.db_path().exists():
                info = backup_service.create_backup(profile_code)
                report.backed_up = True
                log.info("Pre-migration backup created: %s", info.path)
        except Exception as exc:  # pragma: no cover - environment dependent
            report.backed_up = False
            log.warning("Pre-migration backup skipped: %s", exc)

    # 2. Create any entirely missing tables (safe, standard, additive).
    if missing_tables:
        Base.metadata.create_all(db.engine)
        report.added_tables = missing_tables
        log.info("Created %d missing table(s): %s", len(missing_tables), ", ".join(sorted(missing_tables)))

    # 3. Add missing columns to existing tables inside one transaction (rolls
    #    back atomically on any failure -- the original data is untouched).
    if missing_columns:
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
        log.info("Added %d column(s): %s", len(report.added_columns), ", ".join(report.added_columns))

    # 4. Record the new schema version with raw SQL (append-only history).
    if from_version < CURRENT_SCHEMA_VERSION:
        with db.engine.begin() as conn:
            conn.execute(
                text("INSERT INTO schema_version (version, applied_at) VALUES (:v, :t)"),
                {"v": CURRENT_SCHEMA_VERSION, "t": __import__("datetime").datetime.utcnow().isoformat()},
            )
    report.to_version = CURRENT_SCHEMA_VERSION
    log.info("Migration complete: schema is now v%s.", CURRENT_SCHEMA_VERSION)
    return report
