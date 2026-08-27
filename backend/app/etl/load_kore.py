"""Kore.ai loader -- population A.

Lands ``conversations`` (sessions), ``messages`` and ``nlu_events`` from the
session / message / analytics extracts, and logs the task-containment report.

Three things worth knowing before reading the code:

*   **The session page is capped.** Every extract reports ``moreAvailable: true``
    against 100 rows, which is why P-01's "100 conversations" is a floor and not
    a period total. The loader records the cap in ``conversations.raw`` and the
    provenance rows themselves are seeded (see ``seed_business``).
*   **``containmentType`` is camelCase on the wire.** ``selfService`` /
    ``dropOff`` / ``agent`` are normalised to the schema's snake_case check
    constraint values ``self_service`` / ``drop_off`` / ``agent_transfer``.
*   **The bot id on the wire is a stream id.** ``st-89af1dba-...`` is Marina.
    The API surface keys bots as ``marina`` (``settings.default_bot_id``), so the
    stream id is aliased and kept in ``bots.note`` for traceability.
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from typing import Any, Iterable

from app.core.db import get_pool
from app.etl import StageResult, clean, log, parse_iso, run_stage, slug
from app.etl.paths import (
    KORE_ANALYTICS_FILES,
    KORE_CONTAINMENT_FILES,
    KORE_MESSAGE_FILES,
    KORE_PERFORMANCE_FILES,
    KORE_SESSION_FILES,
    load_json,
)

# Kore.ai stream id -> the bot key the API and the UI use.
BOT_ID_ALIASES: dict[str, str] = {
    "st-89af1dba-973c-53e9-9fb4-eb17a40ed873": "marina",
}

CONTAINMENT_MAP = {
    "selfservice": "self_service",
    "self_service": "self_service",
    "dropoff": "drop_off",
    "drop_off": "drop_off",
    "agent": "agent_transfer",
    "agenttransfer": "agent_transfer",
    "agent_transfer": "agent_transfer",
}

NLU_RESULTS = {"successintent", "failintent", "unhandledutterance"}
_NLU_CANONICAL = {
    "successintent": "successintent",
    "failintent": "failintent",
    "unhandledutterance": "unhandledUtterance",
}

# An outgoing body seen this many times or more across the corpus is bot template
# copy rather than something composed for one guest. Used for messages.is_template.
TEMPLATE_REPEAT_THRESHOLD = 3


def bot_key(raw_bot_id: Any) -> str:
    text = clean(raw_bot_id) or "unknown"
    return BOT_ID_ALIASES.get(text, slug(text, 64))


def normalise_containment(value: Any) -> str | None:
    text = clean(value)
    if not text:
        return None
    return CONTAINMENT_MAP.get(text.replace("-", "").replace(" ", "").lower())


def _session_tag_map(tags: Any) -> dict[str, str]:
    """``tags.sessionTags`` is a list of ``{name, value}`` objects, not a map."""
    out: dict[str, str] = {}
    if not isinstance(tags, dict):
        return out
    for entry in tags.get("sessionTags") or []:
        if isinstance(entry, dict):
            name = clean(entry.get("name"))
            value = clean(entry.get("value"))
            if name and value and name not in out:
                out[name] = value
    return out


def _alt_text_values(tags: Any) -> list[str]:
    """``altText`` holds ``{name: 'label', value: 'Onboard Purchase'}`` objects."""
    if not isinstance(tags, dict):
        return []
    values: list[str] = []
    for entry in tags.get("altText") or []:
        if isinstance(entry, dict):
            value = clean(entry.get("value"))
            if value:
                values.append(value)
        else:
            value = clean(entry)
            if value:
                values.append(value)
    return values


def _as_int(value: Any) -> int | None:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Sessions -> conversations
# ---------------------------------------------------------------------------
def _build_session_row(raw: dict[str, Any], source_file: str) -> dict[str, Any] | None:
    session_id = clean(raw.get("sessionId"))
    if not session_id:
        return None

    started_at = parse_iso(raw.get("start_time"))
    ended_at = parse_iso(raw.get("end_time"))
    duration = None
    if started_at and ended_at:
        seconds = int(round((ended_at - started_at).total_seconds()))
        duration = max(seconds, 0)  # schema forbids a negative duration

    tag_map = _session_tag_map(raw.get("tags"))
    languages = raw.get("session_lang")
    language = clean(languages[0]) if isinstance(languages, list) and languages else None

    return {
        "session_id": session_id,
        "bot_id": bot_key(raw.get("botId")),
        "channel": clean(raw.get("channel")),
        "channel_user_id": clean(raw.get("userId")),
        "language": language,
        "started_at": started_at,
        "ended_at": ended_at,
        "duration_seconds": duration,
        "message_count": _as_int(raw.get("noOfMessagesExchanged")),
        "task_count": _as_int(raw.get("noOfTasksExecuted")),
        "containment_type": normalise_containment(raw.get("containmentType")),
        "session_status": clean(raw.get("sessionStatus")),
        "is_developer": bool(raw.get("isDeveloper")),
        "ticket_id": _as_int(tag_map.get("TicketID")),
        "inquiry_type": tag_map.get("inquiryType"),
        "event_name": tag_map.get("eventName"),
        "alt_text": _alt_text_values(raw.get("tags")),
        "source_file": source_file,
        "raw": json.dumps({"source_file": source_file, "session": raw}),
    }


_CONVERSATION_UPSERT = """
INSERT INTO conversations (
    session_id, bot_id, channel, channel_user_id, language,
    started_at, ended_at, duration_seconds, message_count, task_count,
    containment_type, session_status, is_developer,
    ticket_id, inquiry_type, event_name, alt_text, source_file, raw
) VALUES (
    %(session_id)s, %(bot_id)s, %(channel)s, %(channel_user_id)s, %(language)s,
    %(started_at)s, %(ended_at)s, %(duration_seconds)s, %(message_count)s, %(task_count)s,
    %(containment_type)s, %(session_status)s, %(is_developer)s,
    %(ticket_id)s, %(inquiry_type)s, %(event_name)s, %(alt_text)s, %(source_file)s, %(raw)s
)
ON CONFLICT (session_id) DO UPDATE SET
    bot_id = EXCLUDED.bot_id,
    channel = COALESCE(EXCLUDED.channel, conversations.channel),
    channel_user_id = COALESCE(EXCLUDED.channel_user_id, conversations.channel_user_id),
    language = COALESCE(EXCLUDED.language, conversations.language),
    started_at = COALESCE(EXCLUDED.started_at, conversations.started_at),
    ended_at = COALESCE(EXCLUDED.ended_at, conversations.ended_at),
    duration_seconds = COALESCE(EXCLUDED.duration_seconds, conversations.duration_seconds),
    message_count = COALESCE(EXCLUDED.message_count, conversations.message_count),
    task_count = COALESCE(EXCLUDED.task_count, conversations.task_count),
    containment_type = COALESCE(EXCLUDED.containment_type, conversations.containment_type),
    session_status = COALESCE(EXCLUDED.session_status, conversations.session_status),
    is_developer = EXCLUDED.is_developer,
    ticket_id = COALESCE(EXCLUDED.ticket_id, conversations.ticket_id),
    inquiry_type = COALESCE(EXCLUDED.inquiry_type, conversations.inquiry_type),
    event_name = COALESCE(EXCLUDED.event_name, conversations.event_name),
    alt_text = COALESCE(NULLIF(EXCLUDED.alt_text, '{}'), conversations.alt_text),
    source_file = EXCLUDED.source_file,
    raw = EXCLUDED.raw
