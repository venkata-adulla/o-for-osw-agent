"""Telemetry query layer -- one function per panel.

Every telemetry figure the UI shows comes from exactly one function in this
module, and `/api/ask` calls the same functions through its tools. That is the
reason this layer exists: a chat answer and a screen cannot disagree if they read
the same query.

Three rules held throughout:

* **Parameterised SQL only.** Where an identifier has to be interpolated (there
  are none today) it must come from an allowlist in this file.
* **Absent seed data is a shape, not an error.** The ETL lands in a separate
  workstream, so every collection function returns a well-formed empty payload
  rather than raising.
* **The incident simulation is data, not arithmetic in Python.** Degraded
  figures are read from `topology_hops.incident_ms` and the `incident`-state rows
  of `kpi_snapshots`. Nothing about the incident is hard-coded here except the
  join that finds it.
"""
from __future__ import annotations

import functools
import inspect
import logging
import re
from datetime import datetime
from decimal import Decimal
from typing import Any, Callable, Iterable

from app.core.db import fetch_all, fetch_one, fetch_value
from app.core.envelope import envelope
from app.core.otel import (
    BAGGAGE_ALLOWLIST,
    OSW_TENANT_ID,
    OSW_WORKFLOW,
    tracer,
)
from app.routers.incident import current_state

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# osw.* attribute keys used by this module's own instrumentation.
#
# The four *baggage* keys are imported from app.core.otel above and never
# re-declared. The keys below extend that namespace with span-only attributes
# (panel provenance, simulated state, result size) which are not allowlisted for
# propagation -- requirement 04: OSW fields live under osw.*, requirement 06:
# nothing guest-identifying is ever set as an attribute.
# ---------------------------------------------------------------------------
OSW_PANEL_ID = "osw.panel.id"
OSW_SIM_STATE = "osw.simulated.state"
OSW_RESULT_ROWS = "osw.result.rows"
OSW_TRACE_REF = "osw.trace.ref"
OSW_CONVERSATION_ID = "osw.conversation.id"
OSW_INSTRUMENT = "osw.metric.instrument"
OSW_SEVERITY = "osw.log.severity"
OSW_PROFILE_TYPE = "osw.profile.type"

POPULATION = "T"
BASIS_TELEMETRY = "OpenTelemetry signals from instrumented services"

# --- allowlists (nothing outside these ever reaches a SQL string) -----------
STATES: tuple[str, ...] = ("healthy", "incident")
PROFILE_TYPES: tuple[str, ...] = ("cpu", "allocations")
PROPAGATION_STATUSES: tuple[str, ...] = ("complete", "attention")
TRACE_OUTCOMES: tuple[str, ...] = ("success", "error", "abandoned", "blocked")

SEVERITY_FILTERS: dict[str, tuple[str, ...]] = {
    "ALL": (),
    "ERROR": ("ERROR", "FATAL"),  # FATAL folded into ERROR: the UI offers 4 filters
    "WARN": ("WARN",),
    "INFO": ("INFO",),
    "DEBUG": ("DEBUG",),
    "TRACE": ("TRACE",),
    "FATAL": ("FATAL",),
}

# Preferred defaults when the caller does not name one. Values are compared, not
# interpolated, so they are safe; they exist so the demo lands on the panel the
# reference screenshots show.
DEFAULT_HISTOGRAM_INSTRUMENT = "osw.conversation.duration"
DEFAULT_OUTCOME_INSTRUMENT = "osw.enrichment.operation"
DEFAULT_PROFILE_SERVICE = "enrichment-service"

# ---------------------------------------------------------------------------
# Static explainer copy.
#
# The schema stores figures, not prose-only panels. A handful of things in
# REFERENCE_PARITY are pure explainer text with no table to hold them -- the
# conversation/trace/span model cards, the "what is p95?" note, the metric
# glossary, the trace-to-profile correlation strip and the diagnose summary
# line. They are served from here so the shape of the response is stable whether
# or not the ETL has run.
# ---------------------------------------------------------------------------
TRACE_MODEL_ROWS: tuple[dict[str, Any], ...] = (
    {
        "step_no": 1,
        "code": "conversation",
        "title": "Conversation",
        "body": "The complete guest chat",
        "contains": "Request trace",
    },
    {
        "step_no": 2,
        "code": "trace",
        "title": "Request trace",
        "body": "One end-to-end outcome",
        "contains": "Spans",
    },
    {
        "step_no": 3,
        "code": "span",
        "title": "Spans",
        "body": "Individual system operations",
        "contains": None,
    },
)
TRACE_MODEL_HEADLINE = "Conversations → traces → spans"
TRACE_MODEL_SUBTITLE = "Follow the guest, then inspect the work"
TRACE_MODEL_BODY = (
    "One conversation is the guest's chat session. Each request inside it creates "
    "a trace, and each technical operation inside that trace is a span."
)

P95_EXPLAINER = (
    "What is p95? Sort all measurements from shortest to longest. The p95 value "
    "is the point below which 95% fall; only the slowest 5% take longer."
)

METRIC_GLOSSARY: tuple[dict[str, str], ...] = (
    {"term": "Counter", "body": "Adds up events, such as conversations started."},
    {
        "term": "Histogram",
        "body": (
            "Groups measurements, such as conversation duration, so percentiles "
            "like p95 can be calculated."
        ),
    },
    {
        "term": "Dimensions",
        "body": "Approved categories used to filter or group the metric.",
    },
)
METRIC_NAMESPACE = "osw.*"
METRIC_CARDINALITY_RULE = (
    "Low-cardinality dimensions keep dashboards fast and costs predictable. "
    "IDs belong in logs and traces -- not metric labels."
)

LOG_CORRELATION_RULE = "IDs belong in logs and traces -- not metric labels."

PROFILE_CORRELATION_STEPS: tuple[dict[str, Any], ...] = (
    {
        "step_no": 1,
        "title": "Metric alert",
        "body": "p95 latency exceeded 5 seconds",
        "route": "/api/metrics/summaries",
    },
    {
        "step_no": 2,
        "title": "Slow trace",
        "body": "Enrichment span took 4.7 seconds",
        "route": "/api/traces",
    },
    {
        "step_no": 3,
        "title": "Linked profile",
        "body": "Ship alias matching is the hot path",
        "route": "/api/profiles",
    },
)
PROFILE_CORRELATION_HEADLINE = "From symptom to code"

# REFERENCE_PARITY, Standards page. Resource attributes are how a service says
# who it is; without them nothing downstream can group by service.
COLLECTOR_ENV_BLOCK = (
    "# Every service identifies itself with Resource attributes\n"
    "OTEL_SERVICE_NAME=osw-enrichment\n"
    "OTEL_RESOURCE_ATTRIBUTES=service.version=2.4.1,"
    "deployment.environment.name=production\n"
    "OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4318\n"
    "OTEL_PROPAGATORS=tracecontext,baggage"
)
COLLECTOR_ENV_VARS: tuple[dict[str, str], ...] = (
    {"name": "OTEL_SERVICE_NAME", "value": "osw-enrichment"},
    {
        "name": "OTEL_RESOURCE_ATTRIBUTES",
        "value": "service.version=2.4.1,deployment.environment.name=production",
    },
    {"name": "OTEL_EXPORTER_OTLP_ENDPOINT", "value": "http://otel-collector:4318"},
    {"name": "OTEL_PROPAGATORS", "value": "tracecontext,baggage"},
)
# The receiver in app/routers/otlp.py. Named here so the Standards page can
# prove the export contract with live rows instead of asserting it.
OTLP_RECEIVER_ROUTES: tuple[str, ...] = ("/v1/traces", "/v1/metrics", "/v1/logs")

DIAGNOSE_SUMMARY = (
    "One investigation workflow -- from business symptom to technical evidence."
)

