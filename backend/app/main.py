"""O for OSW -- unified observability API.

Business view and technical view over one context, served from one process so a
business symptom and its technical evidence can never disagree.
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.db import get_pool, healthy
from app.core.otel import setup_telemetry
from app.core.scheduler import enabled as scheduler_enabled, etl_loop
from app.routers import (
    ask,
    baggage,
    conversations,
    customers,
    incident,
    journey,
    lines,
    logs,
    meta,
    metrics,
    otlp,
    overview,
    products,
    profiles,
    standards,
    tickets,
    traces,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
log = logging.getLogger("osw")


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_telemetry(app)
    try:
        get_pool()
    except Exception:
        log.warning("database pool not ready at startup; will retry on first query")

    scheduler_task: asyncio.Task | None = None
    if scheduler_enabled():
        scheduler_task = asyncio.create_task(etl_loop())
        log.info("ETL scheduler started")
    else:
        log.info("ETL scheduler disabled (ETL_SCHEDULER_ENABLED=false)")

    yield

    if scheduler_task is not None:
        scheduler_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await scheduler_task
    try:
        get_pool().close()
    except Exception:  # pragma: no cover - shutdown is best-effort
        log.debug("connection pool already closed")


app = FastAPI(
    title="O for OSW -- Observability API",
    version=settings.app_version,
    description=(
        "One operating picture for every OSW automation: the business view "
        "(outcomes, journey health, guest experience) and the technical view "
        "(traces, metrics, logs, baggage, profiles) on OpenTelemetry."
    ),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    # PoC: the dashboard is unauthenticated, so this is deliberately open.
    # Tighten to the dashboard origin before this leaves the lab.
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(ValueError)
async def value_error_handler(_: Request, exc: ValueError) -> JSONResponse:
    return JSONResponse(status_code=400, content={"detail": str(exc)})


@app.get("/health", tags=["system"])
def health() -> dict:
    return {
        "status": "ok",
        "db": "up" if healthy() else "down",
        "version": settings.app_version,
    }


for router in (
    meta.router,
    overview.router,
    journey.router,
    tickets.router,
    lines.router,
    products.router,
    customers.router,
    conversations.router,
    traces.router,
    metrics.router,
    logs.router,
    baggage.router,
    profiles.router,
    standards.router,
    incident.router,
    ask.router,
    otlp.router,
):
    app.include_router(router)
