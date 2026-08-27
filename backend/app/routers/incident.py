"""Incident simulation.

Held server-side on purpose. When a reviewer flips the switch, every page -- KPIs,
topology, traces, logs, profiles -- moves together, which is exactly the point the
"symptom to code" workflow is making. Client-side state would let two panels
disagree about whether the system is on fire.
"""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

from app.core.db import fetch_one

router = APIRouter(prefix="/api/incident", tags=["incident"])

State = Literal["healthy", "incident"]

_state: State = "healthy"


def current_state() -> State:
    return _state


class StateRequest(BaseModel):
    state: State


def _incident_row() -> dict | None:
    return fetch_one(
        """
        SELECT code, title, detail, severity, started_at, is_simulated
        FROM incidents
        ORDER BY id
        LIMIT 1
        """
    )


def _payload() -> dict:
    return {
        "state": _state,
        "incident": _incident_row() if _state == "incident" else None,
    }


@router.get("/state")
def get_state() -> dict:
    return _payload()


@router.post("/simulate")
def simulate(body: StateRequest) -> dict:
    global _state
    _state = body.state
    return _payload()