PRIVACY_PANEL_KINDS: tuple[str, ...] = ("privacy", "scale")


# ---------------------------------------------------------------------------
# small helpers
# ---------------------------------------------------------------------------
def _plain(value: Any) -> Any:
    """Decimal -> float so JSON callers (and the LLM) see plain numbers."""
    if isinstance(value, Decimal):
        return float(value)
    return value


def _rows(rows: Iterable[dict]) -> list[dict]:
    return [{k: _plain(v) for k, v in row.items()} for row in rows]


def _row(row: dict | None) -> dict | None:
    return None if row is None else {k: _plain(v) for k, v in row.items()}


def clamp(value: int | None, default: int, maximum: int, minimum: int = 0) -> int:
    if value is None:
        return default
    try:
        n = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(n, maximum))


def resolve_state(state: str | None) -> str:
    """A caller-supplied state wins; otherwise the server-held simulation state.

    Held server-side (see routers/incident.py) so every page agrees about
    whether the system is on fire.
    """
    if state is None or state == "":
        return current_state()
    lowered = str(state).strip().lower()
    if lowered not in STATES:
        raise ValueError(f"state must be one of {', '.join(STATES)}")
    return lowered


def _pct_from_text(text: str | None) -> float | None:
    """'99.8%' -> 99.8. Coverage is stored as display text on signal_coverage."""
    if not text:
        return None
    match = re.search(r"(\d+(?:\.\d+)?)", text)
    return float(match.group(1)) if match else None


def _window_label(lo: datetime | None, hi: datetime | None) -> str:
    """Map an observed range onto the UI's window selector vocabulary."""
    if lo is None or hi is None:
        return ""
    seconds = (hi - lo).total_seconds()
    if seconds <= 0:
        return "single instant"
    hours = seconds / 3600.0
    if hours <= 1.5:
        return "1 hour"
    if hours <= 7:
        return "6 hours"
    if hours <= 36:
        return "24 hours"
    days = max(1, round(hours / 24.0))
    return f"{days} days"


def _panel_span(name: str, panel_id: str | None = None) -> Callable[[Callable], Callable]:
    """Wrap a panel query in a span carrying its osw.* provenance.

    The dashboard is instrumented to the contract it audits -- requirement 01.
    Attribute recording is best-effort: telemetry must never be the reason a
    panel fails to render.
    """
    attr_for_arg = {
        "state": OSW_SIM_STATE,
        "trace_id": OSW_TRACE_REF,
        "conversation_id": OSW_CONVERSATION_ID,
        "instrument": OSW_INSTRUMENT,
        "severity": OSW_SEVERITY,
        "profile_type": OSW_PROFILE_TYPE,
        "workflow": OSW_WORKFLOW,
    }

    def decorate(fn: Callable) -> Callable:
        signature = inspect.signature(fn)

        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            with tracer().start_as_current_span(f"osw.panel.{name}") as span:
                try:
                    if panel_id:
                        span.set_attribute(OSW_PANEL_ID, panel_id)
                    span.set_attribute(OSW_TENANT_ID, "osw-prod")
                    bound = signature.bind_partial(*args, **kwargs)
                    for arg_name, value in bound.arguments.items():
                        key = attr_for_arg.get(arg_name)
                        if key and value is not None:
                            span.set_attribute(key, str(value))
                except Exception:  # pragma: no cover - instrumentation only
                    log.debug("could not annotate span for %s", name, exc_info=True)
                result = fn(*args, **kwargs)
                try:
                    if isinstance(result, dict):
                        if isinstance(result.get("state"), str):
                            span.set_attribute(OSW_SIM_STATE, result["state"])
                        items = result.get("items") or result.get("spans") or result.get("frames")
                        if isinstance(items, list):
                            span.set_attribute(OSW_RESULT_ROWS, len(items))
                except Exception:  # pragma: no cover
                    log.debug("could not annotate result for %s", name, exc_info=True)
                return result

        return wrapper

    return decorate


# ---------------------------------------------------------------------------
# incident simulation -- read from the tables, never computed in Python
# ---------------------------------------------------------------------------
def incident_overrides() -> list[dict]:
    """Hops whose timing changes under the simulated incident.

    One row per service that degrades, carrying both the healthy figure (used to
    recognise the span/hop to replace) and the incident figure.
    """
    return _rows(
        fetch_all(
            """
            SELECT hop_no,
                   service_name,
                   display_name,
                   operation,
                   healthy_ms,
                   incident_ms,
                   incident_ms - healthy_ms AS delta_ms
            FROM topology_hops
            WHERE healthy_ms  IS NOT NULL
              AND incident_ms IS NOT NULL
              AND incident_ms <> healthy_ms
            ORDER BY hop_no
            """
        )
    )


def _overrides_by_service(state: str) -> dict[str, dict]:
    """First degrading hop per service; a service at two hops degrades once."""
    if state != "incident":
        return {}
    by_service: dict[str, dict] = {}
    for row in incident_overrides():
        by_service.setdefault(row["service_name"], row)
    return by_service


def incident_record() -> dict | None:
    """The incident the simulation reports -- severity included (SEV-2)."""
    return _row(
        fetch_one(
            """
            SELECT code, title, detail, severity, started_at, resolved_at, is_simulated
            FROM incidents
            ORDER BY id
            LIMIT 1
            """
        )
    )


def state_context(state: str) -> dict[str, Any]:
    """The state block every telemetry payload carries."""
    return {
        "state": state,
        "incident": incident_record() if state == "incident" else None,
        "degraded_services": [
            {
                "hop_no": row["hop_no"],
                "service_name": row["service_name"],
                "display_name": row["display_name"],
                "operation": row["operation"],
                "healthy_ms": row["healthy_ms"],
                "incident_ms": row["incident_ms"],
            }
            for row in (incident_overrides() if state == "incident" else [])
        ],
    }


# ===========================================================================
# TRACES
# ===========================================================================
def _trace_rows(
    *,
    state: str,
    workflow: str | None = None,
    outcome: str | None = None,
    conversation_id: str | None = None,
    limit: int | None = None,
) -> list[dict]:
    """Recent request traces, with the incident delta folded into duration.

    `d` sums the per-trace duration change implied by `topology_hops`: a span is
    only treated as degraded when its duration equals the healthy figure for
    that service, so re-applying the simulation is idempotent and a trace that
    is already slow (the enrichment-failed trace) is left alone.
    """
    sql = """
        WITH ov AS (
            -- DISTINCT ON: a service can appear at two hops (Zendesk Adapter is
            -- both hop 4 and hop 7), and one degradation must not be counted
            -- twice. Matches _overrides_by_service(), which keeps the same row.
            SELECT DISTINCT ON (service_name)
                   service_name, healthy_ms, incident_ms
            FROM topology_hops
            WHERE healthy_ms  IS NOT NULL
              AND incident_ms IS NOT NULL
              AND incident_ms <> healthy_ms
            ORDER BY service_name, hop_no
        ),
        d AS (
            SELECT s.trace_id,
                   COALESCE(SUM(ov.incident_ms - ov.healthy_ms), 0) AS delta_ms
            FROM spans s
            JOIN ov ON ov.service_name = s.service_name
                   AND s.duration_ms   = ov.healthy_ms
            WHERE NOT s.is_root
            GROUP BY s.trace_id
        )
        SELECT t.trace_id,
               t.label,
               t.workflow,
               t.outcome,
               t.status,
               t.started_at,
               t.conversation_id,
               t.ticket_ref,
               t.span_count,
               t.root_service,
               COALESCE(sv.display_name, t.root_service) AS root_service_display,
               t.root_operation,
               t.duration_ms AS healthy_duration_ms,
               t.duration_ms
                 + CASE WHEN %(incident)s THEN COALESCE(d.delta_ms, 0) ELSE 0 END
                 AS duration_ms,
               CASE WHEN %(incident)s THEN COALESCE(d.delta_ms, 0) ELSE 0 END
                 AS incident_delta_ms
        FROM traces t
        LEFT JOIN d          ON d.trace_id      = t.trace_id
        LEFT JOIN services sv ON sv.service_name = t.root_service
        WHERE (%(workflow)s::text IS NULL OR t.workflow = %(workflow)s)
          AND (%(outcome)s::text  IS NULL OR t.outcome  = %(outcome)s)
          AND (%(conversation_id)s::text IS NULL
               OR t.conversation_id = %(conversation_id)s)
        ORDER BY t.started_at DESC, t.trace_id
        LIMIT %(limit)s
    """
    return _rows(
        fetch_all(
            sql,
            {
                "incident": state == "incident",
                "workflow": workflow,
                "outcome": outcome,
                "conversation_id": conversation_id,
                "limit": clamp(limit, 25, 500, 1),
            },
        )
    )


