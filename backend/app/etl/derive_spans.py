"""Derived traces/spans -- the one place the technical view touches real data.

Everything in ``seed_telemetry.py`` is a literal ported from the reference
screen. This stage is different: it reads the *real* per-node timing records
Kore.ai reports (``load_kore.performance_records()``) and the *real* sessions
``load_kore`` already landed in ``conversations``, and
turns each real session that has timing data into one ``traces`` row plus one
``spans`` row per node execution.

Why the join has to happen in Python, not SQL: the performance extract never
carries a ``sessionId``. Inspecting the raw file
(``Extracts Prod/Get Analytics - performance (per-node timing)``) shows each
record only carries ``userId`` (the Kore.ai user id) and a ``timestamp``.
Cross-checking one record's ``userId`` against
``Extracts Prod/Sessions History (all outcomes)`` confirms ``userId`` is
exactly ``conversations.channel_user_id``, and that the record's timestamp
falls inside that session's ``[started_at, ended_at]`` window (with a few
hundred milliseconds of overshoot at the boundary -- the doc-comparable case
observed: a "BillingGratuityIssue" record timestamped 169ms after its
session's own ``end_time``). So the join key is
``(channel_user_id == userId) AND (timestamp within window, +/- a slack)``,
picking the closest window when a guest has more than one session.

Run this stage after ``load_kore`` (needs real sessions already in
``conversations``) and after ``seed_telemetry`` (needs the ``services`` rows
for the spans' FK). ``derived-``-prefixed ids keep this data visually
distinct from the 5 named reference traces and the ``bg``-prefixed baggage
filler traces seed_telemetry.py creates.
"""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any

from app.core.db import get_pool
from app.etl import StageResult, clean, parse_iso, parse_response_time_ms, run_stage, slug
from app.etl.load_kore import performance_records

# How far outside a session's [started_at, ended_at] window a performance
# record's timestamp may still fall and be considered "this session's". The
# one case checked by hand overshot end_time by 169ms; 15s is a generous
# margin for clock/measurement skew without risking a false match onto a
# neighbouring session by the same guest.
_WINDOW_SLACK = timedelta(seconds=15)

# Kore.ai node "type" -> the closest of the 7 services seed_telemetry.py seeds.
# Judgment call: the performance extract has no service-topology field, only a
# node type (script/generativeai/aiassist/pre|postprocessor script/service) and
# a node name. Internal dialog-engine steps map to kore-dialog; anything typed
# "service"/"aiassist" is an outbound call, bucketed by what the node name
# names.
_SERVICE_HINTS: tuple[tuple[str, str], ...] = (
    ("document", "document-service"),
    ("reservation", "enrichment-service"),
    ("transcation", "enrichment-service"),  # sic -- the extract itself misspells "transaction"
    ("transaction", "enrichment-service"),
    ("vessel", "enrichment-service"),
    ("cruise", "enrichment-service"),
    ("itiernary", "document-service"),  # sic -- "itinerary" misspelled in the extract
    ("itinerary", "document-service"),
    ("zendesk", "zendesk-adapter"),
    ("ticket", "zendesk-adapter"),
)


def _service_for(node_name: str, node_type: str | None) -> str:
    node_type = (node_type or "").lower()
    lowered = node_name.lower()
    if node_type in ("service", "aiassist", "generativeai"):
        for needle, service in _SERVICE_HINTS:
            if needle in lowered:
                return service
        return "osw-orchestrator"
    return "kore-dialog"  # script / preprocessor script / postprocessor script


def _fetch_real_conversations(cur: Any) -> list[dict[str, Any]]:
    cur.execute(
        """
        SELECT session_id, channel_user_id, started_at, ended_at, session_status,
               containment_type, ticket_id, inquiry_type, bot_id
          FROM conversations
         WHERE channel_user_id IS NOT NULL
           AND started_at IS NOT NULL
           AND ended_at IS NOT NULL
        """
    )
    return list(cur.fetchall())


