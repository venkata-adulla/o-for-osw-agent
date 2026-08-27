"""Governance -- the implementation blueprint and the diagnose workflow.

The prefix is `/api` rather than `/api/standards` because `/api/diagnose` lives
here too: the checklist and the investigation workflow are the same argument
told twice, once as a contract and once as a walkthrough.

Every standards payload carries live `otlp_ingest` counts. A page that claims
"OTLP export succeeds through the Collector" should be able to prove it, and the
receiver in routers/otlp.py is what makes that provable rather than asserted.
"""
from __future__ import annotations

from fastapi import APIRouter

from app.services import telemetry

router = APIRouter(prefix="/api", tags=["standards"])


@router.get("/standards/requirements")
def standards_requirements() -> dict:
    return telemetry.standards_requirements()


@router.get("/standards/checklist")
def standards_checklist() -> dict:
    return telemetry.standards_checklist()


@router.get("/standards/collector-path")
def collector_path() -> dict:
    return telemetry.collector_path()


@router.get("/standards/privacy")
def privacy_standards() -> dict:
    return telemetry.privacy_standards()


@router.get("/standards/otlp-ingest")
def otlp_ingest() -> dict:
    """The ingest evidence on its own, for the LIVE pill to poll."""
    return telemetry.otlp_ingest_stats()


@router.get("/diagnose")
def diagnose(state: str | None = None) -> dict:
    return telemetry.diagnose(state=state)
