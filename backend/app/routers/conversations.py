"""Conversations -- population A, the Kore.ai session page.

The list route is paged rather than capped-and-truncated, because the underlying
extract is itself one capped API page: ``total`` is the number of rows we
*hold*, and the populations panel is where a reader learns that more exist.

The detail route is where the two halves of this product meet: the same session
id that identifies a business conversation is the ``conversation_id`` carried by
its traces, so a business record hands straight over to its technical evidence.
"""
from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.core.config import settings
from app.core.envelope import envelope
from app.services import business

router = APIRouter(prefix="/api/conversations", tags=["conversations"])


@router.get("")
def list_conversations(
    bot_id: str = Query(settings.default_bot_id),
    limit: int = Query(
        business.DEFAULT_PAGE_LIMIT,
        ge=1,
        le=business.MAX_PAGE_LIMIT,
        description="clamped to 200",
    ),
    offset: int = Query(0, ge=0),
    channel: str | None = Query(None),
    containment_type: str | None = Query(
        None, description="self_service | drop_off | agent_transfer"
    ),
    q: str | None = Query(None, description="matches session_id or channel_user_id"),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
) -> dict[str, Any]:
    """The session list, newest first, with the total held before paging."""
    payload = business.list_conversations(
        bot_id=bot_id,
        limit=limit,
        offset=offset,
        channel=channel,
        containment_type=containment_type,
        q=q,
        date_from=date_from,
        date_to=date_to,
    )
    return envelope(payload, panel_id="P-01", population="A", basis=payload["basis"])


@router.get("/{session_id}")
def conversation_detail(session_id: str) -> dict[str, Any]:
    """One session, its ordered turns, and any trace ids that carry its id."""
    payload = business.conversation_detail(session_id)
    if payload is None:
        raise HTTPException(
            status_code=404, detail=f"conversation {session_id} not found"
        )
    return envelope(
        payload, panel_id="CONVERSATION-DETAIL", population="A", basis=payload["basis"]
    )