def _signal_coverage_pct(signal: str) -> float | None:
    row = fetch_one(
        "SELECT coverage_text FROM signal_coverage WHERE signal = %s",
        (signal,),
    )
    return _pct_from_text(row["coverage_text"]) if row else None


@_panel_span("traces.list", "OTEL-TRACES")
def list_traces(
    limit: int | None = None,
    workflow: str | None = None,
    outcome: str | None = None,
    state: str | None = None,
) -> dict[str, Any]:
    """Recent request traces for the traces list.

    Filters: `workflow` (free text, compared not interpolated), `outcome`
    (success | error | abandoned | blocked), `limit` (default 25, max 200).
    """
    resolved = resolve_state(state)
    if outcome is not None and outcome.strip().lower() not in TRACE_OUTCOMES:
        raise ValueError(f"outcome must be one of {', '.join(TRACE_OUTCOMES)}")
    items = _trace_rows(
        state=resolved,
        workflow=workflow or None,
        outcome=(outcome.strip().lower() if outcome else None),
        limit=clamp(limit, 25, 200, 1),
    )
    workflows = [
        r["workflow"]
        for r in fetch_all(
            """
            SELECT DISTINCT workflow
            FROM traces
            WHERE workflow IS NOT NULL AND workflow <> ''
            ORDER BY workflow
            """
        )
    ]
    return envelope(
        {
            "items": items,
            "coverage_pct": _signal_coverage_pct("traces"),
            "workflows": workflows,
            "outcomes": list(TRACE_OUTCOMES),
            **state_context(resolved),
        },
        panel_id="OTEL-TRACES",
        population=POPULATION,
        basis=BASIS_TELEMETRY,
    )


@_panel_span("traces.model", "OTEL-TRACE-MODEL")
def trace_model() -> dict[str, Any]:
    """The conversations -> traces -> spans explainer, plus trace coverage."""
    return envelope(
        {
            "headline": TRACE_MODEL_HEADLINE,
            "subtitle": TRACE_MODEL_SUBTITLE,
            "body": TRACE_MODEL_BODY,
            "coverage_pct": _signal_coverage_pct("traces"),
            "items": [dict(row) for row in TRACE_MODEL_ROWS],
        },
        panel_id="OTEL-TRACE-MODEL",
        population=POPULATION,
        basis=BASIS_TELEMETRY,
    )


@_panel_span("traces.conversation", "OTEL-TRACE-CONVERSATION")
def conversation_traces(
    conversation_id: str, state: str | None = None
) -> dict[str, Any] | None:
    """One guest chat session and the request traces inside it.

    None when the conversation is unknown, so the router can 404 rather than
    inventing a session.
    """
    resolved = resolve_state(state)
    conversation = _row(
        fetch_one(
            """
            SELECT conversation_id, guest_ref, channel, started_at, status,
                   summary, trace_count, ticket_count
            FROM telemetry_conversations
            WHERE conversation_id = %s
            """,
            (conversation_id,),
        )
    )
    if conversation is None:
        return None
    traces = _trace_rows(state=resolved, conversation_id=conversation_id, limit=200)
    return envelope(
        {
            **conversation,
            # trace_count/ticket_count are the stored figures; traces is what we hold.
            "traces": traces,
            "traces_held": len(traces),
            **state_context(resolved),
        },
        panel_id="OTEL-TRACE-CONVERSATION",
        population=POPULATION,
        basis=BASIS_TELEMETRY,
    )


def _axis_ticks(duration_ms: int, ticks: int = 5) -> list[int]:
    """`ticks` evenly spaced marks from 0 to the root duration, inclusive."""
    if duration_ms <= 0 or ticks < 2:
        return [0] * max(ticks, 1)
    step = duration_ms / (ticks - 1)
    return [int(round(step * i)) for i in range(ticks - 1)] + [int(duration_ms)]


def _apply_incident_to_spans(
    spans: list[dict], overrides: dict[str, dict]
) -> tuple[list[dict], int]:
    """Replace degraded span durations and push later spans out by the delta.

    The reference request path is a chain of sequential hops, so a single
    running shift is the right model: when Enrichment goes from 852ms to 4.7s
    everything downstream starts 3.85s later and the root grows by the same
    amount. A span is only degraded when its duration still equals the healthy
    figure, which keeps this idempotent.
    """
    ordered = sorted(
        spans,
        key=lambda s: (
            not s.get("is_root"),
            s.get("start_offset_ms") or 0,
            s.get("depth") or 0,
            s.get("hop_no") if s.get("hop_no") is not None else 0,
            s.get("span_id") or "",
        ),
    )
    shift = 0
    total_delta = 0
    root: dict | None = None
    for span in ordered:
        span["is_degraded"] = False
        span["start_offset_ms"] = (span.get("start_offset_ms") or 0) + shift
        if span.get("is_root"):
            root = span
            continue
        override = overrides.get(span.get("service_name") or "")
        if override and span.get("duration_ms") == override.get("healthy_ms"):
            span["healthy_duration_ms"] = override["healthy_ms"]
            span["duration_ms"] = override["incident_ms"]
            span["is_degraded"] = True
            delta = int(override["incident_ms"]) - int(override["healthy_ms"])
            shift += delta
            total_delta += delta
    if root is not None and total_delta:
        root["healthy_duration_ms"] = root["duration_ms"]
        root["duration_ms"] = int(root["duration_ms"]) + total_delta
    # Waterfall order: root first, then by start offset.
    ordered.sort(
        key=lambda s: (
            not s.get("is_root"),
            s.get("start_offset_ms") or 0,
            s.get("depth") or 0,
        )
    )
    return ordered, total_delta


