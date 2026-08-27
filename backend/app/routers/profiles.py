"""Profiles -- code-level insight.

Frames are returned flat (id / parent_id / depth / pct); the frontend assembles
the flame graph, so nesting is never baked into the transport shape.
"""
from __future__ import annotations

from fastapi import APIRouter, Query

from app.services import telemetry

router = APIRouter(prefix="/api/profiles", tags=["profiles"])


@router.get("")
def profile(
    service: str | None = None,
    # `type` is the contract's query name; aliased because it shadows a builtin.
    profile_type: str | None = Query(default=None, alias="type"),
) -> dict:
    return telemetry.profile(service=service, profile_type=profile_type)


@router.get("/correlation")
def profile_correlation() -> dict:
    return telemetry.profile_correlation()
