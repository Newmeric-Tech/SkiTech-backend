"""
Safe error summaries - app/utils/safe_errors.py

str() of a SQLAlchemy error carries the SQL statement, its bound parameters
and Postgres' DETAIL line ("Failing row contains (...)"), so on the
channel-manager sync path it would leak guest names, emails and phones into
integrations.error_message, sync_logs.error_message and the logs.
safe_error_summary() keeps only what is safe to store and print.
"""
from typing import Optional

import httpx
from sqlalchemy.exc import StatementError

MAX_SUMMARY = 200


def _postgres_error(err: BaseException) -> Optional[BaseException]:
    """The asyncpg exception behind a SQLAlchemy error, if any. It carries the
    structured sqlstate/table/column/constraint fields."""
    seen = set()
    node: Optional[BaseException] = err
    while node is not None and id(node) not in seen:
        seen.add(id(node))
        if type(node).__module__.startswith("asyncpg"):
            return node
        node = getattr(node, "orig", None) or node.__cause__
    return None


def safe_error_summary(err: BaseException) -> str:
    """Exception class plus a short summary with no bound parameters or row values.

    - Database errors: class, sqlstate and the table/column/constraint names
      only. Postgres message text is dropped because some messages quote the
      offending value (e.g. 'invalid input syntax for type integer: "..."').
    - Plain Exception (raised by our adapters with provider HTTP status text)
      and httpx transport errors: first line of the message, capped.
    - Anything else (ValueError, KeyError, ...) can echo provider data, so
      only the class name is kept.
    """
    pg = _postgres_error(err)
    if pg is not None or isinstance(err, StatementError):
        source = pg if pg is not None else err
        parts = [type(source).__name__]
        for label, attr in (("sqlstate", "sqlstate"), ("table", "table_name"),
                            ("column", "column_name"), ("constraint", "constraint_name")):
            value = getattr(source, attr, None)
            if value:
                parts.append(f"{label}={value}")
        return f"Database error: {' '.join(parts)}"[:MAX_SUMMARY]

    if type(err) is Exception or isinstance(err, httpx.HTTPError):
        lines = str(err).splitlines()
        if lines and lines[0].strip():
            return f"{type(err).__name__}: {lines[0].strip()}"[:MAX_SUMMARY]

    return type(err).__name__
