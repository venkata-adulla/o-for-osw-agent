"""Traces -- every request, end to end.

Thin by design: the queries live in services/telemetry.py so `/api/ask` can call
exactly the same functions the screen calls.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.services import telemetry

router = APIRouter(prefix="/api/traces", tags=["traces"])


@router.get("")
def list_traces(
    limit: int | None = Query(default=None, ge=1, le=200),
    workflow: str | None = None,
    outcome: str | None = None,
    state: str | None = None,
) -> dict:
    return telemetry.list_traces(
        limit=limit, workflow=workflow, outcome=outcome, state=state
    )


# Declared before /{trace_id} so the literal paths are not swallowed by it.
@router.get("/model")
def trace_model() -> dict:
    return telemetry.trace_model()


@router.get("/conversations/{conversation_id}")
def conversation_traces(conversation_id: str, state: str | None = None) -> dict:
    payload = telemetry.conversation_traces(conversation_id, state=state)
    if payload is None:
        raise HTTPException(status_code=404, detail="conversation not found")
    return payload


@router.get("/{trace_id}")
def trace_detail(trace_id: str, state: str | None = None) -> dict:
    payload = telemetry.trace_detail(trace_id, state=state)
    if payload is None:
        raise HTTPException(status_code=404, detail="trace not found")
    return payload
