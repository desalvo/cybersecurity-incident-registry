"""Ordered schema upgrades with a fail-closed, transactionally staged ledger.

The core and SQLite DB-API adapter deliberately import only the standard
library. Runtime SQLAlchemy imports are lazy so the ledger contract can be
tested independently of Flask and the application's dependency graph.

Schema revision IDs are independent of the functional application version.
Append a new ID and its immutable, idempotent callback for each later change;
never rename, reorder or replace a published revision. The initial bridge
retains the existing migrations for installations that predate this ledger.

This module never commits. Schema callbacks can contain existing DDL code that
commits separately; therefore failure can leave partial DDL, but never a
successful revision marker. Such callbacks MUST be safe to retry. After all
callbacks and model validation, the caller stages the ledger in the SAME
transaction as bootstrap data, then commits that transaction once.

Callers must serialize upgrades (the application's PostgreSQL bootstrap lock)
and run the read-only compatibility preflight before restore recovery writes.
"""
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
import re
from typing import Protocol


LEDGER_TABLE = "cir_schema_migrations"
SCHEMA_REVISIONS = ("20261122_01_legacy_bridge", "20261127_02_support_tickets")
_LEDGER_COLUMNS = frozenset({"position", "revision_id", "applied_at"})
_REVISION_ID = re.compile(r"[a-z0-9][a-z0-9_.-]{0,159}")
_CREATE_LEDGER = """CREATE TABLE cir_schema_migrations (
    position INTEGER NOT NULL PRIMARY KEY CHECK (position > 0),
    revision_id VARCHAR(160) NOT NULL UNIQUE,
    applied_at VARCHAR(40) NOT NULL
)"""
_READ_LEDGER = (
    "SELECT position, revision_id, applied_at "
    "FROM cir_schema_migrations ORDER BY position ASC"
)


class SchemaCompatibilityError(RuntimeError):
    """The stored schema history is invalid or newer than this application."""


class MigrationExecutionError(RuntimeError):
    """An idempotent schema callback failed before success could be recorded."""


@dataclass(frozen=True)
class LedgerSnapshot:
    exists: bool
    rows: tuple


@dataclass(frozen=True)
class SchemaPlan:
    revision_ids: tuple[str, ...]
    applied_ids: tuple[str, ...]
    pending_ids: tuple[str, ...]
    ledger_exists: bool

    @property
    def status(self) -> str:
        """no-ledger: legacy/fresh; baseline: known prefix; current: all known."""
        if not self.ledger_exists:
            return "no-ledger"
        return "baseline" if self.pending_ids else "current"


@dataclass(frozen=True)
class CompletedUpgrade:
    """Callbacks completed; markers remain uncommitted until the caller commits."""
    plan: SchemaPlan
    completed_ids: tuple[str, ...]


class LedgerStore(Protocol):
    def read_snapshot(self) -> LedgerSnapshot: ...
    def begin_staging(self) -> None: ...
    def create_ledger(self) -> None: ...
    def insert_revision(self, position: int, revision_id: str, applied_at: str) -> None: ...


def _registry(revision_ids: Sequence[str]) -> tuple[str, ...]:
    if not isinstance(revision_ids, Sequence) or isinstance(revision_ids, (str, bytes)):
        raise ValueError("Schema revision registry must be an ordered sequence of IDs")
    ids = tuple(revision_ids)
    if not ids or any(not isinstance(value, str) or not _REVISION_ID.fullmatch(value)
                      for value in ids):
        raise ValueError("Schema revision registry contains an invalid ID or is empty")
    if len(set(ids)) != len(ids):
        raise ValueError("Schema revision registry contains duplicate IDs")
    return ids