"""

_BOT_UPSERT = """
INSERT INTO bots (bot_id, bot_name, environment, instrumented, data_held, note)
VALUES (%s, %s, %s, %s, %s, %s)
ON CONFLICT (bot_id) DO UPDATE SET data_held = true
"""


def _ensure_bots(cur: Any, bot_ids: Iterable[str], stream_ids: dict[str, str]) -> None:
    """Guarantee the FK target exists for every bot the extracts mention.

    ``seed_business`` owns the descriptive bot metadata; this only makes sure a
    bot seen in a raw extract cannot fail the foreign key, and flips
    ``data_held`` to true because we now demonstrably hold its conversations.
    """
    for bot_id in sorted(set(bot_ids)):
        note = f"Kore.ai stream id {stream_ids.get(bot_id, 'unknown')}"
        cur.execute(_BOT_UPSERT, (bot_id, bot_id.title(), "QA", False, True, note))


def load_sessions(result: StageResult) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    stream_ids: dict[str, str] = {}
    caps: list[str] = []

    for relative in KORE_SESSION_FILES:
        payload = load_json(relative)
        if payload is None:
            continue
        sessions = payload.get("sessions") if isinstance(payload, dict) else None
        if not isinstance(sessions, list):
            result.warn(f"unexpected session shape in {relative}: no sessions[]")
            continue
        caps.append(
            f"{relative}: rows={len(sessions)} total={payload.get('total')} "
            f"moreAvailable={payload.get('moreAvailable')}"
        )
        for raw in sessions:
            if not isinstance(raw, dict):
                continue
            row = _build_session_row(raw, relative)
            if row is None:
                continue
            stream_ids.setdefault(row["bot_id"], clean(raw.get("botId")) or "unknown")
            existing = rows.get(row["session_id"])
            if existing is None:
                rows[row["session_id"]] = row
            else:
                # Merge: a later extract may carry tags the first one lacked.
                for key, value in row.items():
                    if existing.get(key) in (None, [], "") and value not in (None, [], ""):
                        existing[key] = value

    if not rows:
        result.warn("no Kore.ai sessions parsed")
        return rows

    ordered = [rows[key] for key in sorted(rows)]
    with get_pool().connection() as conn:
        with conn.cursor() as cur:
            _ensure_bots(cur, (row["bot_id"] for row in ordered), stream_ids)
            cur.executemany(_CONVERSATION_UPSERT, ordered)
        conn.commit()

    result.add("conversations", len(ordered))
    for note in caps:
        log.info("[load_kore] %s", note)
    return rows


# ---------------------------------------------------------------------------
# Messages
# ---------------------------------------------------------------------------
def _message_body(raw: dict[str, Any]) -> tuple[str | None, str | None]:
    """Join every text component into one body; return (body, first component type)."""
    parts: list[str] = []
    component_type: str | None = None
    for component in raw.get("components") or []:
        if not isinstance(component, dict):
            continue
        component_type = component_type or clean(component.get("cT"))
        data = component.get("data")
        if isinstance(data, dict):
            text = data.get("text")
            if text:
                parts.append(str(text))
    return ("\n".join(parts) or None), component_type


def load_messages(result: StageResult, known_sessions: set[str]) -> None:
    rows: dict[str, dict[str, Any]] = {}
    stream_ids: dict[str, str] = {}

    for relative in KORE_MESSAGE_FILES:
        payload = load_json(relative)
        if payload is None:
            continue
        messages = payload.get("messages") if isinstance(payload, dict) else None
        if not isinstance(messages, list):
            result.warn(f"unexpected message shape in {relative}: no messages[]")
            continue
        for raw in messages:
            if not isinstance(raw, dict):
                continue
            message_id = clean(raw.get("_id"))
            direction = clean(raw.get("type"))
            if not message_id or direction not in {"incoming", "outgoing"}:
                continue
            body, component_type = _message_body(raw)
            bot = bot_key(raw.get("botId"))
            stream_ids.setdefault(bot, clean(raw.get("botId")) or "unknown")
            rows.setdefault(
                message_id,
                {
                    "message_id": message_id,
                    "session_id": clean(raw.get("sessionId")),
                    "bot_id": bot,
                    "direction": direction,
                    "body": body,
                    "component_type": component_type,
                    "task_name": clean(raw.get("tN")),
                    "intent": clean(raw.get("tN")),
                    "created_at": parse_iso(raw.get("createdOn")),
                    "tags": json.dumps(raw.get("tags") or {}),
                    "_channel": clean(raw.get("chnl")),
                    "_language": clean(raw.get("lang")),
                },
            )

    if not rows:
        result.warn("no Kore.ai messages parsed")
        return

    ordered = list(rows.values())

    # Sessions referenced by a message but absent from the session page get a
    # stub conversation, otherwise the FK would drop real turns on the floor.
    # The stub carries no duration, so it cannot pollute the duration panel.
    missing = sorted(
        {
            row["session_id"]
            for row in ordered
            if row["session_id"] and row["session_id"] not in known_sessions
        }
    )
    stubs: list[dict[str, Any]] = []
    for session_id in missing:
        turns = [row for row in ordered if row["session_id"] == session_id]
        stamps = [row["created_at"] for row in turns if row["created_at"]]
        stubs.append(
            {
                "session_id": session_id,
                "bot_id": turns[0]["bot_id"],
                "channel": turns[0]["_channel"],
                "channel_user_id": None,
                "language": turns[0]["_language"],
                "started_at": min(stamps) if stamps else None,
                "ended_at": max(stamps) if stamps else None,
                "duration_seconds": None,
                "message_count": len(turns),
                "task_count": None,
                "containment_type": None,
                "session_status": None,
                "is_developer": False,
                "ticket_id": None,
                "inquiry_type": None,
                "event_name": None,
                "alt_text": [],
                "source_file": "getMessagesV2 (stub: session absent from the session page)",
                "raw": json.dumps({"stub_reason": "message-only session"}),
            }
        )

    # Turn numbering is per session, ordered by time then id so it is stable.
    by_session: dict[str | None, list[dict[str, Any]]] = defaultdict(list)
    for row in ordered:
        by_session[row["session_id"]].append(row)
    for turns in by_session.values():
        turns.sort(key=lambda item: (item["created_at"] or _EPOCH, item["message_id"]))
        for index, row in enumerate(turns, start=1):
            row["turn_no"] = index

    # Bot template copy: identical outgoing text repeated across the corpus.
    body_counts = Counter(row["body"] for row in ordered if row["direction"] == "outgoing" and row["body"])
    for row in ordered:
        row["is_template"] = bool(
            row["direction"] == "outgoing"
            and row["body"]
            and body_counts[row["body"]] >= TEMPLATE_REPEAT_THRESHOLD
        )

    with get_pool().connection() as conn:
        with conn.cursor() as cur:
            _ensure_bots(cur, (row["bot_id"] for row in ordered), stream_ids)
            if stubs:
                cur.executemany(_CONVERSATION_UPSERT, stubs)
                result.add("conversations", len(stubs))
            cur.executemany(
                """
                INSERT INTO messages (
                    message_id, session_id, bot_id, turn_no, direction, body,
                    component_type, task_name, intent, created_at, is_template, tags
                ) VALUES (
                    %(message_id)s, %(session_id)s, %(bot_id)s, %(turn_no)s, %(direction)s, %(body)s,
                    %(component_type)s, %(task_name)s, %(intent)s, %(created_at)s, %(is_template)s, %(tags)s
                )
                ON CONFLICT (message_id) DO UPDATE SET
                    session_id = EXCLUDED.session_id,
                    bot_id = EXCLUDED.bot_id,
                    turn_no = EXCLUDED.turn_no,
                    direction = EXCLUDED.direction,
                    body = EXCLUDED.body,
                    component_type = EXCLUDED.component_type,
                    task_name = EXCLUDED.task_name,
                    intent = EXCLUDED.intent,
                    created_at = EXCLUDED.created_at,
                    is_template = EXCLUDED.is_template,
                    tags = EXCLUDED.tags
                """,
                ordered,
            )
        conn.commit()
    result.add("messages", len(ordered))


# ---------------------------------------------------------------------------
# NLU analytics
# ---------------------------------------------------------------------------
def _identified_intents(analysis: Any) -> list[str]:
    """``identifiedIntents`` is usually ``["BillingGratuityIssue"]`` but can hold objects."""
    if not isinstance(analysis, dict):
        return []
    values: list[str] = []
    for entry in analysis.get("identifiedIntents") or []:
        if isinstance(entry, dict):
            value = clean(entry.get("intent") or entry.get("name") or entry.get("taskName"))
        else:
            value = clean(entry)
        if value:
            values.append(value)
    return values


def load_nlu(result: StageResult) -> None:
    rows: dict[str, tuple[Any, ...]] = {}
    bot_ids: set[str] = set()

    for relative, fallback in KORE_ANALYTICS_FILES:
        payload = load_json(relative)
        if payload is None:
            continue
        records = payload.get("result") if isinstance(payload, dict) else None
        if not isinstance(records, list):
            result.warn(f"unexpected analytics shape in {relative}: no result[]")
            continue
        for raw in records:
            if not isinstance(raw, dict):
                continue
            record_id = clean(raw.get("_id"))
            analysis = raw.get("NLAnalysis") if isinstance(raw.get("NLAnalysis"), dict) else {}
            # A single file mixes outcomes (the "unhandledutterance" export also
            # carries successintent rows), so trust the record over the filename.
            declared = (clean(analysis.get("result")) or "").lower()
            outcome = _NLU_CANONICAL.get(declared, fallback)
            bot = bot_key(raw.get("botId") or raw.get("streamId"))
            bot_ids.add(bot)
            key = record_id or f"{raw.get('messageId')}|{outcome}"
            rows.setdefault(
                key,
                (
                    bot,
                    clean(raw.get("sessionId")),
                    clean(raw.get("messageId")),
                    outcome,
                    clean(raw.get("utterance")),
                    clean(raw.get("intent")),
                    clean(raw.get("taskName")),
                    clean(analysis.get("nodeName")),
                    _identified_intents(analysis),
                    bool(raw.get("isAmbiguous")),
                    parse_iso(raw.get("timestamp")),
                ),
            )

    if not rows:
        result.warn("no Kore.ai NLU records parsed")
        return

    ordered = list(rows.values())
    with get_pool().connection() as conn:
        with conn.cursor() as cur:
            _ensure_bots(cur, bot_ids, {})
            # nlu_events has only a serial PK, so idempotency is a scoped refresh.
            # This loader is the sole writer of the table.
            cur.execute("DELETE FROM nlu_events WHERE bot_id = ANY(%s)", (sorted(bot_ids),))
            cur.executemany(
                """
                INSERT INTO nlu_events (
                    bot_id, session_id, message_id, result, utterance, intent,
                    task_name, node_name, identified_intents, is_ambiguous, occurred_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                ordered,
            )
        conn.commit()

    counts = Counter(row[3] for row in ordered)
    result.add("nlu_events", len(ordered))
    log.info("[load_kore] NLU outcomes: %s", dict(sorted(counts.items())))