@_panel_span("traces.detail", "OTEL-TRACE-DETAIL")
def trace_detail(trace_id: str, state: str | None = None) -> dict[str, Any] | None:
    """Everything the waterfall needs for one request trace.

    Ordered spans with friendly names and offsets, five axis ticks across the
    root duration, and the root's attributes split into semantic conventions and
    business correlation. None when the trace is unknown.
    """
    resolved = resolve_state(state)
    trace = _row(
        fetch_one(
            """
            SELECT t.trace_id, t.label, t.status, t.outcome, t.workflow,
                   t.started_at, t.duration_ms, t.span_count,
                   t.conversation_id, t.ticket_ref,
                   t.root_service, t.root_operation,
                   COALESCE(sv.display_name, t.root_service) AS root_service_display
            FROM traces t
            LEFT JOIN services sv ON sv.service_name = t.root_service
            WHERE t.trace_id = %s
            """,
            (trace_id,),
        )
    )
    if trace is None:
        return None

    spans = _rows(
        fetch_all(
            """
            SELECT s.span_id,
                   s.parent_span_id,
                   s.service_name,
                   COALESCE(sv.display_name, s.service_name) AS display_name,
                   s.operation,
                   s.kind,
                   s.hop_no,
                   s.depth,
                   s.start_offset_ms,
                   s.duration_ms,
                   s.status,
                   s.is_root
            FROM spans s
            LEFT JOIN services sv ON sv.service_name = s.service_name
            WHERE s.trace_id = %s
            ORDER BY s.is_root DESC, s.start_offset_ms, s.depth,
                     COALESCE(s.hop_no, 0), s.span_id
            """,
            (trace_id,),
        )
    )
    spans, delta_ms = _apply_incident_to_spans(spans, _overrides_by_service(resolved))

    root = next((s for s in spans if s.get("is_root")), None)
    duration_ms = int(
        root["duration_ms"] if root else (trace["duration_ms"] or 0) + delta_ms
    )

    attributes = {"semconv": [], "business": []}
    seen: set[tuple[str, str]] = set()
    for row in fetch_all(
        """
        SELECT sa.key, sa.value, sa.grouping
        FROM span_attributes sa
        JOIN spans s ON s.span_id = sa.span_id
        WHERE s.trace_id = %s
        ORDER BY s.is_root DESC, sa.grouping, sa.sort_order, sa.id
        """,
        (trace_id,),
    ):
        grouping = row["grouping"] if row["grouping"] in attributes else "semconv"
        marker = (grouping, row["key"])
        if marker in seen:
            # Root span wins: it is ordered first.
            continue
        seen.add(marker)
        attributes[grouping].append({"key": row["key"], "value": row["value"]})

    return envelope(
        {
            "trace_id": trace["trace_id"],
            "label": trace["label"],
            "status": trace["status"],
            "outcome": trace["outcome"],
            "workflow": trace["workflow"],
            "started_at": trace["started_at"],
            "conversation_id": trace["conversation_id"],
            "ticket_ref": trace["ticket_ref"],
            "root_service": trace["root_service"],
            "root_service_display": trace["root_service_display"],
            "root_operation": trace["root_operation"],
            "duration_ms": duration_ms,
            "healthy_duration_ms": trace["duration_ms"],
            "incident_delta_ms": delta_ms,
            "span_count": len(spans) or trace["span_count"],
            "axis_ticks_ms": _axis_ticks(duration_ms),
            "spans": spans,
            "attributes": attributes,
            **state_context(resolved),
        },
        panel_id="OTEL-TRACE-DETAIL",
        population=POPULATION,
        basis=BASIS_TELEMETRY,
    )


# ===========================================================================
# METRICS
# ===========================================================================
def _active_series() -> int:
    """Distinct (instrument, dimension-set) pairs -- the cost driver.

    Falls back to the coverage strip's stored figure when no series rows are
    held yet, so the tile is never a bare zero next to populated panels.
    """
    counted = fetch_value(
        """
        SELECT COUNT(*) FROM (
            SELECT DISTINCT instrument, dimensions FROM metric_series
        ) s
        """,
        default=0,
    )
    if counted:
        return int(counted)
    row = fetch_one("SELECT volume_text FROM signal_coverage WHERE signal = 'metrics'")
    parsed = _pct_from_text(row["volume_text"]) if row else None
    return int(parsed) if parsed else 0


@_panel_span("metrics.summaries", "OTEL-METRICS")
def metric_summaries(state: str | None = None) -> dict[str, Any]:
    """The metric tiles.

    Under the incident, a tile is replaced by the matching `incident`-state row
    in `kpi_snapshots` (matched on code, else on label) so p95 latency and the
    error rate rise from stored rows rather than from arithmetic here.
    """
    resolved = resolve_state(state)
    rows = _rows(
        fetch_all(
            """
            SELECT ms.code,
                   ms.label,
                   CASE WHEN %(incident)s THEN COALESCE(k.value_text, ms.value_text)
                        ELSE ms.value_text END AS value_text,
                   CASE WHEN %(incident)s THEN COALESCE(NULLIF(k.unit, ''), ms.unit)
                        ELSE ms.unit END       AS unit,
                   ms.value_text               AS healthy_value_text,
                   ms.description,
                   ms.instrument,
                   -- `window` is reserved in Postgres, so the column is
                   -- window_label; the contract exposes it as `window`.
                   ms.window_label             AS "window",
                   CASE WHEN %(incident)s AND k.code IS NOT NULL THEN true
                        ELSE false END         AS is_degraded,
                   CASE WHEN %(incident)s THEN COALESCE(k.tone, 'neutral')
                        ELSE 'neutral' END     AS tone,
                   CASE WHEN %(incident)s THEN COALESCE(k.sub_text, '')
                        ELSE '' END            AS sub_text,
                   i.kind                      AS instrument_kind
            FROM metric_summaries ms
            LEFT JOIN metric_instruments i ON i.name = ms.instrument
            -- The incident figures are stored rows, not arithmetic: a tile is
            -- replaced by the matching incident-state KPI, preferring a code
            -- match and falling back to an exact label match.
            LEFT JOIN LATERAL (
                SELECT ks.code, ks.value_text, ks.unit, ks.sub_text, ks.tone
                FROM kpi_snapshots ks
                WHERE ks.state = %(state)s
                  AND ks.view  = 'technical'
                  AND (ks.code = ms.code OR lower(ks.label) = lower(ms.label))
                ORDER BY (ks.code = ms.code) DESC, ks.sort_order
                LIMIT 1
            ) k ON true
            ORDER BY ms.sort_order, ms.code
            """,
            {"incident": resolved == "incident", "state": resolved},
        )
    )
    return envelope(
        {
            "active_series": _active_series(),
            "cardinality_rule": METRIC_CARDINALITY_RULE,
            "items": rows,
            **state_context(resolved),
        },
        panel_id="OTEL-METRICS",
        population=POPULATION,
        basis=BASIS_TELEMETRY,
    )


def _default_instrument(table: str, preferred: str) -> str | None:
    """First instrument that actually has rows in `table`, preferring `preferred`.

    `table` is never caller-supplied -- it is one of the three literals below.
    """
    allowed = {"metric_histogram_buckets", "metric_outcomes", "metric_series"}
    if table not in allowed:  # pragma: no cover - guard on a local constant
        raise ValueError("unknown metric table")
    return fetch_value(
        f"""
        SELECT b.instrument
        FROM {table} b
        LEFT JOIN metric_instruments i ON i.name = b.instrument
        GROUP BY b.instrument, i.sort_order
        ORDER BY (b.instrument = %s) DESC, i.sort_order NULLS LAST, b.instrument
        LIMIT 1
        """,
        (preferred,),
    )


def _instrument_row(instrument: str | None) -> dict | None:
    if not instrument:
        return None
    return _row(
        fetch_one(
            """
            SELECT name, kind, unit, description, dimensions
            FROM metric_instruments
            WHERE name = %s
            """,
            (instrument,),
        )
    )


@_panel_span("metrics.histogram", "OTEL-METRICS-HISTOGRAM")
def metric_histogram(instrument: str | None = None) -> dict[str, Any]:
    """Bucketed distribution for one histogram instrument."""
    name = instrument or _default_instrument(
        "metric_histogram_buckets", DEFAULT_HISTOGRAM_INSTRUMENT
    )
    buckets = _rows(
        fetch_all(
            """
            SELECT b.bucket_label, b.count
            FROM metric_histogram_buckets b
            WHERE b.instrument = %s
            ORDER BY b.sort_order, b.id
            """,
            (name,),
        )
        if name
        else []
    )
    info = _instrument_row(name) or {}
    total = sum(int(b["count"] or 0) for b in buckets)
    # Not "{description} {P95_EXPLAINER}": the panel already shows the
    # instrument's own description as its subtitle, so prepending it here
    # duplicated that sentence right above a second "What is p95?" heading
    # the frontend adds on top of it.
    explainer = P95_EXPLAINER
    return envelope(
        {
            "instrument": name,
            "kind": info.get("kind"),
            "unit": info.get("unit", ""),
            "description": info.get("description", ""),
            "total": total,
            "buckets": buckets,
            "explainer": explainer,
        },
        panel_id="OTEL-METRICS-HISTOGRAM",
        population=POPULATION,
        basis=BASIS_TELEMETRY,
    )


