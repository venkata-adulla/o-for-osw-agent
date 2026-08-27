"""Telemetry-view seed data -- ports docs/REFERENCE_PARITY.md PARTS 2 and 3.

Like ``seed_business``, this stage has no raw extract: everything here is a
literal a reviewer can point at on the old OTel-lab screen. The exception is
``baggage_requests``, where the doc gives 7 representative rows but also
publishes a summary ("1,284 requests inspected ... 1,274 complete ... 10 needs
attention ... p95 94 B") that only reads correctly if the table actually holds
~1,284 rows -- see ``_generate_baggage_requests`` for how the remaining ~1,277
rows are synthesised to land the totals exactly.

``derive_spans.py`` runs after this stage and adds real, ``derived-``-prefixed
traces/spans on top of what is seeded here; the ``bg``-prefixed traces created
below exist only to satisfy the ``baggage_requests`` foreign key and carry no
span detail.
"""
from __future__ import annotations

import json
import math
from datetime import date, datetime, timedelta, timezone
from typing import Any

from app.core.db import get_pool
from app.etl import StageResult, chunked, run_stage

_UTC = timezone.utc
# The fixed reference "now" the whole demo window seeds against, chosen to match
# the exact timestamps docs/REFERENCE_PARITY.md quotes for the ERROR log row and
# the busiest baggage request.
_DEMO_DATE = date(2026, 8, 25)


def _t(hour: int, minute: int, second: int, micros: int = 0) -> datetime:
    return datetime(_DEMO_DATE.year, _DEMO_DATE.month, _DEMO_DATE.day, hour, minute, second, micros, tzinfo=_UTC)


def _full_trace_id(short: str) -> str:
    """8-hex short id -> the 32-hex OTel trace id, using the fixed demo suffix
    the doc itself shows for a9c0772d (``a9c0772d6a1e3d8857f1c2f0742a9b00``)."""
    return f"{short}6a1e3d8857f1c2f0742a9b00"


# ---------------------------------------------------------------------------
# 1 · Services
# ---------------------------------------------------------------------------
_SERVICES: list[tuple[str, str, str, str, str, str, bool, bool]] = [
    ("web-chat", "Web chat", "1.9.0", "production", "ingress / guest channel", "javascript", True, False),
    ("kore-dialog", "Kore.ai", "2.4.1", "production", "dialog management", "python", True, False),
    ("osw-orchestrator", "OSW Orchestrator", "2.4.1", "production", "request routing", "python", True, False),
    ("zendesk-adapter", "Zendesk Adapter", "2.4.1", "production", "ticketing", "python", True, False),
    ("enrichment-service", "Enrichment", "2.4.1", "production", "business context enrichment", "python", True, False),
    ("document-service", "Document Service", "2.4.1", "production", "document generation", "java", True, False),
    ("otel-collector", "OTel Collector", "0.102.0", "production", "signal collection", "go", True, True),
]

# ---------------------------------------------------------------------------
# 2 · Telemetry conversations
# ---------------------------------------------------------------------------
_TELEMETRY_CONVERSATIONS: list[tuple[str, str, str, datetime, str, str, int, int]] = [
    ("conv_8a2f", "guest_8a2f", "web", _t(14, 30, 31),
     "COMPLETED", "Guest asked to return a product, then raised a billing question in the same chat.", 2, 1),
    ("conv_71b0", "guest_71b0", "web", _t(14, 29, 57),
     "COMPLETED", "Guest requested a return; enrichment failed to resolve the ship name.", 1, 1),
    ("conv_a440", "guest_a440", "web", _t(14, 28, 31),
     "ABANDONED", "Guest asked about a product, then left the chat without completing a request.", 1, 0),
    ("conv_4cc2", "guest_4cc2", "web", _t(14, 27, 19),
     "COMPLETED", "Guest attempted a return that matched an existing in-flight request and was blocked as a duplicate.", 1, 1),
]

# ---------------------------------------------------------------------------
# 3 · Traces + spans + span_attributes
# ---------------------------------------------------------------------------
# workflow -> (root operation, human label used for generated baggage rows)
_WORKFLOW_OPERATION = {
    "product_return": "osw.return_request",
    "billing_inquiry": "osw.billing_inquiry",
    "product_inquiry": "osw.product_inquiry",
    "itinerary_document": "osw.itinerary_document",
    "booking_change": "osw.booking_change",
}
_WORKFLOW_LABEL = {
    "product_return": "Return request",
    "billing_inquiry": "Billing inquiry",
    "product_inquiry": "Product inquiry",
    "itinerary_document": "Itinerary request",
    "booking_change": "Booking change",
}

# (trace_id, conversation_id, ticket_ref, workflow, outcome, status, label,
#  duration_ms, started_at)
_NAMED_TRACES: list[tuple[str, str, str | None, str, str, str, str, int, datetime]] = [
    ("7fd3a91c", "conv_8a2f", "ZD-348211", "product_return", "success", "OK",
     "Return request - document attached", 2840, _t(14, 31, 8)),
    ("0be42f76", "conv_8a2f", None, "billing_inquiry", "success", "OK",
     "Billing inquiry - resolved", 1180, _t(14, 30, 44)),
    ("a9c0772d", "conv_71b0", "ZD-348208", "product_return", "error", "ERROR",
     "Return request - enrichment failed", 8120, _t(14, 29, 57)),
    ("27ecf108", "conv_a440", None, "product_inquiry", "abandoned", "OK",
     "Product inquiry - abandoned", 42600, _t(14, 28, 31)),
    ("b1e55d40", "conv_4cc2", "ZD-348205", "product_return", "blocked", "OK",
     "Return request - duplicate blocked", 1760, _t(14, 27, 19)),
    ("d2a60f94", "conv_b902", "ZD-348201", "itinerary_document", "success", "OK",
     "Itinerary request - PDF generated", 1200, _t(14, 24, 2)),
    ("e81bd550", "conv_c117", "ZD-348197", "booking_change", "success", "OK",
     "Booking change - routed to agent", 900, _t(14, 22, 14)),
]

# The 7-span waterfall for 7FD3A91C, exact durations from the doc. hop_no lines
# up 1:1 with topology_hops (hop 1, "Web chat", precedes this trace's root and
# is not itself a span here).
_TRACE_7FD3A91C_SPANS: list[tuple[str, str, str, int | None, int, int, str]] = [
    # (span_id, service_name, operation, hop_no, start_offset_ms, duration_ms, status)
    ("7fd3a91c-root", "kore-dialog", "osw.return_request", None, 0, 2840, "OK"),
    ("7fd3a91c-s2", "kore-dialog", "dialog.process", 2, 0, 711, "OK"),
    ("7fd3a91c-s3", "osw-orchestrator", "POST /requests", 3, 711, 244, "OK"),
    ("7fd3a91c-s4", "zendesk-adapter", "zendesk.ticket.create", 4, 955, 451, "OK"),
    ("7fd3a91c-s5", "enrichment-service", "document.enrich", 5, 1406, 852, "OK"),
    ("7fd3a91c-s6", "document-service", "document.generate", 6, 2258, 341, "OK"),
    ("7fd3a91c-s7", "zendesk-adapter", "zendesk.attachment.upload", 7, 2599, 398, "OK"),
]

