"""System metadata: what bots exist, where every figure comes from, how much of
each field is actually populated, and how fresh the extract is.

These four routes are the provenance page. They are the reason a leadership
audience can be shown a count of 100 without being misled into reading it as a
period total. Panel ids here are ``META-*`` rather than ``P-xx``: the reference
dashboard renders these as a footer strip rather than a numbered panel, so there
is no P-id to inherit.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from app.core.envelope import envelope
from app.services import business

router = APIRouter(prefix="/api/meta", tags=["meta"])


@router.get("/bots")
def bots() -> dict[str, Any]:
    """Every bot on the platform, instrumented or not."""
    payload = business.list_bots()
    return envelope(
        payload, panel_id="META-BOTS", population="ALL", basis=payload["basis"]
    )


@router.get("/populations")
def populations() -> dict[str, Any]:
    """The three extracts behind every business figure, with their caveats."""
    payload = business.list_populations()
    return envelope(
        payload, panel_id="META-POPULATIONS", population="ALL", basis=payload["basis"]
    )


@router.get("/coverage")
def coverage() -> dict[str, Any]:
    """What fraction of records actually carry each field, within page 1."""
    payload = business.coverage()
    return envelope(
        payload, panel_id="META-COVERAGE", population="B", basis=payload["basis"]
    )


@router.get("/freshness")
def freshness() -> dict[str, Any]:
    """Latest ETL run per source, and when the next one is due."""
    payload = business.freshness()
    return envelope(
        payload, panel_id="META-FRESHNESS", population="ALL", basis=payload["basis"]
    )
