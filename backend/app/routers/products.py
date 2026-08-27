"""Products and services -- population B.

P-16 is a scope finding, not a demand finding: the bot only runs the returns and
billing flows, so ``unused_flows`` names what the intake form offers but the bot
never produced. P-44 is the cleanest taxonomy on the screen -- every return
carries exactly three tags, so both breakdowns sum to the return total.
"""
from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, Query

from app.core.envelope import envelope
from app.services import business

router = APIRouter(prefix="/api/products", tags=["products"])


@router.get("/inquiry-types")
def inquiry_types(
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
) -> dict[str, Any]:
    """P-16 -- which flow the guest needs."""
    payload = business.inquiry_types(date_from=date_from, date_to=date_to)
    return envelope(payload, panel_id="P-16", population="B", basis=payload["basis"])


@router.get("/returns")
def returns(
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
) -> dict[str, Any]:
    """P-44 -- inside the returns flow: ordered how, sent back why?"""
    payload = business.returns_breakdown(date_from=date_from, date_to=date_to)
    return envelope(
        payload,
        panel_id="P-44",
        population="B",
        basis=payload["basis"],
        extra_notes=payload.get("extra_notes"),
    )
