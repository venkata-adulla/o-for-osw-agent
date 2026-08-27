"""Customers -- population B.

One panel, one question: how often does a guest have to ask the bot twice? The
figure is a floor, not a ceiling. Repeat contact arriving by email or phone is
invisible here, and the ticket a follow-up points back to is usually older than
this page.
"""
from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, Query

from app.core.envelope import envelope, notes_for
from app.services import business

router = APIRouter(prefix="/api/customers", tags=["customers"])


@router.get("/repeat")
def repeat(
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
) -> dict[str, Any]:
    """P-30 / P-48 -- guests who came back."""
    payload = business.repeat_guests(date_from=date_from, date_to=date_to)
    return envelope(
        payload,
        panel_id="P-30",
        population="B",
        basis=payload["basis"],
        # P-30 and P-48 are one card pair in the reference; both note sets apply.
        extra_notes=notes_for("P-48"),
    )
