"""Where the raw extracts live, and how to read them.

The extracts sit in the *parent* folder of this repository and are mounted
read-only into the container at ``/data`` (``OSW_DATA_ROOT``). Several of them
have no file extension at all -- they are raw Postman response bodies saved with
the name of the request -- so every path is spelled out here rather than
discovered by glob. If a file is missing the loader logs a warning and carries
on: a partial extract set must still produce a usable database.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.etl import log

# ---------------------------------------------------------------------------
# Zendesk
# ---------------------------------------------------------------------------
# Page 1 of the prod search (345 tickets reported, 100 held). This is population
# B: the 28 bot-raised tickets on which every business ticket panel is computed.
ZENDESK_ALL_TICKETS = "Zendesk - All Tickets"
# A 23-ticket sandbox export. Same envelope shape, different Zendesk instance --
# its ticket ids (e.g. 7258) are the ones the Kore.ai TicketID session tag holds.
ZENDESK_TICKET_EXPORT = "Postman Downloads/Zendesk - Ticket export"

ZENDESK_FILES: tuple[str, ...] = (ZENDESK_ALL_TICKETS, ZENDESK_TICKET_EXPORT)

# ---------------------------------------------------------------------------
# Kore.ai
# ---------------------------------------------------------------------------
# Three session extracts. "Sessions History (all outcomes)" is the 100-row page 1
# that population A is built from; the two `getSessions` files are single-row and
# 100-row captures of the same API. Loading all three is safe because the loader
# keys on sessionId.
KORE_SESSION_FILES: tuple[str, ...] = (
    "Extracts Prod/Sessions History (all outcomes)",
    "Extracts Prod/Sessions History (filter by outcome)",
    "Postman Downloads/getSessions",
    "Extracts Prod/getSessions",
    "Postman Downloads/containmentType=selfService",
    "Postman Downloads/containmentType=dropOff",
    "Postman Downloads/containmentType=agent",
)

KORE_MESSAGE_FILES: tuple[str, ...] = (
    "Postman Downloads/getMessagesV2",
    "Extracts Prod/getMessagesV2",
    "Postman Downloads/getMessagesV2 - sessionid",
    "Postman Downloads/Conversation History V2 (with response-time latency)",
    "Extracts Prod/Conversation History V2 (messages)",
    "Extracts Prod/Conversation History V2 (with response-time latency)",
)

# (path, fallback NLU result when the record carries no NLAnalysis.result)
KORE_ANALYTICS_FILES: tuple[tuple[str, str], ...] = (
    ("Postman Downloads/getAnalytics - successintent", "successintent"),
    ("Postman Downloads/getAnalytics - failintent", "failintent"),
    ("Postman Downloads/getAnalytics - unhandledutterance", "unhandledUtterance"),
    ("Postman Downloads/getAnalytics", "successintent"),
    ("Extracts Prod/Get Analytics - successintent", "successintent"),
    ("Extracts Prod/Get Analytics - failintent", "failintent"),
    ("Extracts Prod/Get Analytics - unhandledutterance", "unhandledUtterance"),
)

# Per-node timings. The only real latency data we hold, and therefore the raw
# material for the derived spans (see derive_spans.py).
KORE_PERFORMANCE_FILES: tuple[str, ...] = (
    "Postman Downloads/Get Analytics - performance (per-node timing)",
    "Extracts Prod/Get Analytics - performance (per-node timing)",
)

KORE_CONTAINMENT_FILES: tuple[str, ...] = (
    "Postman Downloads/Containment Report - Poll Status",
    "Extracts Prod/Containment Report - Poll Status",
)


def data_root() -> Path:
    """``/data`` in the container, the repo's parent folder on a developer box."""
    return Path(settings.osw_data_root)


def resolve(relative: str) -> Path | None:
    """Absolute path for a raw file, or None (with a warning) when it is absent.

    Case-insensitive fallback: the extracts were captured on Windows and the
    container filesystem is case-sensitive, so a single wrong capital letter
    would otherwise silently drop a whole population.
    """
    candidate = data_root() / relative
    if candidate.exists():
        return candidate

    parent = candidate.parent
    if parent.is_dir():
        wanted = candidate.name.casefold()
        for entry in sorted(parent.iterdir()):
            if entry.name.casefold() == wanted:
                return entry
    log.warning("raw file not found, skipping: %s", candidate)
    return None


def load_json(relative: str) -> Any | None:
    """Read one raw extract as JSON. Never raises -- returns None and warns."""
    path = resolve(relative)
    if path is None:
        return None
    try:
        with path.open("r", encoding="utf-8-sig") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        log.warning("could not parse %s: %s", path, exc)
        return None


def available(relatives: tuple[str, ...]) -> list[str]:
    """Filter a tuple of relative paths down to the ones that actually exist."""
    return [rel for rel in relatives if (data_root() / rel).exists() or resolve(rel) is not None]