# ---------------------------------------------------------------------------
# Task containment report (no table of its own -- logged, and consumed by
# derive_spans to decide a derived trace's outcome)
# ---------------------------------------------------------------------------
def containment_by_task() -> dict[str, dict[str, Any]]:
    """``{taskName: {self_service, drop_off, agent_transfer, executions, status}}``.

    Shared with ``derive_spans`` so a derived trace can inherit the real
    containment outcome of the task it ran.
    """
    tasks: dict[str, dict[str, Any]] = {}
    for relative in KORE_CONTAINMENT_FILES:
        payload = load_json(relative)
        if not isinstance(payload, dict):
            continue
        report = payload.get("tasksExecutionReport")
        if not isinstance(report, dict):
            # "Containment Report - Poll Status" in Extracts Prod is an
            # IN_PROGRESS job envelope with no data yet -- expected, not an error.
            log.info("[load_kore] containment report %s has no data block yet", relative)
            continue
        data = report.get("data")
        if not isinstance(data, dict):
            continue
        for day, entries in data.items():
            if not isinstance(entries, list):
                continue
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                name = clean(entry.get("taskName"))
                if not name:
                    continue
                bucket = tasks.setdefault(
                    name,
                    {
                        "task_name": name,
                        "executions": 0,
                        "sessions": 0,
                        "self_service": 0,
                        "drop_off": 0,
                        "agent_transfer": 0,
                        "status": clean(entry.get("Status")),
                        "days": set(),
                    },
                )
                bucket["executions"] += int(entry.get("totalExecution") or 0)
                bucket["sessions"] += int(entry.get("totalSession") or 0)
                bucket["self_service"] += int(entry.get("selfServiceSessions") or 0)
                bucket["drop_off"] += int(entry.get("dropOffSessions") or 0)
                bucket["agent_transfer"] += int(entry.get("agentTransferSessions") or 0)
                bucket["days"].add(clean(day))
                if clean(entry.get("Status")) == "failtask":
                    bucket["status"] = "failtask"
    return tasks


