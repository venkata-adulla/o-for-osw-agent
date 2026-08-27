"""Logs -- events that carry trace context.

Pagination is real: `limit` defaults to 7, matching the reference's "this demo
loads 7 representative records per page. A production query retrieves only the
requested page -- not every record at once."
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.services import telemetry

router = APIRouter(prefix="/api/logs", tags=["logs"])


@router.get("")
def list_logs(
    severity: str | None = None,
    limit: int | None = Query(default=None, ge=1, le=200),
    offset: int | None = Query(default=None, ge=0),
    trace_id: str | None = None,
) -> dict:
    return telemetry.list_logs(
        severity=severity, limit=limit, offset=offset, trace_id=trace_id
    )


@router.get("/{log_id}")
def log_detail(log_id: int) -> dict:
    payload = telemetry.log_detail(log_id)
    if payload is None:
        raise HTTPException(status_code=404, detail="log record not found")
    return payload
