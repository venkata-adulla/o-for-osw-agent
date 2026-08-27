"""Connection pooling and query helpers.

One rule, inherited from the previous build because it was learned the hard way:
`timestamptz BETWEEN a AND b` silently drops same-day rows, so every timestamp
filter uses `>= from AND < to + 1 day`. `exclusive_upper()` is the only place
that boundary is expressed.
"""
from __future__ import annotations

import logging
from contextlib import contextmanager
from datetime import date, timedelta
from typing import Any, Iterator, Sequence

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from app.core.config import settings

log = logging.getLogger(__name__)

_pool: ConnectionPool | None = None

MAX_DATE_RANGE_DAYS = 400
DEFAULT_DATE_RANGE_DAYS = 30


def get_pool() -> ConnectionPool:
    """Built lazily so the container can start before Postgres is accepting."""
    global _pool
    if _pool is None:
        _pool = ConnectionPool(
            conninfo=settings.dsn,
            min_size=1,
            max_size=settings.postgres_pool_max,
            open=True,
            kwargs={"row_factory": dict_row, "options": "-c search_path=osw,public"},
        )
    return _pool


@contextmanager
def cursor() -> Iterator[Any]:
    """Read-path cursor. Rolls back on exit so no transaction is left open."""
    with get_pool().connection() as conn:
        with conn.cursor() as cur:
            yield cur
        conn.rollback()


def fetch_all(sql: str, params: Sequence[Any] | dict[str, Any] | None = None) -> list[dict]:
    with cursor() as cur:
        cur.execute(sql, params)
        return list(cur.fetchall())


def fetch_one(sql: str, params: Sequence[Any] | dict[str, Any] | None = None) -> dict | None:
    with cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchone()


def fetch_value(sql: str, params: Sequence[Any] | dict[str, Any] | None = None, default: Any = None) -> Any:
    row = fetch_one(sql, params)
    if not row:
        return default
    first = next(iter(row.values()), default)
    return default if first is None else first


def exclusive_upper(date_to: date) -> date:
    """The upper bound to use with `<` for a timestamptz column."""
    return date_to + timedelta(days=1)


def validate_date_range(date_from: date | None, date_to: date | None) -> tuple[date, date]:
    """Defaults, swaps a reversed pair, and caps the span."""
    today = date.today()
    upper = date_to or today
    lower = date_from or (upper - timedelta(days=DEFAULT_DATE_RANGE_DAYS))
    if lower > upper:
        lower, upper = upper, lower
    if (upper - lower).days > MAX_DATE_RANGE_DAYS:
        lower = upper - timedelta(days=MAX_DATE_RANGE_DAYS)
    return lower, upper


def healthy() -> bool:
    try:
        return fetch_value("SELECT 1") == 1
    except Exception:  # pragma: no cover - surfaced through /health
        log.exception("database health check failed")
        return False