def performance_records() -> list[dict[str, Any]]:
    """Every per-node timing record we hold, de-duplicated across both extracts."""
    seen: set[tuple[Any, ...]] = set()
    records: list[dict[str, Any]] = []
    for relative in KORE_PERFORMANCE_FILES:
        payload = load_json(relative)
        if not isinstance(payload, dict):
            continue
        entries = payload.get("result")
        if not isinstance(entries, list):
            log.warning("[load_kore] unexpected performance shape in %s", relative)
            continue
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            key = (
                clean(entry.get("nodeName")),
                clean(entry.get("taskName")),
                clean(entry.get("timestamp")),
                clean(entry.get("channelUId")),
                clean(entry.get("responseTime")),
            )
            if key in seen:
                continue
            seen.add(key)
            enriched = dict(entry)
            enriched["_source_file"] = relative
            records.append(enriched)
    return records


_EPOCH = parse_iso("1970-01-01T00:00:00Z")


def load(result: StageResult) -> None:
    sessions = load_sessions(result)
    load_messages(result, set(sessions))
    load_nlu(result)

    tasks = containment_by_task()
    if tasks:
        totals = {
            "self_service": sum(task["self_service"] for task in tasks.values()),
            "drop_off": sum(task["drop_off"] for task in tasks.values()),
            "agent_transfer": sum(task["agent_transfer"] for task in tasks.values()),
        }
        log.info(
            "[load_kore] containment report: %d tasks, %s (no table -- consumed by derive_spans)",
            len(tasks),
            totals,
        )

    perf = performance_records()
    log.info("[load_kore] %d per-node performance records available for derive_spans", len(perf))
    result.detail = (
        f"{len(sessions)} sessions, {len(tasks)} containment tasks, {len(perf)} node timings"
    )


def run() -> StageResult:
    with run_stage("load_kore", "Kore.ai sessions, messages and NLU analytics") as result:
        load(result)
    return result