def _plan(snapshot: LedgerSnapshot, revision_ids: Sequence[str]) -> SchemaPlan:
    ids = _registry(revision_ids)
    if not snapshot.exists and snapshot.rows:
        raise SchemaCompatibilityError("Schema ledger rows exist without a ledger table")
    applied = []
    for expected_position, row in enumerate(snapshot.rows, start=1):
        if len(row) != 3:
            raise SchemaCompatibilityError("Schema ledger row has an invalid shape")
        position, revision_id, applied_at = row
        # Do not coerce strings, floats or booleans to integers. Ambiguous
        # history must never be silently accepted or repaired on startup.
        if type(position) is not int or position != expected_position:
            raise SchemaCompatibilityError(
                "Schema ledger positions must be consecutive integers starting at 1")
        if not isinstance(revision_id, str) or not _REVISION_ID.fullmatch(revision_id):
            raise SchemaCompatibilityError("Schema ledger contains an invalid revision ID")
        if revision_id in applied:
            raise SchemaCompatibilityError("Schema ledger contains a duplicate revision ID")
        if expected_position > len(ids) or revision_id not in ids:
            raise SchemaCompatibilityError(
                f"Schema revision {revision_id!r} is unknown to this application; "
                "use a compatible newer application, do not downgrade")
        if revision_id != ids[expected_position - 1]:
            raise SchemaCompatibilityError(
                "Schema ledger is not the exact known revision prefix "
                f"at position {expected_position}")
        if not isinstance(applied_at, str) or not applied_at.strip():
            raise SchemaCompatibilityError("Schema ledger has an invalid application timestamp")
        applied.append(revision_id)
    return SchemaPlan(ids, tuple(applied), ids[len(applied):], snapshot.exists)


def plan_upgrade(store: LedgerStore,
                 revision_ids: Sequence[str] = SCHEMA_REVISIONS) -> SchemaPlan:
    """Read and validate the entire ledger without creating or modifying it."""
    ids = _registry(revision_ids)
    return _plan(store.read_snapshot(), ids)


def _run_callbacks(plan: SchemaPlan,
                   callbacks: Mapping[str, Callable[[], None]]) -> CompletedUpgrade:
    if not isinstance(callbacks, Mapping) or set(callbacks) != set(plan.revision_ids):
        raise ValueError("Schema callbacks must match the complete ordered revision registry")
    if any(not callable(callbacks[revision_id]) for revision_id in plan.revision_ids):
        raise ValueError("Every schema revision must have a callable implementation")
    for revision_id in plan.pending_ids:
        try:
            callbacks[revision_id]()
        except Exception as exc:
            raise MigrationExecutionError(
                f"Schema migration {revision_id} failed; no successful revision was recorded") from exc
    return CompletedUpgrade(plan, plan.pending_ids)


def apply_upgrade(store: LedgerStore,
                  callbacks: Mapping[str, Callable[[], None]],
                  revision_ids: Sequence[str] = SCHEMA_REVISIONS) -> CompletedUpgrade:
    """Validate before the first callback; return only after every callback passes.

    No ledger table or marker is written here. Bootstrap data and required
    schema validation must still succeed before calling ``stage_upgrade``.
    """
    return _run_callbacks(plan_upgrade(store, revision_ids), callbacks)


def stage_upgrade(store: LedgerStore, completed: CompletedUpgrade) -> None:
    """Stage success markers, without committing or recording partial success.

    The caller must rollback its transaction on ANY error, including later
    bootstrap/commit errors. Existing current histories take a read-only path.
    """
    if not isinstance(completed, CompletedUpgrade):
        raise TypeError("Only a completed schema upgrade can be staged")
    plan = completed.plan
    if completed.completed_ids != plan.pending_ids:
        raise SchemaCompatibilityError("Cannot stage an incomplete schema upgrade")
    current = plan_upgrade(store, plan.revision_ids)
    if current != plan:
        raise SchemaCompatibilityError(
            "Schema history changed during upgrade; rollback and retry under the bootstrap lock")
    if not completed.completed_ids:
        return
    store.begin_staging()
    # Check again after beginning the staging transaction. Runtime PostgreSQL
    # callers also hold the bootstrap advisory lock across this entire process.
    if plan_upgrade(store, plan.revision_ids) != plan:
        raise SchemaCompatibilityError("Schema history changed before markers could be staged")
    if not plan.ledger_exists:
        store.create_ledger()
    timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for position, revision_id in enumerate(completed.completed_ids,
                                           start=len(plan.applied_ids) + 1):
        store.insert_revision(position, revision_id, timestamp)


