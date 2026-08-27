"""Baggage -- governed business context.

Two-step by design: the window finds candidate requests, then the detail view
follows baggage on ONE selected trace. Values from different requests are never
combined, which is what makes the propagation audit evidence rather than an
average.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.services import telemetry

router = APIRouter(prefix="/api/baggage", tags=["baggage"])


@router.get("/summary")
def baggage_summary() -> dict:
    return telemetry.baggage_summary()


@router.get("/requests")
def baggage_requests(
    workflow: str | None = None,
    propagation: str | None = None,
    limit: int | None = Query(default=None, ge=1, le=200),
    offset: int | None = Query(default=None, ge=0),
) -> dict:
    return telemetry.baggage_requests(
        workflow=workflow, propagation=propagation, limit=limit, offset=offset
    )


@router.get("/requests/{trace_id}")
def baggage_request_detail(trace_id: str, state: str | None = None) -> dict:
    payload = telemetry.baggage_request_detail(trace_id, state=state)
    if payload is None:
        raise HTTPException(status_code=404, detail="baggage request not found")
    return payload


@router.get("/allowlist")
def baggage_allowlist() -> dict:
    return telemetry.baggage_allowlist()
