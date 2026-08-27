"""Metrics -- rates, distributions and outcomes.

Instrument names are compared against `metric_instruments`, never interpolated,
so an unknown instrument yields an empty panel rather than an error.
"""
from __future__ import annotations

from fastapi import APIRouter, Query

from app.services import telemetry

router = APIRouter(prefix="/api/metrics", tags=["metrics"])


@router.get("/summaries")
def metric_summaries(state: str | None = None) -> dict:
    return telemetry.metric_summaries(state=state)


@router.get("/histogram")
def metric_histogram(instrument: str | None = None) -> dict:
    return telemetry.metric_histogram(instrument=instrument)


@router.get("/outcomes")
def metric_outcomes(instrument: str | None = None) -> dict:
    return telemetry.metric_outcomes(instrument=instrument)


@router.get("/catalog")
def metric_catalog() -> dict:
    return telemetry.metric_catalog()


@router.get("/series")
def metric_series(
    instrument: str | None = None,
    limit: int | None = Query(default=None, ge=1, le=5000),
) -> dict:
    return telemetry.metric_series(instrument=instrument, limit=limit)
