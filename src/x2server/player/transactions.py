"""Nested SQLite writes that release locks even when the final commit fails."""
from contextlib import contextmanager
import logging
import sqlite3
import time
import uuid

LOGGER = logging.getLogger("x2.database")


@contextmanager
def transaction(db):
    """Own only this scope; an inner operation must never commit its caller."""
    nested = db.in_transaction
    marker = "operation_" + uuid.uuid4().hex
    db.execute("SAVEPOINT " + marker)
    started = time.monotonic()
    stage = "body"
    try:
        yield
        stage = "commit"
        # The outermost RELEASE commits and can fail with SQLITE_BUSY.
        db.execute("RELEASE " + marker)
    except BaseException as exc:
        if db.in_transaction:
            if nested:
                db.execute("ROLLBACK TO " + marker)
                db.execute("RELEASE " + marker)
            else:
                # A failed commit keeps the transaction (and its locks) alive.
                # ROLLBACK TO alone would keep that transaction open too.
                db.rollback()
        if isinstance(exc, sqlite3.DatabaseError):
            LOGGER.error("transaction failed stage=%s nested=%s elapsed=%.3fs sqlite_error=%s",
                         stage, nested, time.monotonic() - started,
                         getattr(exc, "sqlite_errorname", type(exc).__name__))
        raise


def is_database_busy(error):
    return isinstance(error, sqlite3.OperationalError) and (
        getattr(error, 'sqlite_errorcode', 0) & 255 in (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED)
        or str(error).lower() in ('database is locked', 'database table is locked'))
