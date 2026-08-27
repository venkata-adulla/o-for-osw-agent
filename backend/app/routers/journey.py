"""Guest journey -- the hand-reviewed chat-to-document chain and everything
hanging off it.

Population C throughout, except ``/durations`` which measures the Kore.ai
session page (population A). C is the only source that can trace a conversation
to a document at all: the Zendesk ticket API returns no attachments field, so
without the review sheets these panels could not exist.
"""
from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, Query

from app.core.config import settings
from app.core.envelope import envelope, notes_for
from app.services import business

router = APIRouter(prefix="/api/journey", tags=["journey"])


@router.get("/chain")
def chain() -> dict[str, Any]:
    """P-54 -- the six-stage chain, its callouts, and the same rows as a table."""
    payload = business.journey_chain()
    return envelope(payload, panel_id="P-54", population="C", basis=payload["basis"])


@router.get("/quit-reasons")
def quit_reasons() -> dict[str, Any]:
    """Which question ends the conversation."""
    payload = business.quit_reasons()
    return envelope(
        payload, panel_id="QUIT-REASONS", population="C", basis=payload["basis"]
    )


@router.get("/outcomes")
def outcomes() -> dict[str, Any]:
    """P-32 -- what the conversation produced, with the per-day review table."""
    payload = business.journey_outcomes()
    return envelope(
        payload,
        panel_id="P-32",
        population="C",
        basis=payload["basis"],
        # The by-day table is the "reviewed sessions by day" extension of P-07,
        # so its axis caveat travels with these figures too.
        extra_notes=notes_for("P-07"),
    )


@router.get("/enrichment")
def enrichment() -> dict[str, Any]:
    """P-55 -- did the guest's paperwork actually reach the ticket?"""
    payload = business.enrichment()
    return envelope(
        payload,
        panel_id="P-55",
        population="C",
        basis=payload["basis"],
        # "Why enrichment failed" is a sub-panel of P-55 in the reference; its
        # notes are carried here so the caveat travels with the figures.
        extra_notes=notes_for("ENRICHMENT-FAILURES"),
    )


@router.get("/duplicates")
def duplicates() -> dict[str, Any]:
    """Is the service team being asked to do the same job twice?"""
    payload = business.duplicates()
    return envelope(
        payload, panel_id="DUPLICATES", population="C", basis=payload["basis"]
    )


@router.get("/durations")
def durations(
    bot_id: str = Query(settings.default_bot_id),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
) -> dict[str, Any]:
    """P-36 -- how long the bot holds a guest. Population A, not C."""
    payload = business.durations(bot_id=bot_id, date_from=date_from, date_to=date_to)
    return envelope(payload, panel_id="P-36", population="A", basis=payload["basis"])
