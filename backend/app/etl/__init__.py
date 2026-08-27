"""ETL package for O for OSW.

Two kinds of loader live here and they are deliberately kept apart:

*   ``seed_*``   -- the reference figures from ``docs/REFERENCE_PARITY.md``. These
    are literals on purpose. Every number a reviewer can point at on the old
    dashboards has to exist as a row, whether or not a raw extract is present.
*   ``load_*`` / ``derive_*`` -- real rows parsed out of the Kore.ai, Zendesk and
    transcript extracts mounted read-only at ``$OSW_DATA_ROOT`` (``/data``).

Shared plumbing (stage bookkeeping, the small parse helpers that more than one
loader needs) lives in this module so the loaders stay readable.

Idempotency rule for the whole package: a stage may be re-run any number of
times and must leave the database in exactly the same state. Tables with a
natural key use ``INSERT ... ON CONFLICT DO UPDATE``. Tables whose only key is a
``serial`` (``panel_notes``, ``nlu_events``, ``metric_series`` ...) are refreshed
with a scoped ``DELETE`` followed by an ``INSERT`` -- safe because for each of
those tables exactly one stage in this package is the writer.
"""
from __future__ import annotations

import logging
import re
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any, Iterable, Iterator, Sequence

from app.core.db import get_pool

log = logging.getLogger("app.etl")

__all__ = [
    "StageResult",
    "chunked",
    "clean",
    "log",
    "parse_amount",
    "parse_date_loose",
    "parse_iso",
    "parse_response_time_ms",
    "run_stage",
    "slug",
    "stage_record",
]


# ---------------------------------------------------------------------------
# Stage bookkeeping
# ---------------------------------------------------------------------------
@dataclass
class StageResult:
    """What one ETL stage did. ``rows`` is what lands in ``etl_runs.rows_loaded``."""

    source: str
    rows: int = 0
    detail: str = ""
    warnings: list[str] = field(default_factory=list)
    tables: dict[str, int] = field(default_factory=dict)

    def add(self, table: str, count: int) -> None:
        """Record ``count`` rows written to ``table`` and add them to the total."""
        self.tables[table] = self.tables.get(table, 0) + count
        self.rows += count

    def warn(self, message: str) -> None:
        """A missing raw file or an unparseable row never aborts a run."""
        self.warnings.append(message)
        log.warning("[%s] %s", self.source, message)

    def summary(self) -> str:
        parts = ", ".join(f"{name}={count}" for name, count in sorted(self.tables.items()))
        text = f"{self.rows} rows"
        if parts:
            text = f"{text} ({parts})"
        if self.warnings:
            text = f"{text} · {len(self.warnings)} warning(s)"
        if self.detail:
            text = f"{text} · {self.detail}"
        return text


@contextmanager
def run_stage(source: str, detail: str = "") -> Iterator[StageResult]:
    """Write the ``etl_runs`` row for one stage: running -> success | failed.

    The bookkeeping uses its own short-lived connection and commits immediately,
    so a stage that blows up half way through still leaves a *failed* audit row
    behind even though its own data transaction was rolled back.
    """
    result = StageResult(source=source, detail=detail)
    pool = get_pool()

    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO etl_runs (source, detail, status, started_at)
                VALUES (%s, %s, 'running', now())
                RETURNING id
                """,
                (source, detail),
            )
            row = cur.fetchone()
            run_id = row["id"] if isinstance(row, dict) else row[0]
        conn.commit()

    log.info("[%s] start", source)
    try:
        yield result
    except Exception as exc:  # noqa: BLE001 - recorded, re-raised by the caller
        with pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE etl_runs
                       SET status = 'failed',
                           finished_at = now(),
                           rows_loaded = %s,
                           error_message = %s
                     WHERE id = %s
                    """,
                    (result.rows, f"{type(exc).__name__}: {exc}"[:2000], run_id),
                )
            conn.commit()
        log.exception("[%s] FAILED", source)
        raise
    else:
        note = result.detail
        if result.warnings:
            note = f"{note} | warnings: {'; '.join(result.warnings)}"[:2000] if note else (
                f"warnings: {'; '.join(result.warnings)}"[:2000]
            )
        with pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE etl_runs
                       SET status = 'success',
                           finished_at = now(),
                           rows_loaded = %s,
                           detail = %s
                     WHERE id = %s
                    """,
                    (result.rows, note, run_id),
                )
            conn.commit()
        log.info("[%s] done -- %s", source, result.summary())


def stage_record(source: str, status: str, message: str) -> None:
    """Record a stage that never really started (e.g. its raw folder is absent)."""
    with get_pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO etl_runs (source, detail, status, started_at, finished_at, rows_loaded)
                VALUES (%s, %s, %s, now(), now(), 0)
                """,
                (source, message, status),
            )
        conn.commit()