# Preserved verbatim from the doc's "Root span attributes" table even though it
# names osw-orchestrator while the waterfall displays this span under Kore.ai --
# a quirk of the source screen, not a transcription error here.
_TRACE_7FD3A91C_SEMCONV: list[tuple[str, str]] = [
    ("service.name", "osw-orchestrator"),
    ("service.version", "2.4.1"),
    ("deployment.environment.name", "production"),
    ("http.request.method", "POST"),
    ("http.response.status_code", "200"),
    ("osw.workflow.name", "return_request"),
]
_TRACE_7FD3A91C_BUSINESS: list[tuple[str, str]] = [
    ("osw.conversation.id", "conv_8a2f"),
    ("osw.ticket.id", "ZD-348211"),
    ("osw.inquiry.type", "return"),
    ("osw.cruise.line", "princess"),
    ("osw.request.outcome", "success"),
    ("trace_id", _full_trace_id("7fd3a91c")),
]

# Root-only spans for the other 6 named traces (baggage/logs reference these but
# the doc never publishes their full waterfall).
_OTHER_ROOT_SPANS: list[tuple[str, str, str, int, str]] = [
    # (trace_id, span_id, service_name, duration_ms, status)
    ("0be42f76", "0be42f76-root", "kore-dialog", 1180, "OK"),
    ("a9c0772d", "a9c0772d-root", "kore-dialog", 8120, "ERROR"),
    ("27ecf108", "27ecf108-root", "kore-dialog", 42600, "UNSET"),
    ("b1e55d40", "b1e55d40-root", "kore-dialog", 1760, "OK"),
    ("d2a60f94", "d2a60f94-root", "kore-dialog", 1200, "OK"),
    ("e81bd550", "e81bd550-root", "kore-dialog", 900, "OK"),
]
# The enrichment span the ERROR log record's span_id points at -- gives the
# incident-topology "Enrichment 4.7s" figure a concrete home inside a9c0772d.
_A9C0772D_ENRICHMENT_SPAN = (
    "a9c0772d", "21a77ee63a8a1bf2", "enrichment-service", "document.enrich", 5, 1406, 4700, "ERROR"
)

# ---------------------------------------------------------------------------
# 4 · Logs
# ---------------------------------------------------------------------------
# (time, severity_text, severity_number, service_name, event_name, body, trace_id)
_LOG_ROWS: list[tuple[datetime, str, int, str, str, str, str | None]] = [
    (_t(14, 31, 10, 842000), "INFO", 9, "zendesk-adapter", "osw.document.attached",
     "Return document attached to ticket ZD-348211", "7fd3a91c"),
    (_t(14, 31, 10, 444000), "INFO", 9, "document-service", "osw.document.generated",
     "Document created in 341 ms", "7fd3a91c"),
    (_t(14, 29, 59, 911000), "ERROR", 17, "enrichment-service", "osw.enrichment.failed",
     "Ship alias could not be resolved", "a9c0772d"),
    (_t(14, 29, 58, 306000), "WARN", 13, "osw-orchestrator", "osw.input.validation",
     "Purchase date absent; recovery prompt issued", "a9c0772d"),
    (_t(14, 28, 31, 17000), "INFO", 9, "kore-dialog", "osw.conversation.started",
     "New conversation accepted from web channel", "27ecf108"),
    (_t(14, 27, 20, 774000), "WARN", 13, "osw-orchestrator", "osw.ticket.duplicate_blocked",
     "Idempotency key matched existing request", "b1e55d40"),
    (_t(14, 26, 12, 401000), "INFO", 9, "otel-collector", "otel.export.completed",
     "Batch exported: 512 spans, 84 metrics, 226 logs", None),
    (_t(14, 12, 36, 791000), "INFO", 9, "osw-orchestrator", "osw.request.completed",
     "Product inquiry completed without ticket creation", "3ed901ac"),
    (_t(14, 11, 18, 340000), "INFO", 9, "kore-dialog", "osw.conversation.started",
     "New conversation accepted from mobile web", "3ed901ac"),
    (_t(14, 10, 5, 612000), "WARN", 13, "enrichment-service", "osw.input.rejected",
     "Booking reference format was not accepted", "98f22d70"),
]
_ERROR_LOG_INDEX = 2  # the row above with severity ERROR
_ERROR_LOG_ATTRIBUTES = {
    "timestamp": "2026-08-25T14:29:59.911Z",
    "severity_text": "ERROR",
    "service.name": "enrichment-service",
    "event.name": "osw.enrichment.failed",
    "body": "Ship alias could not be resolved",
    "trace_id": _full_trace_id("a9c0772d"),
    "span_id": "21a77ee63a8a1bf2",
    "error.type": "SHIP_NOT_FOUND",
}

# ---------------------------------------------------------------------------
# 5 · Metrics
# ---------------------------------------------------------------------------
_METRIC_INSTRUMENTS: list[tuple[str, str, str, str, list[str]]] = [
    ("osw.conversation.started", "Counter", "{conversation}",
     "New guest chat sessions started per hour.", ["channel", "bot.id"]),
    ("osw.conversation.duration", "Histogram", "s",
     "Time from the guest's first message until the chat is completed or abandoned.",
     ["workflow", "outcome"]),
    ("osw.conversation.abandoned", "Counter", "{conversation}", "", ["step", "reason"]),
    ("osw.ticket.created", "Counter", "{ticket}",
     "Eligible requests that successfully created a ticket.", ["inquiry.type"]),
    ("osw.enrichment.operation", "Counter", "{operation}",
     "Attempts to validate or add business context before the request continues.", ["result"]),
    ("osw.enrichment.duration", "Histogram", "s", "", ["result"]),
    ("osw.document.attached", "Counter", "{document}", "", ["result"]),
]

_METRIC_SUMMARIES: list[tuple[str, str, str, str, str, str]] = [
    # (code, instrument, label, value_text, unit, description)
    ("conversation_rate", "osw.conversation.started", "Conversation rate", "53.5", "/hour",
     "New guest chat sessions started per hour."),
    ("conversation_duration_p95", "osw.conversation.duration", "Conversation duration (p95)", "8m 42s", "",
     "95% finish within this time; the slowest 5% take longer."),
    ("ticket_success", "osw.ticket.created", "Ticket success", "83.4", "percent",
     "Eligible requests that successfully created a ticket."),
    ("enrichment_system_errors", "osw.enrichment.operation", "Enrichment system errors", "1.3", "percent",
     "Unexpected service failures only; rejected guest input is separate."),
]

_HISTOGRAM_BUCKETS: list[tuple[str, int]] = [
    ("<= 30s", 78),
    ("30-60s", 156),
    ("1-2m", 342),
    ("2-5m", 493),
    ("5-10m", 171),
    ("> 10m", 44),
]