def _match_records(
    records: list[dict[str, Any]], conversations: list[dict[str, Any]]
) -> tuple[dict[str, list[tuple[dict[str, Any], datetime]]], int]:
    """Group performance records by the real session they belong to.

    Returns ``{session_id: [(record, parsed_timestamp), ...]}`` plus a count of
    records that named no ``userId``/``timestamp`` we could parse, or whose
    timestamp fell inside no known session's window -- neither is an error,
    just a record we cannot ground to a real conversation.
    """
    by_user: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for conv in conversations:
        by_user[conv["channel_user_id"]].append(conv)

    matched: dict[str, list[tuple[dict[str, Any], datetime]]] = defaultdict(list)
    unmatched = 0

    for record in records:
        user_id = clean(record.get("userId"))
        timestamp = parse_iso(record.get("timestamp"))
        if not user_id or not timestamp:
            unmatched += 1
            continue

        best_session: str | None = None
        best_slack: float | None = None
        for conv in by_user.get(user_id, []):
            lo = conv["started_at"] - _WINDOW_SLACK
            hi = conv["ended_at"] + _WINDOW_SLACK
            if lo <= timestamp <= hi:
                slack = min(
                    abs((timestamp - conv["started_at"]).total_seconds()),
                    abs((timestamp - conv["ended_at"]).total_seconds()),
                )
                if best_slack is None or slack < best_slack:
                    best_slack = slack
                    best_session = conv["session_id"]

        if best_session is None:
            unmatched += 1
            continue
        matched[best_session].append((record, timestamp))

    return matched, unmatched


# The five workflow values every seeded trace/baggage row uses (see
# REFERENCE_PARITY.md's WORKFLOW filter). A derived trace's workflow has to
# land on one of these, or it silently drops out of every workflow filter on
# the Traces/Baggage pages instead of showing up under the flow it belongs to.
_WORKFLOW_ALIASES: dict[str, str] = {
    "billing": "billing_inquiry",
    "return": "product_return",
    "returns": "product_return",
    "product": "product_inquiry",
    "itinerary": "itinerary_document",
    "booking": "booking_change",
}


def _workflow_for(inquiry_type: str | None, task_name: str | None) -> str:
    basis = inquiry_type or task_name or "general"
    slug_value = slug(basis, 48).replace("-", "_") or "general"
    return _WORKFLOW_ALIASES.get(slug_value, slug_value)


_TRACE_UPSERT = """
INSERT INTO traces (
    trace_id, conversation_id, ticket_ref, root_service, root_operation, workflow,
    outcome, status, label, started_at, duration_ms, span_count
) VALUES (%(trace_id)s, %(conversation_id)s, %(ticket_ref)s, %(root_service)s, %(root_operation)s,
          %(workflow)s, %(outcome)s, %(status)s, %(label)s, %(started_at)s, %(duration_ms)s, %(span_count)s)
"""

_SPAN_INSERT = """
INSERT INTO spans (
    span_id, trace_id, parent_span_id, service_name, operation, kind, hop_no, depth,
    start_offset_ms, duration_ms, status, is_root, attributes
) VALUES (%(span_id)s, %(trace_id)s, %(parent_span_id)s, %(service_name)s, %(operation)s, %(kind)s,
          %(hop_no)s, %(depth)s, %(start_offset_ms)s, %(duration_ms)s, %(status)s, %(is_root)s, %(attributes)s)
"""


