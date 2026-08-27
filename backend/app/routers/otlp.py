"""OTLP/HTTP receiver.

The forward path. Today the telemetry pages are served from the tables the ETL
populates; the moment a real OSW service is instrumented, its signals arrive here
through the Collector and land in `otlp_ingest` without a schema change. Promotion
into `spans`/`log_records`/`metric_series` is then a query, not a migration.

Responses follow the OTLP/HTTP spec: 200 with a (possibly empty) partialSuccess.
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Request

from app.core.db import get_pool

log = logging.getLogger(__name__)

router = APIRouter(tags=["otlp"])


def _persist(signal: str, payload: dict[str, Any]) -> None:
    with get_pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO otlp_ingest (signal, payload) VALUES (%s, %s)",
                (signal, __import__("json").dumps(payload)),
            )
        conn.commit()


async def _accept(request: Request, signal: str) -> dict:
    try:
        payload = await request.json()
    except Exception:
        # Protobuf bodies are accepted but not decoded in the PoC; record the
        # arrival so the pipeline is visibly working end to end.
        raw = await request.body()
        payload = {"_encoding": "protobuf", "_bytes": len(raw)}
    try:
        _persist(signal, payload)
    except Exception:
        log.exception("failed to persist OTLP %s payload", signal)
    return {"partialSuccess": {}}


@router.post("/v1/traces")
async def receive_traces(request: Request) -> dict:
    return await _accept(request, "traces")


@router.post("/v1/metrics")
async def receive_metrics(request: Request) -> dict:
    return await _accept(request, "metrics")


@router.post("/v1/logs")
async def receive_logs(request: Request) -> dict:
    return await _accept(request, "logs")


@router.get("/api/otlp/ingest-stats", tags=["otlp"])
def ingest_stats() -> dict:
    """Proof the collector path is live -- shown on the Standards page."""
    from app.core.db import fetch_all

    rows = fetch_all(
        """
        SELECT signal,
               COUNT(*)          AS batches,
               MAX(received_at)  AS last_received_at,
               COUNT(*) FILTER (WHERE promoted) AS promoted
        FROM otlp_ingest
        GROUP BY signal
        ORDER BY signal
        """
    )
    return {"items": rows}