def validate_schema_shape(actual: Mapping[str, Sequence[str]],
                          required: Mapping[str, Sequence[str]]) -> None:
    """Require current model tables/columns while retaining legacy extra data."""
    missing_tables = sorted(set(required) - set(actual))
    missing_columns = {
        table: sorted(set(required[table]) - set(actual[table]))
        for table in sorted(set(required) & set(actual))
        if set(required[table]) - set(actual[table])
    }
    if missing_tables or missing_columns:
        parts = []
        if missing_tables:
            parts.append("missing tables: " + ", ".join(missing_tables))
        if missing_columns:
            parts.append("missing columns: " + "; ".join(
                table + ".[" + ", ".join(columns) + "]"
                for table, columns in missing_columns.items()))
        raise SchemaCompatibilityError("Schema validation failed: " + "; ".join(parts))


class SQLiteLedgerStore:
    """Standard-library SQLite DB-API adapter; transaction belongs to caller."""

    def __init__(self, connection):
        self.connection = connection

    def read_snapshot(self) -> LedgerSnapshot:
        import sqlite3
        try:
            row = self.connection.execute(
                "SELECT name, type FROM sqlite_master WHERE name = ? COLLATE NOCASE", (LEDGER_TABLE,)
            ).fetchone()
            if row is None:
                return LedgerSnapshot(False, ())
            if row[0] != LEDGER_TABLE:
                raise SchemaCompatibilityError("Schema ledger identifier is not canonical")
            if row[1] != "table":
                raise SchemaCompatibilityError("Schema ledger must be a physical table")
            columns = {row[1] for row in self.connection.execute(
                "PRAGMA table_info(cir_schema_migrations)").fetchall()}
            if not _LEDGER_COLUMNS <= columns:
                raise SchemaCompatibilityError("Schema ledger is missing required columns")
            rows = tuple(tuple(row) for row in self.connection.execute(_READ_LEDGER).fetchall())
            return LedgerSnapshot(True, rows)
        except sqlite3.DatabaseError as exc:
            raise SchemaCompatibilityError("Cannot safely read the schema migration ledger") from exc

    def begin_staging(self) -> None:
        # sqlite3's default legacy transaction mode does not BEGIN for DDL.
        # Starting explicitly keeps the new ledger table and markers rollbackable.
        if getattr(self.connection, "autocommit", False) is True:
            raise SchemaCompatibilityError("Schema markers require a caller-managed transaction")
        if not self.connection.in_transaction:
            self.connection.execute("BEGIN")

    def create_ledger(self) -> None:
        self.connection.execute(_CREATE_LEDGER)

    def insert_revision(self, position: int, revision_id: str, applied_at: str) -> None:
        self.connection.execute(
            "INSERT INTO cir_schema_migrations (position, revision_id, applied_at) VALUES (?, ?, ?)",
            (position, revision_id, applied_at),
        )