@_panel_span("metrics.outcomes", "OTEL-METRICS-OUTCOMES")
def metric_outcomes(instrument: str | None = None) -> dict[str, Any]:
    """Outcome dimensions for one counter -- success vs rejected vs error.

    The error rate the note quotes counts only `is_error` rows: a rejected guest
    input is not a service failure, and conflating the two is how an intake
    problem gets read as an outage.
    """
    name = instrument or _default_instrument("metric_outcomes", DEFAULT_OUTCOME_INSTRUMENT)
    items = _rows(
        fetch_all(
            """
            SELECT o.result, o.count, o.is_error, o.note
            FROM metric_outcomes o
            WHERE o.instrument = %s
            ORDER BY o.sort_order, o.id
            """,
            (name,),
        )
        if name
        else []
    )
    total = sum(int(i["count"] or 0) for i in items)
    errors = sum(int(i["count"] or 0) for i in items if i["is_error"])
    note = next((i["note"] for i in items if i.get("note")), "")
    info = _instrument_row(name) or {}
    return envelope(
        {
            "instrument": name,
            "description": info.get("description", ""),
            "total": total,
            "error_count": errors,
            "error_pct": round(errors * 100.0 / total, 1) if total else None,
            "items": [
                {k: v for k, v in item.items() if k != "note"} for item in items
            ],
            "note": note,
        },
        panel_id="OTEL-METRICS-OUTCOMES",
        population=POPULATION,
        basis=BASIS_TELEMETRY,
    )


@_panel_span("metrics.catalog", "OTEL-METRICS-CATALOG")
def metric_catalog() -> dict[str, Any]:
    """Every OSW business instrument, its kind, unit and approved dimensions."""
    items = _rows(
        fetch_all(
            """
            SELECT name, kind, unit, description, dimensions
            FROM metric_instruments
            ORDER BY sort_order, name
            """
        )
    )
    for item in items:
        item["dimensions"] = list(item.get("dimensions") or [])
    return envelope(
        {
            "namespace": METRIC_NAMESPACE,
            "items": items,
            "glossary": [dict(term) for term in METRIC_GLOSSARY],
            "cardinality_rule": METRIC_CARDINALITY_RULE,
        },
        panel_id="OTEL-METRICS-CATALOG",
        population=POPULATION,
        basis=BASIS_TELEMETRY,
    )


@_panel_span("metrics.series", "OTEL-METRICS-SERIES")
def metric_series(instrument: str | None = None, limit: int | None = None) -> dict[str, Any]:
    """Time series points for one instrument."""
    name = instrument or _default_instrument("metric_series", DEFAULT_HISTOGRAM_INSTRUMENT)
    points = _rows(
        fetch_all(
            """
            SELECT s.bucket_at, s.value, s.dimensions
            FROM metric_series s
            WHERE s.instrument = %s
            ORDER BY s.bucket_at
            LIMIT %s
            """,
            (name, clamp(limit, 500, 5000, 1)),
        )
        if name
        else []
    )
    info = _instrument_row(name) or {}
    return envelope(
        {
            "instrument": name,
            "kind": info.get("kind"),
            "unit": info.get("unit", ""),
            "points": [
                {"bucket_at": p["bucket_at"], "value": p["value"], "dimensions": p["dimensions"]}
                for p in points
            ],
        },
        panel_id="OTEL-METRICS-SERIES",
        population=POPULATION,
        basis=BASIS_TELEMETRY,
    )


# ===========================================================================
# LOGS
# ===========================================================================
def _log_window() -> dict[str, Any]:
    row = _row(
        fetch_one(
            """
            SELECT MIN(observed_at) AS window_from,
                   MAX(observed_at) AS window_to,
                   COUNT(*)         AS records
            FROM log_records
            """
        )
    ) or {"window_from": None, "window_to": None, "records": 0}
    row["label"] = _window_label(row.get("window_from"), row.get("window_to"))
    return row


@_panel_span("logs.list", "OTEL-LOGS")
def list_logs(
    severity: str | None = None,
    limit: int | None = None,
    offset: int | None = None,
    trace_id: str | None = None,
) -> dict[str, Any]:
    """Structured log records, newest first.

    `limit` defaults to 7 to match the reference's pagination ("this demo loads 7
    representative records per page") and is capped at 200. `severity` is one of
    ALL / ERROR / WARN / INFO; ERROR includes FATAL.
    """
    key = (severity or "ALL").strip().upper()
    if key not in SEVERITY_FILTERS:
        raise ValueError(
            "severity must be one of " + ", ".join(sorted(SEVERITY_FILTERS))
        )
    levels = list(SEVERITY_FILTERS[key])
    params: dict[str, Any] = {
        "all_levels": not levels,
        "levels": levels,
        "trace_id": trace_id or None,
        "limit": clamp(limit, 7, 200, 1),
        "offset": clamp(offset, 0, 100_000, 0),
    }
    # The ::text[] cast is what lets the ALL case pass an empty list without
    # Postgres complaining that it cannot type an empty array.
    where = """
        WHERE (%(all_levels)s OR severity_text = ANY(%(levels)s::text[]))
          AND (%(trace_id)s::text IS NULL OR trace_id = %(trace_id)s)
    """
    items = _rows(
        fetch_all(
            f"""
            SELECT id, observed_at, severity_text, severity_number, service_name,
                   event_name, body, trace_id, span_id, error_type
            FROM log_records
            {where}
            ORDER BY observed_at DESC, id DESC
            LIMIT %(limit)s OFFSET %(offset)s
            """,
            params,
        )
    )
    total = int(
        fetch_value(f"SELECT COUNT(*) FROM log_records {where}", params, default=0) or 0
    )
    window = _log_window()
    return envelope(
        {
            "items": items,
            "total": total,
            "limit": params["limit"],
            "offset": params["offset"],
            "window": window["label"],
            "window_from": window["window_from"],
            "window_to": window["window_to"],
            "records_held": window["records"],
            "severity": key,
            "severities": ["ALL", "ERROR", "WARN", "INFO"],
            "correlation_rule": LOG_CORRELATION_RULE,
        },
        panel_id="OTEL-LOGS",
        population=POPULATION,
        basis=BASIS_TELEMETRY,
    )


@_panel_span("logs.detail", "OTEL-LOGS")
def log_detail(log_id: int) -> dict[str, Any] | None:
    """One log record in full, including attributes.

    `json_view` is the exact key set the reference renders in its expanded JSON
    block, so the UI does not have to rename fields to draw it.
    """
    row = _row(
        fetch_one(
            """
            SELECT id, observed_at, severity_text, severity_number, service_name,
                   event_name, body, trace_id, span_id, error_type, attributes
            FROM log_records
            WHERE id = %s
            """,
            (int(log_id),),
        )
    )
    if row is None:
        return None
    observed = row["observed_at"]
    json_view: dict[str, Any] = {
        "timestamp": observed.isoformat().replace("+00:00", "Z")
        if isinstance(observed, datetime)
        else observed,
        "severity_text": row["severity_text"],
        "service.name": row["service_name"],
        "event.name": row["event_name"],
        "body": row["body"],
        "trace_id": row["trace_id"],
        "span_id": row["span_id"],
    }
    if row["error_type"]:
        json_view["error.type"] = row["error_type"]
    for key, value in (row.get("attributes") or {}).items():
        json_view.setdefault(key, value)
    return envelope(
        {
            **row,
            "attributes": row.get("attributes") or {},
            "json_view": json_view,
            "correlation_rule": LOG_CORRELATION_RULE,
            # requirement 05: a log record is the front door to its waterfall
            "trace_route": f"/api/traces/{row['trace_id']}" if row["trace_id"] else None,
        },
        panel_id="OTEL-LOGS",
        population=POPULATION,
        basis=BASIS_TELEMETRY,
    )


