"""Tickets and system health -- population B, the bot-raised cohort.

``/activity`` is the one route here that deliberately mixes populations: the
Kore.ai page and the Zendesk export cover different, barely overlapping days,
and putting them on one axis is the only way to see that the two systems agree
on the single day they share. Days absent from an extract come back as ``null``,
never zero.
"""
from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, Query

from app.core.config import settings
from app.core.envelope import envelope, notes_for
from app.services import business

router = APIRouter(prefix="/api/tickets", tags=["tickets"])


@router.get("/summary")
def summary(
    bot_id: str = Query(settings.default_bot_id),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
) -> dict[str, Any]:
    """P-45 still waiting, plus P-43 requests raised."""
    payload = business.ticket_summary(
        bot_id=bot_id, date_from=date_from, date_to=date_to
    )
    return envelope(
        payload,
        panel_id="P-45",
        population="B",
        basis=payload["basis"],
        extra_notes=notes_for("P-43"),
    )


@router.get("/status")
def status(
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
) -> dict[str, Any]:
    """Bot-raised tickets by Zendesk status."""
    payload = business.ticket_status(date_from=date_from, date_to=date_to)
    return envelope(payload, panel_id="P-45", population="B", basis=payload["basis"])


@router.get("/activity")
def activity(
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
) -> dict[str, Any]:
    """P-07 -- activity over time. Conversations against bot-raised tickets."""
    payload = business.activity(date_from=date_from, date_to=date_to)
    return envelope(payload, panel_id="P-07", population="A/B", basis=payload["basis"])


@router.get("/correlation")
def correlation(
    bot_id: str = Query(settings.default_bot_id),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
) -> dict[str, Any]:
    """P-43 -- does the link between the two systems hold?"""
    payload = business.conversation_ticket_correlation(
        bot_id=bot_id, date_from=date_from, date_to=date_to
    )
    return envelope(payload, panel_id="P-43", population="A", basis=payload["basis"])


@router.get("/backend-failures")
def backend_failures(
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
) -> dict[str, Any]:
    """Automation failures carried as tags on bot-raised tickets."""
    payload = business.backend_failures(date_from=date_from, date_to=date_to)
    return envelope(
        payload, panel_id="BACKEND-FAILURES", population="B", basis=payload["basis"]
    )


@router.get("/recent")
def recent(
    limit: int = Query(50, ge=1, le=business.MAX_PAGE_LIMIT),
    bot_raised: bool | None = Query(
        None,
        description="true for the bot-raised cohort only; omit for every ticket held",
    ),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
) -> dict[str, Any]:
    """The most recent tickets held, newest first."""
    payload = business.recent_tickets(
        limit=limit, bot_raised=bot_raised, date_from=date_from, date_to=date_to
    )
    return envelope(
        payload,
        panel_id="TICKETS-RECENT",
        population="B" if bot_raised else "ALL",
        basis=payload["basis"],
    )
