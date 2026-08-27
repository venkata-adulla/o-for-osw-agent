"""Cruise lines and ships -- population B.

Both panels are raw counts with no sailing or passenger divisor, which means the
biggest partner always ranks worst. That caveat rides along in the envelope
rather than being left to the reader.
"""
from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, Query

from app.core.envelope import envelope
from app.services import business

router = APIRouter(prefix="/api/lines", tags=["lines"])


@router.get("/contacts")
def contacts(
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
) -> dict[str, Any]:
    """P-09 -- which partners generate the most guest contact."""
    payload = business.line_contacts(date_from=date_from, date_to=date_to)
    return envelope(payload, panel_id="P-09", population="B", basis=payload["basis"])


@router.get("/ships")
def ships(
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
) -> dict[str, Any]:
    """Contacts by ship. Free-text ship names, so also a naming-gap panel."""
    payload = business.ships(date_from=date_from, date_to=date_to)
    return envelope(payload, panel_id="SHIPS", population="B", basis=payload["basis"])


@router.get("/mood")
def mood(
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
) -> dict[str, Any]:
    """P-13 -- how happy guests are when they reach us."""
    payload = business.guest_mood(date_from=date_from, date_to=date_to)
    return envelope(
        payload,
        panel_id="P-13",
        population="B",
        basis=payload["basis"],
        extra_notes=payload.get("extra_notes"),
    )