# ===========================================================================
# BAGGAGE
# ===========================================================================
@_panel_span("baggage.summary", "OTEL-BAGGAGE")
def baggage_summary() -> dict[str, Any]:
    """Propagation health across the requests we hold baggage evidence for.

    Counted from `baggage_requests`, not scaled up to the window's trace total:
    the audit is only honest about the requests it actually inspected.
    """
    row = _row(
        fetch_one(
            """
            SELECT COUNT(*)                                                   AS requests_inspected,
                   COUNT(*) FILTER (WHERE propagation_status = 'complete')     AS complete_propagation,
                   COUNT(*) FILTER (WHERE propagation_status = 'attention')    AS needs_attention,
                   COALESCE(SUM(missing_count), 0)                             AS missing_fields,
                   COALESCE(SUM(changed_count), 0)                             AS changed_fields,
                   PERCENTILE_DISC(0.95) WITHIN GROUP (ORDER BY header_bytes)  AS header_p95_bytes,
                   MAX(header_bytes)                                           AS header_max_bytes
            FROM baggage_requests
            """
        )
    ) or {}
    inspected = int(row.get("requests_inspected") or 0)
    complete = int(row.get("complete_propagation") or 0)
    traces_total = int(fetch_value("SELECT COUNT(*) FROM traces", default=0) or 0)
    allowed_fields = int(
        fetch_value(
            "SELECT COUNT(*) FROM baggage_fields WHERE is_allowed", default=0
        )
        or len(BAGGAGE_ALLOWLIST)
    )
    return envelope(
        {
            "requests_inspected": inspected,
            "complete_propagation": complete,
            "complete_pct": round(complete * 100.0 / inspected, 1) if inspected else None,
            "needs_attention": int(row.get("needs_attention") or 0),
            "missing_fields": int(row.get("missing_fields") or 0),
            "changed_fields": int(row.get("changed_fields") or 0),
            "header_p95_bytes": _plain(row.get("header_p95_bytes")),
            "header_max_bytes": _plain(row.get("header_max_bytes")),
            "allowed_fields": allowed_fields,
            "traces_total": traces_total,
            "spec": "W3C Baggage",
            "scope_note": (
                "Detailed baggage remains request-scoped: values from different "
                "requests are never combined."
            ),
        },
        panel_id="OTEL-BAGGAGE",
        population=POPULATION,
        basis=BASIS_TELEMETRY,
    )


@_panel_span("baggage.requests", "OTEL-BAGGAGE")
def baggage_requests(
    workflow: str | None = None,
    propagation: str | None = None,
    limit: int | None = None,
    offset: int | None = None,
) -> dict[str, Any]:
    """Candidate requests to inspect. `propagation` is complete | attention | all."""
    status = (propagation or "all").strip().lower()
    if status in ("", "all"):
        status = None
    elif status not in PROPAGATION_STATUSES:
        raise ValueError(
            "propagation must be all, " + " or ".join(PROPAGATION_STATUSES)
        )
    params: dict[str, Any] = {
        "workflow": (workflow or None) if (workflow or "").lower() != "all" else None,
        "status": status,
        # Default 10, not 50: the reference lab's own table shows "7
        # representative requests from 1,284" -- most of that population is
        # generated filler that exists only so the summary tiles above are a
        # real count, not a demo of seven rows. A wall of look-alike filler
        # rows is worse than showing none, so the default page stays small;
        # pass a bigger `limit` explicitly to page through the rest.
        "limit": clamp(limit, 10, 200, 1),
        "offset": clamp(offset, 0, 100_000, 0),
    }
    where = """
        WHERE (%(workflow)s::text IS NULL OR br.workflow = %(workflow)s)
          AND (%(status)s::text   IS NULL OR br.propagation_status = %(status)s)
    """
    items = _rows(
        fetch_all(
            f"""
            SELECT br.trace_id, br.conversation_id, br.ticket_ref, br.request_label,
                   br.workflow, br.propagation_status, br.fields_present,
                   br.fields_expected, br.header_bytes, br.outcome, br.started_at,
                   br.missing_count, br.changed_count
            FROM baggage_requests br
            {where}
            ORDER BY
                -- Rows tied to a real conversation or ticket first: those are
                -- the ones worth reading. Undifferentiated filler sinks to
                -- the bottom regardless of its (synthetic) timestamp.
                (br.conversation_id IS NOT NULL OR br.ticket_ref IS NOT NULL) DESC,
                br.started_at DESC, br.trace_id
            LIMIT %(limit)s OFFSET %(offset)s
            """,
            params,
        )
    )
    total = int(
        fetch_value(
            f"SELECT COUNT(*) FROM baggage_requests br {where}", params, default=0
        )
        or 0
    )
    workflows = [
        r["workflow"]
        for r in fetch_all(
            """
            SELECT DISTINCT workflow
            FROM baggage_requests
            WHERE workflow IS NOT NULL AND workflow <> ''
            ORDER BY workflow
            """
        )
    ]
    return envelope(
        {
            "items": items,
            "total": total,
            "limit": params["limit"],
            "offset": params["offset"],
            "workflows": workflows,
            "propagation_statuses": list(PROPAGATION_STATUSES),
        },
        panel_id="OTEL-BAGGAGE",
        population=POPULATION,
        basis=BASIS_TELEMETRY,
    )