_METRIC_OUTCOMES: list[tuple[str, int, bool, str]] = [
    ("Success", 962, False, ""),
    ("Input rejected", 28, False, ""),
    ("System error", 13, True,
     "Enrichment error rate: 13 system errors / 1,003 attempts = 1.3%. Input rejections are "
     "tracked separately because the service itself did not fail."),
]

# Per-instrument 24h totals used to synthesise metric_series (not in the doc verbatim,
# but anchored to the tiles/journey numbers it does give: 1,284 conversations started,
# 65 abandoned (1284-1219), 1,071 tickets created, 1,003 enrichment operations,
# 962 documents attached).
_SERIES_TOTALS: dict[str, int] = {
    "osw.conversation.started": 1284,
    "osw.conversation.abandoned": 65,
    "osw.ticket.created": 1071,
    "osw.enrichment.operation": 1003,
    "osw.document.attached": 962,
}
# Histogram-shaped instruments get a smooth wave (seconds) instead of a bucket total.
_SERIES_WAVE: dict[str, tuple[float, float]] = {
    "osw.conversation.duration": (180.0, 40.0),
    "osw.enrichment.duration": (45.0, 12.0),
}

# ---------------------------------------------------------------------------
# 6 · Baggage
# ---------------------------------------------------------------------------
_BAGGAGE_FIELDS: list[tuple[str, str]] = [
    ("osw.tenant.id", "Routing"),
    ("osw.bot.id", "Bot configuration"),
    ("osw.channel", "Channel behavior"),
    ("osw.workflow.name", "Workflow selection"),
]
_BAGGAGE_BLOCKED_FIELDS: list[tuple[str, str, str]] = [
    ("guest.email", "[redacted]", "PII blocked"),
    ("booking.number", "[redacted]", "Record key blocked"),
    ("card.last_four", "not present", "Payment data denied"),
    ("conversation.text", "[dropped]", "Sensitive + unbounded"),
]

# (trace_id, request_label, ticket_ref, conversation_id, workflow, propagation_status,
#  fields_present, fields_expected, header_bytes, outcome, started_at, missing, changed)
_NAMED_BAGGAGE_REQUESTS: list[tuple[str, str, str | None, str, str, str, int, int, int, str, datetime, int, int]] = [
    ("7fd3a91c", "Return request - document attached", "ZD-348211", "conv_8a2f", "product_return",
     "complete", 4, 4, 92, "Success", _t(14, 31, 8), 0, 0),
    ("0be42f76", "Billing inquiry - resolved in chat", None, "conv_8a2f", "billing_inquiry",
     "complete", 4, 4, 91, "Success", _t(14, 30, 44), 0, 0),
    ("a9c0772d", "Return request - enrichment failed", "ZD-348208", "conv_71b0", "product_return",
     "complete", 4, 4, 92, "Error", _t(14, 29, 57), 0, 0),
    ("27ecf108", "Product inquiry - guest abandoned", None, "conv_a440", "product_inquiry",
     "attention", 3, 4, 64, "Abandoned", _t(14, 28, 31), 1, 0),
    ("b1e55d40", "Return request - duplicate blocked", "ZD-348205", "conv_4cc2", "product_return",
     "complete", 4, 4, 92, "Blocked", _t(14, 27, 19), 0, 0),
    ("d2a60f94", "Itinerary request - PDF generated", "ZD-348201", "conv_b902", "itinerary_document",
     "complete", 4, 4, 94, "Success", _t(14, 24, 2), 0, 0),
    ("e81bd550", "Booking change - routed to agent", "ZD-348197", "conv_c117", "booking_change",
     "attention", 3, 4, 73, "Success", _t(14, 22, 14), 1, 0),
]

# Full propagation audit -- only 7FD3A91C has the doc's complete hop table.
_TRACE_7FD3A91C_HOPS: list[tuple[int, str, str, int, int, int, int, str, str | None, str | None]] = [
    # (hop_no, service_name, operation, offset_ms, fields_present, fields_expected, header_bytes,
    #  result, traceparent, baggage_value)
    (1, "Web chat", "Guest request", 0, 4, 4, 92, "Created", None, None),
    (2, "Kore.ai", "Process dialog", 57, 4, 4, 92, "Injected", None, None),
    (3, "OSW Orchestrator", "Route request", 768, 4, 4, 92, "Extracted",
     "00-7fd3a91c6a1e3d8857f1c2f0742a9b00-21a77ee63a8a1bf2-01",
     "osw.tenant.id=osw-prod, osw.bot.id=marina, osw.channel=web, osw.workflow.name=product_return"),
    (4, "Zendesk Adapter", "Create ticket", 1010, 4, 4, 92, "Forwarded", None, None),
    (5, "Enrichment", "Add context", 1460, 4, 4, 92, "Forwarded", None, None),
    (6, "Document Service", "Generate PDF", 2310, 4, 4, 92, "Forwarded", None, None),
    (7, "Zendesk Adapter", "Upload document", 2650, 4, 4, 92, "Read", None, None),
]
_TRACE_7FD3A91C_HOP3_FIELDS: list[tuple[str, str]] = [
    ("osw.tenant.id", "osw-prod"),
    ("osw.bot.id", "marina"),
    ("osw.channel", "web"),
    ("osw.workflow.name", "product_return"),
]

_GENERATED_BAGGAGE_TOTAL = 1277  # 1284 - 7 named; lands 1274 complete + 10 attention overall.
_GENERATED_COMPLETE = 1269  # 1274 complete - 5 named complete
_GENERATED_ATTENTION = 8  # 10 attention - 2 named attention