class SQLAlchemyLedgerStore:
    """Lazy adapter for an existing SQLAlchemy Connection or ORM Session.

    Never pass an Engine here: runtime wrappers open read connections explicitly,
    and staging is deliberately bound to the caller's Session transaction.
    """

    def __init__(self, executor):
        from sqlalchemy import inspect, text
        self.executor = executor
        self.connection = executor if hasattr(executor, "exec_driver_sql") else executor.connection()
        self._inspect = inspect
        self._text = text

    def read_snapshot(self) -> LedgerSnapshot:
        from sqlalchemy.exc import SQLAlchemyError
        try:
            inspector = self._inspect(self.connection)
            tables = set(inspector.get_table_names())
            if LEDGER_TABLE not in tables:
                if any(name.casefold() == LEDGER_TABLE for name in tables):
                    raise SchemaCompatibilityError("Schema ledger identifier is not canonical")
                if inspector.has_table(LEDGER_TABLE):
                    raise SchemaCompatibilityError("Schema ledger must be a physical table")
                return LedgerSnapshot(False, ())
            columns = {column["name"] for column in inspector.get_columns(LEDGER_TABLE)}
            if not _LEDGER_COLUMNS <= columns:
                raise SchemaCompatibilityError("Schema ledger is missing required columns")
            rows = tuple(tuple(row) for row in self.executor.execute(self._text(_READ_LEDGER)).all())
            return LedgerSnapshot(True, rows)
        except SQLAlchemyError as exc:
            raise SchemaCompatibilityError("Cannot safely read the schema migration ledger") from exc

    def begin_staging(self) -> None:
        # Session.connection() returns the connection in its transaction; no
        # separate engine.begin()/commit() is allowed for successful markers.
        # For SQLite, ensure its DB-API transaction exists before ledger DDL.
        raw = self.connection.connection.driver_connection
        if getattr(raw, "autocommit", False) is True:
            raise SchemaCompatibilityError("Schema markers require a caller-managed transaction")
        if self.connection.dialect.name == "sqlite":
            if not raw.in_transaction:
                self.connection.exec_driver_sql("BEGIN")

    def create_ledger(self) -> None:
        self.executor.execute(self._text(_CREATE_LEDGER))

    def insert_revision(self, position: int, revision_id: str, applied_at: str) -> None:
        self.executor.execute(self._text(
            "INSERT INTO cir_schema_migrations (position, revision_id, applied_at) "
            "VALUES (:position, :revision_id, :applied_at)"),
            {"position": position, "revision_id": revision_id, "applied_at": applied_at},
        )


def assert_schema_supported(engine,
                            revision_ids: Sequence[str] = SCHEMA_REVISIONS) -> SchemaPlan:
    """Read-only runtime preflight; call before any restore/bootstrap mutation."""
    with engine.connect() as connection:
        return plan_upgrade(SQLAlchemyLedgerStore(connection), revision_ids)


def prepare_schema_upgrade(engine,
                           callbacks: Mapping[str, Callable[[], None]],
                           revision_ids: Sequence[str] = SCHEMA_REVISIONS) -> CompletedUpgrade:
    """Recheck under the bootstrap lock, then apply only pending schema steps."""
    # Release this read connection before callbacks acquire their own DDL
    # connection; this also avoids exhausting small connection pools.
    plan = assert_schema_supported(engine, revision_ids)
    return _run_callbacks(plan, callbacks)


def stage_schema_upgrade(session, completed: CompletedUpgrade) -> None:
    """Stage markers in the final bootstrap Session; caller owns commit/rollback."""
    # Ledger preflight must not flush unrelated dirty bootstrap rows.
    # The caller commits them together with any newly staged migration markers.
    with session.no_autoflush:
        stage_upgrade(SQLAlchemyLedgerStore(session), completed)


def validate_model_schema(engine, metadata) -> None:
    """Read-only required model table/column validation, with lazy SQLAlchemy."""
    from sqlalchemy import inspect
    actual, required = {}, {}
    with engine.connect() as connection:
        inspector = inspect(connection)
        tables_by_schema = {}
        for table in metadata.tables.values():
            if table.schema not in tables_by_schema:
                tables_by_schema[table.schema] = set(inspector.get_table_names(schema=table.schema))
            required[table.fullname] = tuple(column.name for column in table.columns)
            if table.name in tables_by_schema[table.schema]:
                actual[table.fullname] = tuple(column["name"] for column in
                                               inspector.get_columns(table.name, schema=table.schema))
    validate_schema_shape(actual, required)