@_panel_span("baggage.request_detail", "OTEL-BAGGAGE-DETAIL")
def baggage_request_detail(
    trace_id: str, state: str | None = None
) -> dict[str, Any] | None:
    """The propagation audit for one request: hops, headers, fields, evidence.

    Request-scoped by construction -- one trace_id in, one trace_id's hops out.
    None when the request is unknown.
    """
    resolved = resolve_state(state)
    request = _row(
        fetch_one(
            """
            SELECT br.trace_id, br.request_label, br.ticket_ref, br.conversation_id,
                   br.workflow, br.propagation_status, br.fields_present,
                   br.fields_expected, br.header_bytes, br.outcome, br.started_at,
                   br.missing_count, br.changed_count,
                   t.label AS trace_label, t.duration_ms, t.status AS trace_status
            FROM baggage_requests br
            LEFT JOIN traces t ON t.trace_id = br.trace_id
            WHERE br.trace_id = %s
            """,
            (trace_id,),
        )
    )
    if request is None:
        return None

    hops = _rows(
        fetch_all(
            """
            SELECT bh.hop_no,
                   bh.service_name,
                   COALESCE(sv.display_name, th.display_name, bh.service_name)
                     AS display_name,
                   bh.operation,
                   bh.trace_offset_ms,
                   bh.fields_present,
                   bh.fields_expected,
                   bh.header_bytes,
                   bh.result,
                   bh.traceparent,
                   bh.baggage_value,
                   th.is_origin
            FROM baggage_hops bh
            LEFT JOIN services     sv ON sv.service_name = bh.service_name
            LEFT JOIN topology_hops th ON th.hop_no      = bh.hop_no
            WHERE bh.trace_id = %s
            ORDER BY bh.hop_no
            """,
            (trace_id,),
        )
    )

    # Incident: the degraded hop takes longer, so every later hop is observed
    # further into the trace. Read from topology_hops, shifted by hop order.
    overrides = _overrides_by_service(resolved)
    shift = 0
    for hop in hops:
        hop["trace_offset_ms"] = (hop.get("trace_offset_ms") or 0) + shift
        hop["is_degraded"] = False
        override = overrides.get(hop.get("service_name") or "")
        # Baggage hop numbers are the topology hop numbers, so require both to
        # agree: a service that appears twice degrades only where it degrades.
        if override and override.get("hop_no") == hop.get("hop_no"):
            hop["is_degraded"] = True
            hop["service_duration_ms"] = override["incident_ms"]
            hop["healthy_duration_ms"] = override["healthy_ms"]
            shift += int(override["delta_ms"])

    hop_fields: dict[str, list[dict[str, Any]]] = {}
    for row in _rows(
        fetch_all(
            """
            SELECT bhf.hop_no, bhf.key, bhf.value,
                   COALESCE(bf.purpose, '') AS purpose,
                   bhf.status
            FROM baggage_hop_fields bhf
            LEFT JOIN baggage_fields bf ON bf.key = bhf.key
            WHERE bhf.trace_id = %s
            ORDER BY bhf.hop_no, bhf.sort_order, bhf.id
            """,
            (trace_id,),
        )
    ):
        # Keyed by hop number as a JSON object of arrays: hop_fields["3"] is the
        # snapshot the third service received.
        hop_fields.setdefault(str(row["hop_no"]), []).append(
            {
                "key": row["key"],
                "value": row["value"],
                "purpose": row["purpose"],
                "status": row["status"],
            }
        )

    blocked = _rows(
        fetch_all(
            """
            SELECT field, observed_value, reason
            FROM baggage_blocked_fields
            ORDER BY sort_order, field
            """
        )
    )
    return envelope(
        {
            "request": request,
            "hops": hops,
            "hop_fields": hop_fields,
            "blocked": blocked,
            "blocked_note": "These values never entered the outgoing baggage header.",
            "scope_note": (
                "This audit belongs only to the selected request. Choose another "
                "row to replace it."
            ),
            **state_context(resolved),
        },
        panel_id="OTEL-BAGGAGE-DETAIL",
        population=POPULATION,
        basis=BASIS_TELEMETRY,
    )


@_panel_span("baggage.allowlist", "OTEL-BAGGAGE-ALLOWLIST")
def baggage_allowlist() -> dict[str, Any]:
    """The governed allowlist and the fields the origin filter refuses.

    `is_enforced_here` marks the keys this API itself propagates -- the tuple
    lives in app.core.otel, so the documented allowlist and the enforced one
    cannot drift apart.
    """
    allowed = _rows(
        fetch_all(
            """
            SELECT key, purpose, is_allowed
            FROM baggage_fields
            WHERE is_allowed
            ORDER BY sort_order, key
            """
        )
    )
    if not allowed:
        # No seed rows yet: the enforced tuple is still the truth.
        allowed = [
            {"key": key, "purpose": "", "is_allowed": True} for key in BAGGAGE_ALLOWLIST
        ]
    for row in allowed:
        row["is_enforced_here"] = row["key"] in BAGGAGE_ALLOWLIST
    blocked = _rows(
        fetch_all(
            """
            SELECT field, observed_value, reason
            FROM baggage_blocked_fields
            ORDER BY sort_order, field
            """
        )
    )
    return envelope(
        {
            "allowed": allowed,
            "blocked": blocked,
            "enforced_keys": list(BAGGAGE_ALLOWLIST),
            "spec": "W3C Baggage",
            "rule": (
                "Only an approved allowlist of business context travels with a "
                "request. Transcripts, names, emails, booking numbers and payment "
                "data never enter baggage."
            ),
        },
        panel_id="OTEL-BAGGAGE-ALLOWLIST",
        population=POPULATION,
        basis=BASIS_TELEMETRY,
    )


# ===========================================================================
# PROFILES
# ===========================================================================
@_panel_span("profiles.flame", "OTEL-PROFILES")
def profile(
    service: str | None = None, profile_type: str | None = None
) -> dict[str, Any]:
    """One flame profile as a FLAT frame list -- the UI builds the tree.

    Each frame carries `id`, `parent_id`, `depth` and `pct`; a root frame has
    `parent_id` null.
    """
    ptype = (profile_type or "cpu").strip().lower()
    if ptype not in PROFILE_TYPES:
        raise ValueError(f"type must be one of {', '.join(PROFILE_TYPES)}")
    header = _row(
        fetch_one(
            """
            SELECT p.id, p.service_name,
                   COALESCE(sv.display_name, p.service_name) AS display_name,
                   p.profile_type, p.window_label, p.sample_hz, p.finding
            FROM profiles p
            LEFT JOIN services sv ON sv.service_name = p.service_name
            WHERE p.profile_type = %(ptype)s
              AND (%(service)s::text IS NULL OR p.service_name = %(service)s)
            ORDER BY (p.service_name = %(preferred)s) DESC, p.service_name
            LIMIT 1
            """,
            {
                "ptype": ptype,
                "service": service or None,
                "preferred": DEFAULT_PROFILE_SERVICE,
            },
        )
    )
    services = [
        r["service_name"]
        for r in fetch_all(
            "SELECT DISTINCT service_name FROM profiles ORDER BY service_name"
        )
    ]
    if header is None:
        # No profile held for this combination: well-formed empty payload.
        return envelope(
            {
                "service_name": service,
                "display_name": None,
                "profile_type": ptype,
                "window_label": "",
                "sample_hz": None,
                "finding": "",
                "frames": [],
                "hot_functions": [],
                "services": services,
                "profile_types": list(PROFILE_TYPES),
            },
            panel_id="OTEL-PROFILES",
            population=POPULATION,
            basis=BASIS_TELEMETRY,
        )

    frames = _rows(
        fetch_all(
            """
            SELECT id, parent_id, function_name, pct, self_ms, depth
            FROM profile_frames
            WHERE profile_id = %s
            ORDER BY depth, sort_order, id
            """,
            (header["id"],),
        )
    )
    hot = _rows(
        fetch_all(
            """
            SELECT function_name, pct, total_ms
            FROM profile_hot_functions
            WHERE profile_id = %s
            ORDER BY sort_order, pct DESC
            """,
            (header["id"],),
        )
    )
    return envelope(
        {
            "profile_id": header["id"],
            "service_name": header["service_name"],
            "display_name": header["display_name"],
            "profile_type": header["profile_type"],
            "window_label": header["window_label"],
            "sample_hz": header["sample_hz"],
            "finding": header["finding"],
            "frames": frames,
            "hot_functions": hot,
            "services": services,
            "profile_types": list(PROFILE_TYPES),
        },
        panel_id="OTEL-PROFILES",
        population=POPULATION,
        basis=BASIS_TELEMETRY,
    )


@_panel_span("profiles.correlation", "OTEL-PROFILE-CORRELATION")
def profile_correlation() -> dict[str, Any]:
    """Metric alert -> slow trace -> linked profile: symptom to code."""
    return envelope(
        {
            "headline": PROFILE_CORRELATION_HEADLINE,
            "steps": [dict(step) for step in PROFILE_CORRELATION_STEPS],
        },
        panel_id="OTEL-PROFILE-CORRELATION",
        population=POPULATION,
        basis=BASIS_TELEMETRY,
    )