def _generate_baggage_requests() -> tuple[list[tuple[Any, ...]], list[tuple[Any, ...]]]:
    """~1,277 filler (trace, baggage_request) row pairs.

    header_bytes is shaped so the population's 95th percentile lands on 94 B,
    matching the doc's "HEADER SIZE P95 94 B": exactly 1,220 of the 1,284 total
    rows (95%) sit at or below 94 B, and the remaining 64 sit in the 95-96 B tail.
    """
    workflows = list(_WORKFLOW_OPERATION)
    base_end = _t(14, 31, 8)
    step_seconds = 86_400 / _GENERATED_BAGGAGE_TOTAL

    # 1205 complete rows clustered at 91-92B with a small 93-94B shoulder, plus a
    # 64-row 95-96B tail -- 1205 + 64 = 1269 generated complete rows.
    complete_bytes: list[int] = (
        [91] * 600 + [92] * 550 + [93] * 40 + [94] * 15 + [95] * 32 + [96] * 32
    )
    attention_bytes = [60, 65, 68, 70, 72, 75, 78, 82]

    traces: list[tuple[Any, ...]] = []
    requests: list[tuple[Any, ...]] = []
    index = 0

    def _add(is_attention: bool, header_bytes: int) -> None:
        nonlocal index
        workflow = workflows[index % len(workflows)]
        operation = _WORKFLOW_OPERATION[workflow]
        label = _WORKFLOW_LABEL[workflow]
        trace_id = f"bg{index:08x}"
        started_at = base_end - timedelta(seconds=step_seconds * (index + 1))
        duration_ms = 200 + (index * 37) % 2600

        if is_attention:
            outcome = "Abandoned" if index % 2 == 0 else "Error"
            fields_present, fields_expected = 3, 4
            propagation_status = "attention"
            missing, changed = 1, 0
        else:
            # Sprinkle a handful of non-success outcomes among the complete rows,
            # matching that "complete propagation" is orthogonal to "outcome".
            if index % 41 == 0:
                outcome = "Error"
            elif index % 29 == 0:
                outcome = "Blocked"
            elif index % 23 == 0:
                outcome = "Abandoned"
            else:
                outcome = "Success"
            fields_present, fields_expected = 4, 4
            propagation_status = "complete"
            missing, changed = 0, 0

        trace_outcome = outcome.lower()
        traces.append(
            (trace_id, None, None, "osw-orchestrator", operation, workflow, trace_outcome,
             "ERROR" if trace_outcome == "error" else "OK", label, started_at, duration_ms, 0)
        )
        requests.append(
            (trace_id, label, None, None, workflow, propagation_status, fields_present,
             fields_expected, header_bytes, outcome, started_at, missing, changed)
        )
        index += 1

    for value in complete_bytes:
        _add(False, value)
    for value in attention_bytes:
        _add(True, value)

    assert index == _GENERATED_BAGGAGE_TOTAL
    return traces, requests


# ---------------------------------------------------------------------------
# 7 · Profiles
# ---------------------------------------------------------------------------
_FLAME_TREE: dict[str, Any] = {
    "name": "main", "pct": 100.0, "children": [
        {"name": "handleEnrichment", "pct": 96.0, "children": [
            {"name": "resolveShipAlias", "pct": 56.0, "children": [
                {"name": "normalizeName", "pct": 35.0, "children": [
                    {"name": "fuzzyMatch", "pct": 21.0, "children": []},
                    {"name": "tokenize", "pct": 11.0, "children": []},
                ]},
                {"name": "lookupCache", "pct": 18.0, "children": []},
            ]},
            {"name": "buildDocument", "pct": 37.0, "children": [
                {"name": "renderTemplate", "pct": 20.0, "children": [
                    {"name": "layoutText", "pct": 12.0, "children": []},
                ]},
                {"name": "serializePdf", "pct": 14.0, "children": []},
            ]},
        ]},
    ],
}
_PROFILE_FINDING = (
    "resolveShipAlias() accounts for 56% of CPU samples. This supports the trace "
    "evidence around failed ship-name resolution."
)
_HOT_FUNCTIONS: list[tuple[str, float, int]] = [
    ("resolveShipAlias()", 56.2, 1460),
    ("normalizeName()", 34.8, 906),
    ("renderTemplate()", 19.7, 512),
    ("serializePdf()", 14.1, 367),
]

# ---------------------------------------------------------------------------
# 8 · Topology, signals, incidents, standards, diagnose, operating model
# ---------------------------------------------------------------------------
# (hop_no, service_name, display_name, operation, is_origin, healthy_ms, incident_ms, is_telemetry_path)
_TOPOLOGY_HOPS: list[tuple[int, str, str, str, bool, int | None, int | None, bool]] = [
    (1, "web-chat", "Web chat", "Guest request", True, None, None, False),
    (2, "kore-dialog", "Kore.ai", "Process dialog", False, 711, 711, False),
    (3, "osw-orchestrator", "OSW Orchestrator", "Route request", False, 244, 244, False),
    (4, "zendesk-adapter", "Zendesk Adapter", "Create ticket", False, 451, 451, False),
    (5, "enrichment-service", "Enrichment", "Add context", False, 852, 4700, False),
    (6, "document-service", "Document Service", "Generate PDF", False, 341, 341, False),
    (7, "zendesk-adapter", "Zendesk Adapter", "Upload document", False, 398, 398, False),
    (8, "otel-collector", "OTel Collector", "Receives and routes signals", False, 12, 12, True),
]

_SIGNAL_COVERAGE: list[tuple[str, str, str, str, str, str]] = [
    ("traces", "T", "1.28k", "99.8%", "Every request, end to end", "/traces"),
    ("metrics", "M", "84 series", "100%", "Rates, durations and outcomes", "/metrics"),
    ("logs", "L", "4.7k", "98.6%", "Events that carry trace context", "/logs"),
    ("baggage", "B", "4 fields", "100%", "Governed business context", "/baggage"),
    ("profiles", "P", "60 Hz", "24h", "Code-level insight", "/profiles"),
]

_INCIDENT = (
    "enrichment-degradation", "Enrichment degradation detected",
    # No "- started N minutes ago" here: HealthBanner already appends a live
    # "started N minutes ago" computed from `started_at`, so a hardcoded
    # figure here just duplicated it with a different, stale number attached.
    "Error rate crossed the 5% threshold", "SEV-2", True,
)

_OTEL_REQUIREMENTS: list[tuple[str, str, str, str]] = [
    ("01", "API + SDK", "Instrument every service",
     "Use the supported OpenTelemetry SDK for Kore.ai integrations, orchestration, enrichment, "
     "document generation and Zendesk adapters."),
    ("02", "traceparent", "Propagate one context",
     "Use W3C Trace Context across every HTTP call and asynchronous handoff. Preserve the same "
     "trace across the guest journey."),
    ("03", "OTLP", "Export through OTLP",
     "Send traces, metrics and logs to an OpenTelemetry Collector-not directly from every "
     "service to a vendor."),
    ("04", "SemConv", "Use semantic conventions",
     "Prefer standard HTTP, service, deployment and error attributes. Place OSW-specific "
     "fields under the osw.* namespace."),
    ("05", "Correlation", "Correlate every signal",
     "Write trace_id and span_id into structured logs. Link profiles to services and traces. "
     "Never use unique IDs as metric labels."),
    ("06", "Privacy", "Protect customer data",
     "Keep transcripts, names, emails, booking numbers and payment data out of baggage and "
     "default telemetry exports."),
]

_OTEL_CHECKLIST: list[tuple[str, str]] = [
    ("OTEL-01", "Every conversation has one root trace"),
    ("OTEL-02", "Every cross-service call preserves traceparent"),
    ("OTEL-03", "Spans use standard HTTP and error attributes"),
    ("OTEL-04", "Business metrics exclude unique customer identifiers"),
    ("OTEL-05", "Logs are structured and include trace_id + span_id"),
    ("OTEL-06", "Baggage allowlist is documented and enforced"),
    ("OTEL-07", "OTLP export succeeds through the Collector"),
    ("OTEL-08", "Sensitive fields are redacted before export"),
]

_COLLECTOR_PATH_STEPS: list[tuple[int, str, str, str]] = [
    (1, "01", "OSW services", "SDK instrumentation"),
    (2, "02", "OTLP", "gRPC or HTTP"),
    (3, "03", "OTel Collector", "process + route"),
    (4, "04", "Backend", "query + visualize"),
]