def _build_trace_and_spans(
    session_id: str, conv: dict[str, Any], entries: list[tuple[dict[str, Any], datetime]]
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    entries.sort(key=lambda pair: pair[1])
    trace_id = f"derived-{session_id}"

    task_names = [clean(record.get("taskName")) for record, _ in entries if clean(record.get("taskName"))]
    primary_task = task_names[-1] if task_names else None  # the last task run is usually what resolved
    workflow = _workflow_for(conv.get("inquiry_type"), primary_task)

    trace_started_at = conv["started_at"] or entries[0][1]
    last_ts = max(ts for _, ts in entries)
    duration_ms = max(int(round((last_ts - trace_started_at).total_seconds() * 1000)), 1)

    span_rows: list[dict[str, Any]] = []
    any_error = False
    first_service: str | None = None

    for index, (record, ts) in enumerate(entries, start=1):
        node_name = clean(record.get("nodeName")) or "node"
        node_type = clean(record.get("type"))
        service_name = _service_for(node_name, node_type)
        first_service = first_service or service_name

        status_text = (clean(record.get("status")) or "success").lower()
        status_code = record.get("statusCode")
        is_error = status_text != "success" or (isinstance(status_code, int) and status_code >= 400)
        any_error = any_error or is_error

        offset_ms = max(int(round((ts - trace_started_at).total_seconds() * 1000)), 0)
        span_duration_ms = parse_response_time_ms(record.get("responseTime")) or 1
        api_ms = parse_response_time_ms(record.get("apiExecutionTime"))

        span_rows.append(
            {
                "span_id": f"{trace_id}-{index:03d}",
                "trace_id": trace_id,
                "parent_span_id": None,
                "service_name": service_name,
                "operation": node_name,
                "kind": "CLIENT" if node_type in ("service", "aiassist", "generativeai") else "INTERNAL",
                "hop_no": None,
                "depth": 0,
                "start_offset_ms": offset_ms,
                "duration_ms": span_duration_ms,
                "status": "ERROR" if is_error else "OK",
                "is_root": index == 1,
                "attributes": json.dumps(
                    {
                        "task_id": clean(record.get("taskId")),
                        "task_name": clean(record.get("taskName")),
                        "node_type": node_type,
                        "api_execution_ms": api_ms,
                        "source_file": record.get("_source_file"),
                    }
                ),
            }
        )

    outcome = "error" if any_error else ("abandoned" if conv.get("containment_type") == "drop_off" else "success")
    ticket_id = conv.get("ticket_id")

    trace_row = {
        "trace_id": trace_id,
        "conversation_id": session_id,
        "ticket_ref": f"ZD-{ticket_id}" if ticket_id else None,
        "root_service": first_service or "kore-dialog",
        "root_operation": primary_task or "dialog.session",
        "workflow": workflow,
        "outcome": outcome,
        "status": "ERROR" if any_error else "OK",
        "label": f"{(conv.get('inquiry_type') or primary_task or 'Session')} (derived from Kore.ai telemetry)",
        "started_at": trace_started_at,
        "duration_ms": duration_ms,
        "span_count": len(span_rows),
    }
    return trace_row, span_rows


def load(result: StageResult) -> None:
    records = performance_records()
    with get_pool().connection() as conn:
        with conn.cursor() as cur:
            conversations = _fetch_real_conversations(cur)
            by_session = {conv["session_id"]: conv for conv in conversations}

            matched, unmatched = _match_records(records, conversations)

            trace_rows: list[dict[str, Any]] = []
            span_rows: list[dict[str, Any]] = []
            for session_id, entries in matched.items():
                conv = by_session[session_id]
                trace_row, spans = _build_trace_and_spans(session_id, conv, entries)
                trace_rows.append(trace_row)
                span_rows.extend(spans)

            # Owned exclusively by this stage -- scoped delete then insert, but
            # ONLY when there is something to replace it with. A run that finds
            # no raw performance records (no files this host can read -- e.g.
            # a deployment with no local extract mount) must leave whatever was
            # derived by an earlier, better-supplied run alone rather than
            # deleting it and inserting nothing: that would make every derived
            # trace a countdown timer to the next scheduled run instead of
            # durable data. Deleting traces cascades to spans (spans.trace_id
            # ON DELETE CASCADE). "%%" escapes the literal percent for
            # psycopg's placeholder scanner.
            if trace_rows:
                cur.execute("DELETE FROM traces WHERE trace_id LIKE 'derived-%%'")
                cur.executemany(_TRACE_UPSERT, trace_rows)
                cur.executemany(_SPAN_INSERT, span_rows)
        conn.commit()

    result.add("traces", len(trace_rows))
    result.add("spans", len(span_rows))
    if not records:
        result.warn("no Kore.ai performance (per-node timing) records available -- derive_spans wrote nothing")
    result.detail = (
        f"{len(trace_rows)} derived traces / {len(span_rows)} derived spans from "
        f"{len(records)} real performance records ({unmatched} unmatched to a known session)"
    )


def run() -> StageResult:
    with run_stage("derive_spans", "Derived traces/spans from real Kore.ai per-node timing") as result:
        load(result)
    return result