# ===========================================================================
# GOVERNANCE -- standards, collector path, privacy, diagnose
# ===========================================================================
def otlp_ingest_stats() -> dict[str, Any]:
    """Live proof the collector path works.

    Rows land here from the receiver in app/routers/otlp.py, so the Standards
    page can show that OTLP export succeeds (OTEL-07) instead of asserting it.
    """
    by_signal = _rows(
        fetch_all(
            """
            SELECT signal,
                   COUNT(*)                          AS batches,
                   COUNT(*) FILTER (WHERE promoted)  AS promoted,
                   MAX(received_at)                  AS last_received_at
            FROM otlp_ingest
            GROUP BY signal
            ORDER BY signal
            """
        )
    )
    totals = _row(
        fetch_one(
            """
            SELECT COUNT(*)         AS batches,
                   MAX(received_at) AS last_received_at
            FROM otlp_ingest
            """
        )
    ) or {"batches": 0, "last_received_at": None}
    return {
        "batches_total": int(totals.get("batches") or 0),
        "last_received_at": totals.get("last_received_at"),
        "by_signal": by_signal,
        "receiver_routes": list(OTLP_RECEIVER_ROUTES),
        "endpoint": "http://otel-collector:4318",
        "is_live": bool(totals.get("batches")),
    }


@_panel_span("standards.requirements", "OTEL-STANDARDS")
def standards_requirements() -> dict[str, Any]:
    """The six-item OpenTelemetry contract, with live OTLP evidence attached."""
    items = _rows(
        fetch_all(
            """
            SELECT code, badge, title, body, is_required, is_met
            FROM otel_requirements
            ORDER BY sort_order, code
            """
        )
    )
    return envelope(
        {
            "items": items,
            "required_total": sum(1 for i in items if i["is_required"]),
            "met_total": sum(1 for i in items if i["is_met"]),
            "ingest": otlp_ingest_stats(),
        },
        panel_id="OTEL-STANDARDS",
        population=POPULATION,
        basis=BASIS_TELEMETRY,
    )


@_panel_span("standards.checklist", "OTEL-CHECKLIST")
def standards_checklist() -> dict[str, Any]:
    """Definition of done -- the acceptance checklist and its pass count."""
    items = _rows(
        fetch_all(
            """
            SELECT code, statement, is_passing
            FROM otel_checklist
            ORDER BY sort_order, code
            """
        )
    )
    return envelope(
        {
            "items": items,
            "passing": sum(1 for i in items if i["is_passing"]),
            "total": len(items),
            "ingest": otlp_ingest_stats(),
        },
        panel_id="OTEL-CHECKLIST",
        population=POPULATION,
        basis=BASIS_TELEMETRY,
    )


@_panel_span("standards.collector_path", "OTEL-COLLECTOR-PATH")
def collector_path() -> dict[str, Any]:
    """The vendor-neutral pipeline, its env block and live ingest counts."""
    steps = _rows(
        fetch_all(
            """
            SELECT step_no, code, title, detail
            FROM collector_path_steps
            ORDER BY step_no
            """
        )
    )
    return envelope(
        {
            "steps": steps,
            "env_block": COLLECTOR_ENV_BLOCK,
            "env_vars": [dict(v) for v in COLLECTOR_ENV_VARS],
            "contract_note": (
                "One export contract: services speak OTLP to a Collector, never "
                "directly to a vendor."
            ),
            "ingest": otlp_ingest_stats(),
        },
        panel_id="OTEL-COLLECTOR-PATH",
        population=POPULATION,
        basis=BASIS_TELEMETRY,
    )


@_panel_span("standards.privacy", "OTEL-PRIVACY")
def privacy_standards() -> dict[str, Any]:
    """Privacy by production design, and every automation joining one picture."""
    items = _rows(
        fetch_all(
            """
            SELECT kind, code, title, body, sort_order
            FROM operating_model
            WHERE kind = ANY(%s::text[])
            ORDER BY kind, sort_order, code
            """,
            (list(PRIVACY_PANEL_KINDS),),
        )
    )
    panels: dict[str, list[dict]] = {kind: [] for kind in PRIVACY_PANEL_KINDS}
    for item in items:
        panels.setdefault(item["kind"], []).append(item)
    return envelope(
        {
            "items": items,
            "panels": panels,
            "enforced_keys": list(BAGGAGE_ALLOWLIST),
            "blocked": _rows(
                fetch_all(
                    """
                    SELECT field, observed_value, reason
                    FROM baggage_blocked_fields
                    ORDER BY sort_order, field
                    """
                )
            ),
        },
        panel_id="OTEL-PRIVACY",
        population=POPULATION,
        basis=BASIS_TELEMETRY,
    )


def _diagnose_evidence(state: str) -> dict[str, Any]:
    """A live worked example for steps 2-4, not just a link to go find one.

    Picks one real trace (the incident's own error trace when there is one,
    otherwise the most recent trace), pulls the log records that carry that
    trace's context, and profiles whichever service is actually degraded.
    Under a healthy state this doubles as step 5's "watch it turn healthy"
    evidence -- same bundle, just nothing wrong with it.
    """
    trace_row: dict[str, Any] | None = None
    logs_evidence: list[dict] = []
    if state == "incident":
        # Prefer a failing trace that also has correlated log records, so the
        # embedded "read the log" evidence is never an empty panel next to a
        # real failure -- that would undercut the exact point of this page.
        for candidate in _trace_rows(state=state, outcome="error", limit=25):
            found = list_logs(trace_id=candidate["trace_id"], limit=5)["items"]
            if found:
                trace_row, logs_evidence = candidate, found
                break
        if trace_row is None:
            fallback = _trace_rows(state=state, outcome="error", limit=1)
            trace_row = fallback[0] if fallback else None
    if trace_row is None:
        candidates = _trace_rows(state=state, limit=5)
        trace_row = candidates[0] if candidates else None
        if trace_row is not None:
            logs_evidence = list_logs(trace_id=trace_row["trace_id"], limit=5)["items"]

    trace_evidence: dict[str, Any] | None = None
    if trace_row is not None:
        detail = trace_detail(trace_row["trace_id"], state=state)
        if detail is not None:
            trace_evidence = {
                "trace_id": detail["trace_id"],
                "label": detail["label"],
                "status": detail["status"],
                "duration_ms": detail["duration_ms"],
                "span_count": detail["span_count"],
                "axis_ticks_ms": detail["axis_ticks_ms"],
                "spans": detail["spans"],
                "conversation_id": detail.get("conversation_id"),
            }

    degraded = _overrides_by_service(state)
    target_service = next(iter(degraded), None)
    profile_evidence = profile(service=target_service) if target_service else profile()
    if not profile_evidence.get("hot_functions"):
        # No profile held for that exact service -- fall back to whatever
        # profile does exist rather than showing an empty panel.
        profile_evidence = profile()

    return {
        "trace": trace_evidence,
        "logs": logs_evidence,
        "profile": {
            "service_name": profile_evidence.get("service_name"),
            "display_name": profile_evidence.get("display_name"),
            "profile_type": profile_evidence.get("profile_type"),
            "finding": profile_evidence.get("finding"),
            "hot_functions": (profile_evidence.get("hot_functions") or [])[:3],
        },
    }


@_panel_span("standards.diagnose", "OTEL-DIAGNOSE")
def diagnose(state: str | None = None) -> dict[str, Any]:
    """Symptom to code: what the business sees, then the five-click diagnosis."""
    resolved = resolve_state(state)
    rows = _rows(
        fetch_all(
            """
            SELECT phase, step_no, title, body, route
            FROM diagnose_steps
            ORDER BY phase DESC, step_no
            """
        )
    )
    return envelope(
        {
            "symptom": [
                {k: v for k, v in r.items() if k != "phase"}
                for r in rows
                if r["phase"] == "symptom"
            ],
            "diagnosis": [
                {k: v for k, v in r.items() if k != "phase"}
                for r in rows
                if r["phase"] == "diagnosis"
            ],
            "summary": DIAGNOSE_SUMMARY,
            "evidence": _diagnose_evidence(resolved),
            **state_context(resolved),
        },
        panel_id="OTEL-DIAGNOSE",
        population=POPULATION,
        basis=BASIS_TELEMETRY,
    )