_DIAGNOSE_SYMPTOM: list[tuple[int, str, str]] = [
    (1, "A journey stalls", "The live guest journey shows requests piling up at one stage of the flow"),
    (2, "The business feels it", "Drop-offs rise, tickets arrive without paperwork, guest mood starts to dip"),
    (3, "Today: hours of hunting", "Extracts from separate systems, log archaeology and war rooms to find a culprit"),
    (4, "With one view: minutes", "The screen that shows the symptom is the front door to the evidence behind it"),
]
_DIAGNOSE_DIAGNOSIS: list[tuple[int, str, str, str]] = [
    (1, "Alerts trigger", "Business and technical thresholds can flag problems automatically", "/"),
    (2, "Open the trace", "The guest's exact request, timed hop by hop across every service", "/traces"),
    (3, "Read the log", "The error event carries its trace context - one click between log and waterfall", "/logs"),
    (4, "Profile the code", "Flame graphs point to the exact function consuming the time", "/profiles"),
    (5, "Fix and verify", "Ship the fix, then watch the same journey turn healthy again - live", "/"),
]

_OPERATING_MODEL: list[tuple[str, str, str, str]] = [
    ("pillar", "business_view", "Business view",
     "How conversations are going - outcomes, journey health and guest experience"),
    ("pillar", "technical_view", "Technical view",
     "What happens behind each one - latency, errors and service health"),
    ("pillar", "open_standards", "Open standards",
     "OpenTelemetry end to end - vendor-neutral, portable, no lock-in"),
    ("pillar", "one_place", "One place",
     "Every current and future automation lands in the same pane of glass"),
    ("signal", "traces", "Traces", "Every request, end to end"),
    ("signal", "metrics", "Metrics", "Rates, durations and outcomes"),
    ("signal", "logs", "Logs", "Events that carry trace context"),
    ("signal", "baggage", "Baggage", "Governed business context"),
    ("signal", "profiles", "Profiles", "Code-level insight"),
    ("journey_stage", "conversation_started", "Conversation started", ""),
    # No osw.* instrument measures this stage (it isn't in the Metric Catalog),
    # so unlike the other four stages it has no live/derived total to read.
    # The reference lab's own Overview funnel shows 1,219 (94.9%) here, so that
    # literal figure is seeded as the body's leading number -- the same way
    # "1,284 conversations" seeds the KPI tile. See business._telemetry_stages().
    ("journey_stage", "guest_spoke", "Guest spoke", "1219 guests replied before the request moved on"),
    ("journey_stage", "ticket_created", "Ticket created", ""),
    ("journey_stage", "enrichment_run", "Enrichment run", ""),
    ("journey_stage", "document_attached", "Document attached", ""),
    ("privacy", "allowlist", "Only an approved allowlist of business context travels with each request", ""),
    ("privacy", "auditable", "Auditable hop by hop - see exactly what every service received", ""),
    ("scale", "reusable_instrumentation",
     "Reusable instrumentation and dashboard templates accelerate onboarding", ""),
    ("scale", "command_center", "One OSW command center - business and technical, in one place", ""),
]

# (code, label, unit, healthy_value, healthy_delta, healthy_dir, healthy_good, healthy_tone,
#  incident_value, incident_delta, incident_dir, incident_good, incident_tone)
_TECHNICAL_KPIS: list[tuple[str, str, str, str, str, str, bool, str, str, str, str, bool, str]] = [
    ("conversations", "Conversations", "", "1,284", "+12.4%", "up", True, "good",
     "1,284", "+12.4%", "up", True, "good"),
    ("e2e_success", "End-to-end success", "%", "83.4", "+4.8%", "up", True, "good",
     "71.2", "-12.2%", "down", False, "critical"),
    ("p95_latency", "p95 latency", "s", "2.81", "-8.1%", "down", True, "good",
     "8.12", "+189%", "up", False, "critical"),
    ("error_rate", "Error rate", "%", "2.1", "-0.6 pp", "down", True, "good",
     "8.7", "+6.6 pp", "up", False, "critical"),
]


def _spread(total: int, buckets: int = 24) -> list[int]:
    """``total`` split across ``buckets`` as evenly as possible, deterministic order."""
    base, remainder = divmod(total, buckets)
    return [base + 1 if i < remainder else base for i in range(buckets)]


def _wave(base: float, amplitude: float, buckets: int = 24) -> list[float]:
    return [round(base + amplitude * math.sin(2 * math.pi * i / buckets), 1) for i in range(buckets)]


# ---------------------------------------------------------------------------
# Seeding
# ---------------------------------------------------------------------------
def _seed_services(cur: Any, result: StageResult) -> None:
    cur.executemany(
        """
        INSERT INTO services (
            service_name, display_name, service_version, deployment_env, role,
            sdk_language, is_reporting, is_collector
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (service_name) DO UPDATE SET
            display_name = EXCLUDED.display_name,
            service_version = EXCLUDED.service_version,
            deployment_env = EXCLUDED.deployment_env,
            role = EXCLUDED.role,
            sdk_language = EXCLUDED.sdk_language,
            is_reporting = EXCLUDED.is_reporting,
            is_collector = EXCLUDED.is_collector
        """,
        _SERVICES,
    )
    result.add("services", len(_SERVICES))


def _seed_telemetry_conversations(cur: Any, result: StageResult) -> None:
    cur.executemany(
        """
        INSERT INTO telemetry_conversations (
            conversation_id, guest_ref, channel, started_at, status, summary, trace_count, ticket_count
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (conversation_id) DO UPDATE SET
            guest_ref = EXCLUDED.guest_ref,
            channel = EXCLUDED.channel,
            started_at = EXCLUDED.started_at,
            status = EXCLUDED.status,
            summary = EXCLUDED.summary,
            trace_count = EXCLUDED.trace_count,
            ticket_count = EXCLUDED.ticket_count
        """,
        _TELEMETRY_CONVERSATIONS,
    )
    result.add("telemetry_conversations", len(_TELEMETRY_CONVERSATIONS))


_TRACE_UPSERT = """
INSERT INTO traces (
    trace_id, conversation_id, ticket_ref, root_service, root_operation, workflow,
    outcome, status, label, started_at, duration_ms, span_count
) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (trace_id) DO UPDATE SET
    conversation_id = EXCLUDED.conversation_id,
    ticket_ref = EXCLUDED.ticket_ref,
    root_service = EXCLUDED.root_service,
    root_operation = EXCLUDED.root_operation,
    workflow = EXCLUDED.workflow,
    outcome = EXCLUDED.outcome,
    status = EXCLUDED.status,
    label = EXCLUDED.label,
    started_at = EXCLUDED.started_at,
    duration_ms = EXCLUDED.duration_ms,
    span_count = EXCLUDED.span_count
"""