# ---------------------------------------------------------------------------
# Small parse helpers shared by more than one loader
# ---------------------------------------------------------------------------

# Values the OSW form and the bot both use to mean "the guest did not tell us".
# They are *not* data, so they must not become a cruise line called "N/A".
PLACEHOLDERS = {
    "",
    "-",
    "--",
    "n/a",
    "na",
    "n.a.",
    "none",
    "null",
    "nil",
    "not specified",
    "not provided",
    "not available",
    "not mentioned",
    "unknown",
    "unspecified",
    "tbd",
}


def clean(value: Any) -> str | None:
    """Trim, collapse whitespace, and map the placeholder vocabulary to NULL."""
    if value is None:
        return None
    text = re.sub(r"\s+", " ", str(value)).strip()
    text = text.strip("*").strip()
    if text.lower() in PLACEHOLDERS:
        return None
    return text or None


_ISO_TRAILING_Z = re.compile(r"Z$")


def parse_iso(value: Any) -> datetime | None:
    """Parse the ISO-8601 stamps Kore.ai and Zendesk emit (both use a ``Z`` suffix)."""
    text = clean(value)
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(_ISO_TRAILING_Z.sub("+00:00", text))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


_DATE_FORMATS = (
    "%Y-%m-%d",
    "%m/%d/%Y",
    "%d/%m/%Y",
    "%Y/%m/%d",
    "%m-%d-%Y",
    "%d %b %Y",
    "%b %d %Y",
    "%d %B %Y",
    "%B %d %Y",
)


def parse_date_loose(value: Any) -> date | None:
    """Dates in the ticket markdown arrive as ``2026-05-11`` *and* ``05/18/2026``.

    Ambiguous day/month pairs are read US-first because the form is US-hosted;
    a value that only parses as day-first still parses rather than being dropped.
    """
    text = clean(value)
    if not text:
        return None
    text = text.split(" ")[0] if re.match(r"^\d{4}-\d{2}-\d{2}[ T]", text) else text
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    stamp = parse_iso(text)
    return stamp.date() if stamp else None


_AMOUNT_RE = re.compile(r"-?\d[\d,]*(?:\.\d+)?")


def parse_amount(value: Any) -> float | None:
    """``$1,234.56`` / ``USD 396.00`` / ``396`` -> 1234.56 / 396.0 / 396.0."""
    text = clean(value)
    if not text:
        return None
    match = _AMOUNT_RE.search(text.replace(" ", ""))
    if not match:
        return None
    try:
        return float(match.group(0).replace(",", ""))
    except ValueError:
        return None


# Kore.ai reports node timings as prose, e.g. "717 milliseconds" or "1.2 seconds".
# It is a STRING in the API payload, so every consumer has to parse it; doing it
# in one place keeps the unit handling honest.
_DURATION_RE = re.compile(
    r"(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>milliseconds?|millis|msecs?|ms|seconds?|secs?|s|minutes?|mins?|m)\b",
    re.IGNORECASE,
)
_UNIT_TO_MS = {
    "ms": 1.0,
    "msec": 1.0,
    "msecs": 1.0,
    "milli": 1.0,
    "millis": 1.0,
    "millisecond": 1.0,
    "milliseconds": 1.0,
    "s": 1000.0,
    "sec": 1000.0,
    "secs": 1000.0,
    "second": 1000.0,
    "seconds": 1000.0,
    "m": 60_000.0,
    "min": 60_000.0,
    "mins": 60_000.0,
    "minute": 60_000.0,
    "minutes": 60_000.0,
}


def parse_response_time_ms(value: Any) -> int | None:
    """``"717 milliseconds"`` -> ``717``. Returns None when nothing is parseable."""
    if value is None:
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return int(round(float(value)))
    text = str(value).strip()
    if not text:
        return None
    match = _DURATION_RE.search(text)
    if not match:
        # A bare number with no unit is assumed to already be milliseconds,
        # which is what every numeric Kore.ai latency field uses.
        try:
            return int(round(float(text)))
        except ValueError:
            return None
    factor = _UNIT_TO_MS.get(match.group("unit").lower(), 1.0)
    return int(round(float(match.group("value")) * factor))


_SLUG_RE = re.compile(r"[^a-z0-9]+")


def slug(value: str, max_len: int = 48) -> str:
    return _SLUG_RE.sub("-", str(value).lower()).strip("-")[:max_len] or "x"


def chunked(rows: Sequence[Any], size: int = 500) -> Iterator[Sequence[Any]]:
    for start in range(0, len(rows), size):
        yield rows[start : start + size]


def day_range(first: date, last: date) -> list[date]:
    return [first + timedelta(days=offset) for offset in range((last - first).days + 1)]


def unique(items: Iterable[Any]) -> list[Any]:
    """Order-preserving de-duplication."""
    seen: set[Any] = set()
    out: list[Any] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out
