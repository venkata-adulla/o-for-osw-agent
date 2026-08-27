"""Command centre -- the one screen that answers "is the bot working?".

Every route that can look different during an incident takes an optional
``state``; when it is omitted the server's own simulation state is used, so a
reviewer flipping the switch moves this page and every other page together.

Only parameters that actually change the answer are declared. Extra query params
(``bot_id`` on a ticket panel, for instance) are accepted and ignored by FastAPI,
so the contract's "common params" promise still holds -- but the OpenAPI schema
does not advertise a filter with nothing to filter on.

The basis string always comes from the payload the service produced, never from
a literal here: the same provenance then reaches the ``/api/ask`` tools, which
call those functions directly and never see this envelope.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

from app.core.envelope import envelope
from app.routers.incident import current_state
from app.services import business

router = APIRouter(prefix="/api/overview", tags=["overview"])


@router.get("/kpis")
def kpis(
    view: str = Query("business", description="business | technical"),
    state: str | None = Query(
        None,
        description="healthy | incident -- defaults to the server's simulation state",
    ),
) -> dict[str, Any]:
    """The headline tile strip. Stored rows per state, not browser arithmetic."""
    payload = business.kpis(view=view, state=state or current_state())
    technical = payload["view"] == "technical"
    return envelope(
        payload,
        panel_id="OTEL-KPIS" if technical else "P-01",
        population="T" if technical else "A",
        basis=payload["basis"],
    )


@router.get("/health")
def health(state: str | None = Query(None)) -> dict[str, Any]:
    """The health banner: services reporting, and the incident if there is one."""
    payload = business.system_health(state=state or current_state())
    return envelope(
        payload, panel_id="OTEL-HEALTH", population="T", basis=payload["basis"]
    )


@router.get("/topology")
def topology(state: str | None = Query(None)) -> dict[str, Any]:
    """The ordered business request path, timed for the current state."""
    payload = business.topology(state=state or current_state())
    return envelope(
        payload, panel_id="OTEL-TOPOLOGY", population="T", basis=payload["basis"]
    )


@router.get("/signals")
def signals() -> dict[str, Any]:
    """Signal coverage -- five signals, one context."""
    payload = business.signals()
    return envelope(
        payload, panel_id="OTEL-SIGNALS", population="T", basis=payload["basis"]
    )


@router.get("/journey")
def journey(
    source: str = Query("telemetry", description="telemetry | review"),
    state: str | None = Query(None),
) -> dict[str, Any]:
    """The guest-journey funnel from either source, in one stage shape.

    ``telemetry`` is the live OTel funnel (population T); ``review`` is the
    hand-reviewed chat-to-document chain (population C, panel P-54). Both
    return identical stage objects so one component renders either.
    """
    payload = business.journey_overview(source=source, state=state or current_state())
    is_review = payload["source"] == "review"
    return envelope(
        payload,
        panel_id="P-54" if is_review else "OTEL-JOURNEY",
        population="C" if is_review else "T",
        basis=payload["basis"],
    )


@router.get("/operating-model")
def operating_model() -> dict[str, Any]:
    """The four-pillar operating-model slide, as rows rather than layout."""
    payload = business.operating_model()
    return envelope(
        payload, panel_id="SLIDE-SEE", population="ALL", basis=payload["basis"]
    )