_SPAN_UPSERT = """
INSERT INTO spans (
    span_id, trace_id, parent_span_id, service_name, operation, kind, hop_no, depth,
    start_offset_ms, duration_ms, status, is_root, attributes
) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (span_id) DO UPDATE SET
    trace_id = EXCLUDED.trace_id,
    parent_span_id = EXCLUDED.parent_span_id,
    service_name = EXCLUDED.service_name,
    operation = EXCLUDED.operation,
    kind = EXCLUDED.kind,
    hop_no = EXCLUDED.hop_no,
    depth = EXCLUDED.depth,
    start_offset_ms = EXCLUDED.start_offset_ms,
    duration_ms = EXCLUDED.duration_ms,
    status = EXCLUDED.status,
    is_root = EXCLUDED.is_root,
    attributes = EXCLUDED.attributes
"""


def _seed_named_traces(cur: Any, result: StageResult) -> None:
    trace_rows = [
        (trace_id, conversation_id, ticket_ref, "kore-dialog", _WORKFLOW_OPERATION[workflow], workflow,
         outcome, status, label, started_at, duration_ms,
         7 if trace_id == "7fd3a91c" else (2 if trace_id == "a9c0772d" else 1))
        for trace_id, conversation_id, ticket_ref, workflow, outcome, status, label, duration_ms, started_at
        in _NAMED_TRACES
    ]
    cur.executemany(_TRACE_UPSERT, trace_rows)
    result.add("traces", len(trace_rows))

    span_rows: list[tuple[Any, ...]] = []
    for span_id, service_name, operation, hop_no, start_offset_ms, duration_ms, status in _TRACE_7FD3A91C_SPANS:
        span_rows.append(
            (span_id, "7fd3a91c", None if span_id.endswith("-root") else "7fd3a91c-root",
             service_name, operation, "SERVER", hop_no, 0 if span_id.endswith("-root") else 1,
             start_offset_ms, duration_ms, status, span_id.endswith("-root"), "{}")
        )
    for trace_id, span_id, service_name, duration_ms, status in _OTHER_ROOT_SPANS:
        span_rows.append(
            (span_id, trace_id, None, service_name, _WORKFLOW_OPERATION[
                next(w for t, _, _, w, *_ in _NAMED_TRACES if t == trace_id)
            ], "SERVER", None, 0, 0, duration_ms, status, True, "{}")
        )
    tid, sid, svc, op, hop, offset, dur, status = _A9C0772D_ENRICHMENT_SPAN
    span_rows.append((sid, tid, f"{tid}-root", svc, op, "CLIENT", hop, 1, offset, dur, status, False, "{}"))

    cur.executemany(_SPAN_UPSERT, span_rows)
    result.add("spans", len(span_rows))

    cur.execute("DELETE FROM span_attributes WHERE span_id = %s", ("7fd3a91c-root",))
    attr_rows = [
        ("7fd3a91c-root", key, value, "semconv", index)
        for index, (key, value) in enumerate(_TRACE_7FD3A91C_SEMCONV, start=1)
    ] + [
        ("7fd3a91c-root", key, value, "business", index)
        for index, (key, value) in enumerate(_TRACE_7FD3A91C_BUSINESS, start=1)
    ]
    cur.executemany(
        "INSERT INTO span_attributes (span_id, key, value, grouping, sort_order) VALUES (%s, %s, %s, %s, %s)",
        attr_rows,
    )
    result.add("span_attributes", len(attr_rows))


