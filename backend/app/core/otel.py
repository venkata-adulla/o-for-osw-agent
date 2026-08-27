"""OpenTelemetry wiring for this service.

This is the dashboard practising what it reports: the API is itself instrumented
to the same contract it audits on the Standards page.

  01 API + SDK        -- real SDK, not a shim
  02 traceparent      -- W3C tracecontext + baggage propagators
  03 OTLP             -- exports to the Collector, never to a vendor directly
  04 SemConv          -- standard service.*/deployment.* resource attributes,
                         OSW fields under the osw.* namespace
  05 Correlation      -- trace_id/span_id injected into every log line
  06 Privacy          -- guest identifiers are never set as attributes; the
                         Collector scrubs as a second line of defence
"""
from __future__ import annotations

import logging

from opentelemetry import baggage, trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.logging import LoggingInstrumentor
from opentelemetry.propagate import set_global_textmap
from opentelemetry.propagators.composite import CompositePropagator
from opentelemetry.baggage.propagation import W3CBaggagePropagator
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.semconv.resource import ResourceAttributes

from app.core.config import settings

log = logging.getLogger(__name__)

# The OSW business namespace. Keys here are the only business context allowed to
# travel with a request -- see the Baggage allowlist.
OSW_TENANT_ID = "osw.tenant.id"
OSW_BOT_ID = "osw.bot.id"
OSW_CHANNEL = "osw.channel"
OSW_WORKFLOW = "osw.workflow.name"

BAGGAGE_ALLOWLIST = (OSW_TENANT_ID, OSW_BOT_ID, OSW_CHANNEL, OSW_WORKFLOW)

_initialised = False


def setup_telemetry(app) -> None:
    """Idempotent; safe to call from the lifespan hook."""
    global _initialised
    if _initialised:
        return

    resource = Resource.create(
        {
            ResourceAttributes.SERVICE_NAME: "osw-observability-api",
            ResourceAttributes.SERVICE_VERSION: settings.app_version,
            ResourceAttributes.DEPLOYMENT_ENVIRONMENT: "poc",
            OSW_TENANT_ID: "osw-prod",
        }
    )

    provider = TracerProvider(resource=resource)
    try:
        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    except Exception:
        # A missing Collector must never stop the API from serving.
        log.warning("OTLP span exporter unavailable; continuing without export")
    trace.set_tracer_provider(provider)

    # Requirement 02: one context across every hop, trace plus baggage.
    set_global_textmap(
        CompositePropagator([TraceContextTextMapPropagator(), W3CBaggagePropagator()])
    )

    FastAPIInstrumentor.instrument_app(app, excluded_urls="health,docs,openapi.json")
    HTTPXClientInstrumentor().instrument()
    # Requirement 05: trace_id and span_id in every structured log line.
    LoggingInstrumentor().instrument(set_logging_format=True)

    _initialised = True
    log.info("OpenTelemetry initialised for osw-observability-api")


def tracer() -> trace.Tracer:
    return trace.get_tracer("osw.observability")


def set_request_baggage(bot_id: str, channel: str = "web", workflow: str | None = None) -> None:
    """Attach only allowlisted business context. Nothing guest-identifying."""
    baggage.set_baggage(OSW_TENANT_ID, "osw-prod")
    baggage.set_baggage(OSW_BOT_ID, bot_id)
    baggage.set_baggage(OSW_CHANNEL, channel)
    if workflow:
        baggage.set_baggage(OSW_WORKFLOW, workflow)