def _seed_logs(cur: Any, result: StageResult) -> None:
    rows = []
    for index, (observed_at, severity_text, severity_number, service_name, event_name, body, trace_id) in enumerate(
        _LOG_ROWS
    ):
        attributes = _ERROR_LOG_ATTRIBUTES if index == _ERROR_LOG_INDEX else {}
        error_type = "SHIP_NOT_FOUND" if index == _ERROR_LOG_INDEX else None
        span_id = "21a77ee63a8a1bf2" if index == _ERROR_LOG_INDEX else None
        rows.append(
            (observed_at, severity_text, severity_number, service_name, event_name, body,
             trace_id, span_id, error_type, json.dumps(attributes))
        )
    cur.execute("DELETE FROM log_records WHERE observed_at::date = %s", (_DEMO_DATE,))
    cur.executemany(
        """
        INSERT INTO log_records (
            observed_at, severity_text, severity_number, service_name, event_name, body,
            trace_id, span_id, error_type, attributes
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        rows,
    )
    result.add("log_records", len(rows))


def _seed_metrics(cur: Any, result: StageResult) -> None:
    rows = [
        (name, kind, unit, description, dimensions, sort_order)
        for sort_order, (name, kind, unit, description, dimensions) in enumerate(_METRIC_INSTRUMENTS, start=1)
    ]
    cur.executemany(
        """
        INSERT INTO metric_instruments (name, kind, unit, description, dimensions, sort_order)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (name) DO UPDATE SET
            kind = EXCLUDED.kind, unit = EXCLUDED.unit, description = EXCLUDED.description,
            dimensions = EXCLUDED.dimensions, sort_order = EXCLUDED.sort_order
        """,
        rows,
    )
    result.add("metric_instruments", len(rows))

    rows = [
        (code, instrument, label, value_text, unit, "24h", description, sort_order)
        for sort_order, (code, instrument, label, value_text, unit, description) in enumerate(
            _METRIC_SUMMARIES, start=1
        )
    ]
    cur.executemany(
        """
        INSERT INTO metric_summaries (code, instrument, label, value_text, unit, window_label, description, sort_order)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (code) DO UPDATE SET
            instrument = EXCLUDED.instrument, label = EXCLUDED.label, value_text = EXCLUDED.value_text,
            unit = EXCLUDED.unit, window_label = EXCLUDED.window_label, description = EXCLUDED.description,
            sort_order = EXCLUDED.sort_order
        """,
        rows,
    )
    result.add("metric_summaries", len(rows))

    cur.execute("DELETE FROM metric_histogram_buckets WHERE instrument = %s", ("osw.conversation.duration",))
    rows = [
        ("osw.conversation.duration", label, count, sort_order)
        for sort_order, (label, count) in enumerate(_HISTOGRAM_BUCKETS, start=1)
    ]
    cur.executemany(
        """
        INSERT INTO metric_histogram_buckets (instrument, bucket_label, count, sort_order)
        VALUES (%s, %s, %s, %s)
        """,
        rows,
    )
    result.add("metric_histogram_buckets", len(rows))

    cur.execute("DELETE FROM metric_outcomes WHERE instrument = %s", ("osw.enrichment.operation",))
    rows = [
        ("osw.enrichment.operation", result_label, count, is_error, note, sort_order)
        for sort_order, (result_label, count, is_error, note) in enumerate(_METRIC_OUTCOMES, start=1)
    ]
    cur.executemany(
        """
        INSERT INTO metric_outcomes (instrument, result, count, is_error, note, sort_order)
        VALUES (%s, %s, %s, %s, %s, %s)
        """,
        rows,
    )
    result.add("metric_outcomes", len(rows))

    instruments = [name for name, *_ in _METRIC_INSTRUMENTS]
    cur.execute("DELETE FROM metric_series WHERE instrument = ANY(%s)", (instruments,))
    end = _t(14, 0, 0)
    series_rows: list[tuple[str, datetime, float, str]] = []
    for name in instruments:
        if name in _SERIES_TOTALS:
            values: list[float] = [float(v) for v in _spread(_SERIES_TOTALS[name])]
        elif name in _SERIES_WAVE:
            base, amplitude = _SERIES_WAVE[name]
            values = _wave(base, amplitude)
        else:
            values = _wave(50.0, 8.0)
        for hours_back, value in enumerate(reversed(values)):
            bucket_at = end - timedelta(hours=hours_back)
            series_rows.append((name, bucket_at, value, "{}"))
    for batch in chunked(series_rows, 500):
        cur.executemany(
            "INSERT INTO metric_series (instrument, bucket_at, value, dimensions) VALUES (%s, %s, %s, %s)",
            batch,
        )
    result.add("metric_series", len(series_rows))


def _seed_baggage(cur: Any, result: StageResult) -> None:
    rows = [
        (key, purpose, True, sort_order) for sort_order, (key, purpose) in enumerate(_BAGGAGE_FIELDS, start=1)
    ]
    cur.executemany(
        """
        INSERT INTO baggage_fields (key, purpose, is_allowed, sort_order) VALUES (%s, %s, %s, %s)
        ON CONFLICT (key) DO UPDATE SET
            purpose = EXCLUDED.purpose, is_allowed = EXCLUDED.is_allowed, sort_order = EXCLUDED.sort_order
        """,
        rows,
    )
    result.add("baggage_fields", len(rows))

    rows = [
        (field, observed, reason, sort_order)
        for sort_order, (field, observed, reason) in enumerate(_BAGGAGE_BLOCKED_FIELDS, start=1)
    ]
    cur.executemany(
        """
        INSERT INTO baggage_blocked_fields (field, observed_value, reason, sort_order) VALUES (%s, %s, %s, %s)
        ON CONFLICT (field) DO UPDATE SET
            observed_value = EXCLUDED.observed_value, reason = EXCLUDED.reason, sort_order = EXCLUDED.sort_order
        """,
        rows,
    )
    result.add("baggage_blocked_fields", len(rows))

    filler_traces, filler_requests = _generate_baggage_requests()

    # Filler traces first (baggage_requests.trace_id FKs into traces).
    for batch in chunked(filler_traces, 500):
        cur.executemany(_TRACE_UPSERT, batch)
    result.add("traces", len(filler_traces))

    named_trace_ids = [row[0] for row in _NAMED_BAGGAGE_REQUESTS]
    cur.execute(
        # "%%" escapes the literal percent -- psycopg scans for %s/%(name)s placeholders
        # in the query text, so a bare "%" here would be misread as a stray placeholder.
        "DELETE FROM baggage_requests WHERE trace_id LIKE 'bg%%' OR trace_id = ANY(%s)",
        (named_trace_ids,),
    )
    all_requests = list(_NAMED_BAGGAGE_REQUESTS) + filler_requests
    for batch in chunked(all_requests, 500):
        cur.executemany(
            """
            INSERT INTO baggage_requests (
                trace_id, request_label, ticket_ref, conversation_id, workflow, propagation_status,
                fields_present, fields_expected, header_bytes, outcome, started_at, missing_count, changed_count
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            batch,
        )
    result.add("baggage_requests", len(all_requests))

    cur.execute("DELETE FROM baggage_hops WHERE trace_id = %s", ("7fd3a91c",))
    rows = [
        ("7fd3a91c", hop_no, service_name, operation, offset_ms, fields_present, fields_expected,
         header_bytes, result_label, traceparent, baggage_value)
        for hop_no, service_name, operation, offset_ms, fields_present, fields_expected, header_bytes,
        result_label, traceparent, baggage_value in _TRACE_7FD3A91C_HOPS
    ]
    cur.executemany(
        """
        INSERT INTO baggage_hops (
            trace_id, hop_no, service_name, operation, trace_offset_ms, fields_present, fields_expected,
            header_bytes, result, traceparent, baggage_value
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        rows,
    )
    result.add("baggage_hops", len(rows))

    cur.execute("DELETE FROM baggage_hop_fields WHERE trace_id = %s AND hop_no = %s", ("7fd3a91c", 3))
    rows = [
        ("7fd3a91c", 3, key, value, "Present", sort_order)
        for sort_order, (key, value) in enumerate(_TRACE_7FD3A91C_HOP3_FIELDS, start=1)
    ]
    cur.executemany(
        """
        INSERT INTO baggage_hop_fields (trace_id, hop_no, key, value, status, sort_order)
        VALUES (%s, %s, %s, %s, %s, %s)
        """,
        rows,
    )
    result.add("baggage_hop_fields", len(rows))


def _insert_frame(cur: Any, profile_id: int, node: dict[str, Any], parent_id: int | None,
                   depth: int, counter: list[int]) -> None:
    counter[0] += 1
    cur.execute(
        """
        INSERT INTO profile_frames (profile_id, parent_id, function_name, pct, self_ms, depth, sort_order)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        RETURNING id
        """,
        (profile_id, parent_id, node["name"], node["pct"], None, depth, counter[0]),
    )
    row = cur.fetchone()
    node_id = row["id"] if isinstance(row, dict) else row[0]
    for child in node["children"]:
        _insert_frame(cur, profile_id, child, node_id, depth + 1, counter)


def _seed_profiles(cur: Any, result: StageResult) -> None:
    cur.execute(
        """
        INSERT INTO profiles (service_name, profile_type, window_label, sample_hz, finding)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (service_name, profile_type) DO UPDATE SET
            window_label = EXCLUDED.window_label, sample_hz = EXCLUDED.sample_hz, finding = EXCLUDED.finding
        RETURNING id
        """,
        ("enrichment-service", "cpu", "last 30 min", 60, _PROFILE_FINDING),
    )
    row = cur.fetchone()
    profile_id = row["id"] if isinstance(row, dict) else row[0]
    result.add("profiles", 1)

    cur.execute("DELETE FROM profile_frames WHERE profile_id = %s", (profile_id,))
    counter = [0]
    _insert_frame(cur, profile_id, _FLAME_TREE, None, 0, counter)
    result.add("profile_frames", counter[0])

    cur.execute("DELETE FROM profile_hot_functions WHERE profile_id = %s", (profile_id,))
    rows = [
        (profile_id, name, pct, total_ms, sort_order)
        for sort_order, (name, pct, total_ms) in enumerate(_HOT_FUNCTIONS, start=1)
    ]
    cur.executemany(
        """
        INSERT INTO profile_hot_functions (profile_id, function_name, pct, total_ms, sort_order)
        VALUES (%s, %s, %s, %s, %s)
        """,
        rows,
    )
    result.add("profile_hot_functions", len(rows))


def _seed_topology_and_governance(cur: Any, result: StageResult) -> None:
    cur.executemany(
        """
        INSERT INTO topology_hops (
            hop_no, service_name, display_name, operation, is_origin, healthy_ms, incident_ms, is_telemetry_path
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (hop_no) DO UPDATE SET
            service_name = EXCLUDED.service_name, display_name = EXCLUDED.display_name,
            operation = EXCLUDED.operation, is_origin = EXCLUDED.is_origin,
            healthy_ms = EXCLUDED.healthy_ms, incident_ms = EXCLUDED.incident_ms,
            is_telemetry_path = EXCLUDED.is_telemetry_path
        """,
        _TOPOLOGY_HOPS,
    )
    result.add("topology_hops", len(_TOPOLOGY_HOPS))

    rows = [
        (signal, glyph, volume, coverage, description, route, sort_order)
        for sort_order, (signal, glyph, volume, coverage, description, route) in enumerate(
            _SIGNAL_COVERAGE, start=1
        )
    ]
    cur.executemany(
        """
        INSERT INTO signal_coverage (signal, glyph, volume_text, coverage_text, description, route, sort_order)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (signal) DO UPDATE SET
            glyph = EXCLUDED.glyph, volume_text = EXCLUDED.volume_text, coverage_text = EXCLUDED.coverage_text,
            description = EXCLUDED.description, route = EXCLUDED.route, sort_order = EXCLUDED.sort_order
        """,
        rows,
    )
    result.add("signal_coverage", len(rows))

    code, title, detail, severity, is_simulated = _INCIDENT
    cur.execute(
        """
        INSERT INTO incidents (code, title, detail, severity, started_at, resolved_at, is_simulated)
        VALUES (%s, %s, %s, %s, %s, NULL, %s)
        ON CONFLICT (code) DO UPDATE SET
            title = EXCLUDED.title, detail = EXCLUDED.detail, severity = EXCLUDED.severity,
            started_at = EXCLUDED.started_at, is_simulated = EXCLUDED.is_simulated
        """,
        (code, title, detail, severity, _t(14, 25, 0), is_simulated),
    )
    result.add("incidents", 1)

    rows = [
        (code, badge, title, body, True, True, sort_order)
        for sort_order, (code, badge, title, body) in enumerate(_OTEL_REQUIREMENTS, start=1)
    ]
    cur.executemany(
        """
        INSERT INTO otel_requirements (code, badge, title, body, is_required, is_met, sort_order)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (code) DO UPDATE SET
            badge = EXCLUDED.badge, title = EXCLUDED.title, body = EXCLUDED.body,
            is_required = EXCLUDED.is_required, is_met = EXCLUDED.is_met, sort_order = EXCLUDED.sort_order
        """,
        rows,
    )
    result.add("otel_requirements", len(rows))

    rows = [
        (code, statement, True, sort_order)
        for sort_order, (code, statement) in enumerate(_OTEL_CHECKLIST, start=1)
    ]
    cur.executemany(
        """
        INSERT INTO otel_checklist (code, statement, is_passing, sort_order) VALUES (%s, %s, %s, %s)
        ON CONFLICT (code) DO UPDATE SET
            statement = EXCLUDED.statement, is_passing = EXCLUDED.is_passing, sort_order = EXCLUDED.sort_order
        """,
        rows,
    )
    result.add("otel_checklist", len(rows))

    rows = [(step_no, code, title, detail) for step_no, code, title, detail in _COLLECTOR_PATH_STEPS]
    cur.executemany(
        """
        INSERT INTO collector_path_steps (step_no, code, title, detail) VALUES (%s, %s, %s, %s)
        ON CONFLICT (step_no) DO UPDATE SET code = EXCLUDED.code, title = EXCLUDED.title, detail = EXCLUDED.detail
        """,
        rows,
    )
    result.add("collector_path_steps", len(rows))

    rows = [
        ("symptom", step_no, title, body, "") for step_no, title, body in _DIAGNOSE_SYMPTOM
    ] + [
        ("diagnosis", step_no, title, body, route) for step_no, title, body, route in _DIAGNOSE_DIAGNOSIS
    ]
    cur.executemany(
        """
        INSERT INTO diagnose_steps (phase, step_no, title, body, route) VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (phase, step_no) DO UPDATE SET
            title = EXCLUDED.title, body = EXCLUDED.body, route = EXCLUDED.route
        """,
        rows,
    )
    result.add("diagnose_steps", len(rows))

    counters: dict[str, int] = {}
    rows = []
    for kind, code, title, body in _OPERATING_MODEL:
        counters[kind] = counters.get(kind, 0) + 1
        rows.append((kind, code, title, body, counters[kind]))
    cur.executemany(
        """
        INSERT INTO operating_model (kind, code, title, body, sort_order) VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (kind, code) DO UPDATE SET
            title = EXCLUDED.title, body = EXCLUDED.body, sort_order = EXCLUDED.sort_order
        """,
        rows,
    )
    result.add("operating_model", len(rows))


def _seed_technical_kpis(cur: Any, result: StageResult) -> None:
    rows = []
    for sort_order, (
        code, label, unit, h_value, h_delta, h_dir, h_good, h_tone,
        i_value, i_delta, i_dir, i_good, i_tone,
    ) in enumerate(_TECHNICAL_KPIS, start=1):
        rows.append((code, "technical", "healthy", label, h_value, unit, "", h_delta, h_dir, h_good, h_tone, "", "", sort_order))
        rows.append((code, "technical", "incident", label, i_value, unit, "", i_delta, i_dir, i_good, i_tone, "", "", sort_order))
    cur.executemany(
        """
        INSERT INTO kpi_snapshots (
            code, view, state, label, value_text, unit, sub_text,
            delta_text, delta_direction, delta_is_good, tone, panel_id, footnote, sort_order
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (view, code, state) DO UPDATE SET
            view = EXCLUDED.view, label = EXCLUDED.label, value_text = EXCLUDED.value_text, unit = EXCLUDED.unit,
            sub_text = EXCLUDED.sub_text, delta_text = EXCLUDED.delta_text, delta_direction = EXCLUDED.delta_direction,
            delta_is_good = EXCLUDED.delta_is_good, tone = EXCLUDED.tone, panel_id = EXCLUDED.panel_id,
            footnote = EXCLUDED.footnote, sort_order = EXCLUDED.sort_order
        """,
        rows,
    )
    result.add("kpi_snapshots", len(rows))


def load(result: StageResult) -> None:
    with get_pool().connection() as conn:
        with conn.cursor() as cur:
            _seed_services(cur, result)
            _seed_telemetry_conversations(cur, result)
            _seed_named_traces(cur, result)
            _seed_logs(cur, result)
            _seed_metrics(cur, result)
            _seed_baggage(cur, result)
            _seed_profiles(cur, result)
            _seed_topology_and_governance(cur, result)
            _seed_technical_kpis(cur, result)
        conn.commit()
    result.detail = "docs/REFERENCE_PARITY.md PARTS 2+3 -- literal technical-view seed"


def run() -> StageResult:
    with run_stage("seed_telemetry", "Reference-parity technical view (traces/metrics/logs/baggage/profiles)") as result:
        load(result)
    return result
