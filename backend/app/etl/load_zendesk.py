"""Zendesk loader -- population B.

Reads the raw search-API envelopes (``{results:[...], count, next_page}``) and
lands ``tickets``, ``ticket_tags`` and ``backend_failures``.

Two things carry all the analytical weight:

1.  **The markdown description.** The bot writes the One Spa World intake form
    into the ticket body as ``**Cruise Line :** PRINCESS CRUISES LTD.``. Nothing
    is available as a first-class Zendesk field on the search response we hold,
    so cruise line, ship, cabin, dates and amounts are parsed out of prose. That
    is why "cruise line named" is a *coverage* metric (23 of 28) rather than a
    guarantee.
2.  **The tag vocabulary.** A ticket is bot-raised when it carries ``chatbot`` or
    ``kore_ai``. The ``osw_*`` tags are the form's own Inquiry Type / order route
    / return reason values, and ``sentiment__*`` is the bot's mood scoring. Those
    tags -- not the prose -- are the taxonomy, which is why P-44 sums cleanly to
    22 with nothing missing.
"""
from __future__ import annotations

import json
import re
from typing import Any, Iterable

from app.core.db import get_pool
from app.etl import (
    StageResult,
    clean,
    log,
    parse_amount,
    parse_date_loose,
    parse_iso,
    run_stage,
)
from app.etl.paths import ZENDESK_FILES, load_json

# ---------------------------------------------------------------------------
# Description parsing
# ---------------------------------------------------------------------------
# Captures every "**Label :** value" pair on one line. Handles both spacing
# variants -- "**Cruise Line :**" and "**Cruise Line:**" -- because the bot
# templates disagree with each other, and a missed variant silently drops a
# ticket out of the cruise-line panel.
_FIELD_RE = re.compile(
    r"\*\*\s*(?P<label>[A-Za-z][A-Za-z0-9 ()/&.'’_-]{0,44}?)\s*:\s*\*\*[ \t]*(?P<value>[^\n]*)"
)

# label (lower-cased, whitespace-collapsed) -> the column it feeds. First match in
# the alias tuple wins, so the most specific spelling is listed first.
_FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "cruise_line": ("cruise line", "cruise line name", "cruiseline"),
    "ship_name": ("ship name", "vessel name", "ship", "vessel"),
    "sail_start": ("start date", "sail date", "sailing date", "cruise start date"),
    "sail_end": ("end date", "sail end date", "cruise end date", "disembark date"),
    # The billing/service templates say "Service Date", the returns template says
    # "Purchase Date". Both answer "when did the thing being disputed happen?".
    "service_date": ("service date", "purchase date", "treatment date"),
    "cabin_number": ("cabin number", "cabin", "stateroom", "stateroom number"),
    "charge_amount": ("amount charged", "charge", "amount", "total charged"),
    "spa_guest_name": ("spa guest name(s)", "spa guest name", "spa guest names", "guest name"),
    "guest_name": ("name", "customer name", "full name"),
    "guest_email": ("email", "email address", "e-mail"),
    "return_reason_text": ("return reason", "reason"),
    "delivery_type": ("delivery type", "order type"),
}
_LABEL_TO_FIELD: dict[str, str] = {
    label: field for field, labels in _FIELD_ALIASES.items() for label in labels
}


def parse_description_fields(description: str | None) -> dict[str, str]:
    """Flatten the markdown body into ``{field: value}`` using the alias table."""
    if not description:
        return {}
    found: dict[str, str] = {}
    for match in _FIELD_RE.finditer(description):
        label = re.sub(r"\s+", " ", match.group("label")).strip().lower()
        field = _LABEL_TO_FIELD.get(label)
        if field is None:
            continue
        value = clean(match.group("value"))
        # First occurrence wins: the customer-details block comes before the
        # products block, and only the first is the authoritative field.
        if value and field not in found:
            found[field] = value
    return found


# ---------------------------------------------------------------------------
# Cruise line canonicalisation
# ---------------------------------------------------------------------------
# The canonical set the business view ranks on. Matching is substring-based
# because the guests and the form both write the line name freehand:
# "PRINCESS CRUISES LTD.", "Princess Cruises Ltd.", "Virgin Cruises".
CANONICAL_LINES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Norwegian", ("norwegian", "ncl")),
    ("Princess", ("princess",)),
    ("Carnival", ("carnival",)),
    ("Celebrity", ("celebrity",)),
    ("Royal Caribbean", ("royal caribbean", "rccl", "royal carribean")),
    ("Disney", ("disney",)),
    ("Cunard", ("cunard",)),
    ("MSC", ("msc",)),
    ("Holland America", ("holland america", "hollandamerica", "hal ")),
    ("Virgin Voyages", ("virgin",)),
)

# Ship families, used only when the cruise-line field itself is missing. This is
# the same naming gap the enrichment-failure panel complains about: the guest who
# typed "Holland America" in the *ship* box is still a Holland America guest.
SHIP_LINE_HINTS: tuple[tuple[str, str], ...] = (
    ("holland america", "Holland America"),
    ("koningsdam", "Holland America"),
    ("westerdam", "Holland America"),
    ("nieuw ", "Holland America"),
    ("zuiderdam", "Holland America"),
    ("oosterdam", "Holland America"),
    ("noordam", "Holland America"),
    ("eurodam", "Holland America"),
    ("rotterdam", "Holland America"),
    ("volendam", "Holland America"),
    ("zaandam", "Holland America"),
    ("veendam", "Holland America"),
    ("of the seas", "Royal Caribbean"),
    ("princess", "Princess"),
    ("norwegian", "Norwegian"),
    ("carnival", "Carnival"),
    ("celebrity", "Celebrity"),
    ("disney ", "Disney"),
    ("queen mary", "Cunard"),
    ("queen elizabeth", "Cunard"),
    ("queen victoria", "Cunard"),
    ("queen anne", "Cunard"),
    ("valiant lady", "Virgin Voyages"),
    ("scarlet lady", "Virgin Voyages"),
    ("resilient lady", "Virgin Voyages"),
    ("brilliant lady", "Virgin Voyages"),
)

# Phrases distinctive enough to trust inside free prose. Deliberately narrower
# than CANONICAL_LINES -- a bare "princess" in a sentence would be a guess, but
# "Allure of the Seas" or "Norwegian Cruise Line" is evidence.
FREE_TEXT_LINE_HINTS: tuple[tuple[str, str], ...] = (
    ("norwegian cruise line", "Norwegian"),
    ("royal caribbean", "Royal Caribbean"),
    ("princess cruises", "Princess"),
    ("carnival cruise", "Carnival"),
    ("celebrity cruises", "Celebrity"),
    ("holland america", "Holland America"),
    ("virgin voyages", "Virgin Voyages"),
    ("disney cruise", "Disney"),
    ("cunard", "Cunard"),
    ("msc cruises", "MSC"),
    ("of the seas", "Royal Caribbean"),
)


def canonical_cruise_line(value: str | None) -> str | None:
    """Map a freehand cruise-line string onto the canonical set.

    An unrecognised line is upper-cased and kept as itself. It is deliberately
    NOT bucketed into "Other": a partner we cannot name yet is a naming gap to
    fix, and hiding it inside a bucket makes that gap invisible.
    """
    text = clean(value)
    if not text:
        return None
    lowered = text.lower()
    for canonical, needles in CANONICAL_LINES:
        if any(needle in lowered for needle in needles):
            return canonical
    return text.upper()


def infer_line_from_ship(ship: str | None) -> str | None:
    text = clean(ship)
    if not text:
        return None
    lowered = text.lower()
    for needle, canonical in SHIP_LINE_HINTS:
        if needle in lowered:
            return canonical
    return None


def infer_line_from_free_text(description: str | None) -> str | None:
    if not description:
        return None
    lowered = description.lower()
    for needle, canonical in FREE_TEXT_LINE_HINTS:
        if needle in lowered:
            return canonical
    return None


# ---------------------------------------------------------------------------
# Tag taxonomy
# ---------------------------------------------------------------------------
BOT_TAGS = {"chatbot", "kore_ai"}

_FAMILY_RULES: tuple[tuple[str, str], ...] = (
    ("prefix:osw_", "osw"),
    ("prefix:intent_confidence__", "intent"),
    ("prefix:intent__", "intent"),
    ("prefix:sentiment_confidence__", "sentiment"),
    ("prefix:sentiment__", "sentiment"),
    ("prefix:system_", "system"),
)


def tag_family(tag: str) -> str:
    """'osw' | 'intent' | 'sentiment' | 'backend' | 'system' | 'other'."""
    lowered = tag.lower()
    for rule, family in _FAMILY_RULES:
        prefix = rule.split(":", 1)[1]
        if lowered.startswith(prefix):
            return family
    # Backend/automation signals are named after the step that broke, e.g.
    # returns_documentcreaterequestfailed -- so match on the failure word.
    if "fail" in lowered or "error" in lowered:
        return "backend"
    return "other"


# Inquiry Type (the "flow" the guest needed). Ordered: the first rule that
# matches wins. The osw_* tags are the form's own values and therefore rank
# above the older tts_/legacy tags.
_FLOW_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Return inquiry", ("osw_product_return",)),
    ("Asked for a person", ("osw_talk_to_human", "talktohuman")),
    ("Spa product", ("osw_product_inquiry",)),
    (
        "Pricing issue",
        (
            "osw_billing",
            "osw_incorrect_overcharged_amount",
            "osw_charged_twice_for_same_service",
            "osw_gratuity_service_charge_dispute",
            "maritime_pricing_issue",
            "overcharged",
        ),
    ),
    ("Onboard service", ("osw_service_inquiry", "osw_onboard_service", "osw_fitness")),
    ("HD order", ("order_inquiry", "tts_order")),
    ("Spa product", ("item_s__damaged_or_incorrect", "tts_product_return", "product_return")),
)

# Tags that name a bucket instead of a flow. When one of these is all we have,
# fall back to the words the guest actually used before giving up.
_FALLBACK_FLOW_TAGS = {"osw_other_fallback", "osw_other2", "osw_other3", "osw_other4"}
_PRICING_WORDS = ("refund", "overcharg", "charged", "charge for", "price", "pricing", "billing", "cost")

ORDER_ROUTE_TAGS = {
    "osw_onboard_purchase": "Onboard purchase",
    "osw_home_delivery_hd": "Home delivery order",
}

RETURN_REASON_TAGS = {
    "osw_health_or_sensitivity_concern": "Reaction or health concern",
    # NOTE the curly apostrophe: the tag really is osw_products_didn’t_meet_expectation.
    "osw_products_didn’t_meet_expectation": "Did not meet expectation",
    "osw_products_didnt_meet_expectation": "Did not meet expectation",
    "osw_order_delivery_or_billing_issue": "Order, delivery or billing",
    "osw_items_damaged_or_incorrect": "Items damaged or incorrect",
    "osw_other2": "Other",
    "osw_other3": "Other",
    "osw_other4": "Other",
    "osw_other_fallback": "Other",
}

SENTIMENT_LABELS = {
    "very_negative": "very negative",
    "negative": "negative",
    "neutral": "neutral",
    "positive": "positive",
    "very_positive": "very positive",
}

# Backend/automation failure signals, labelled and placed on the pipeline stage
# they belong to so the panel can say *where* automation broke.
BACKEND_FAILURE_META: dict[str, tuple[str, str]] = {
    "returns_documentcreaterequestfailed": (
        "Returns document create request failed",
        "returns",
    ),
    "transactions_documentcreaterequestfailed": (
        "Transaction document create request failed",
        "transactions",
    ),
}
_STAGE_HINTS: tuple[tuple[str, str], ...] = (
    ("postvoyageproductsreturn", "returns"),
    ("postvoyagetransactions", "transactions"),
    ("reservation", "reservations"),
    ("transaction", "transactions"),
    ("return", "returns"),
    ("eform", "eform"),
    ("notif", "notification"),
    ("document", "returns"),
)


def _failure_stage(tag: str) -> str | None:
    lowered = tag.lower()
    for needle, stage in _STAGE_HINTS:
        if needle in lowered:
            return stage
    return None


def _failure_label(tag: str) -> str:
    words = tag.replace("__", " ").replace("_", " ").strip()
    return words[:1].upper() + words[1:]


def _derive_flow(tags: set[str], description: str | None) -> str | None:
    for label, needles in _FLOW_RULES:
        if any(needle in tags for needle in needles):
            return label
    if tags & _FALLBACK_FLOW_TAGS:
        lowered = (description or "").lower()
        if any(word in lowered for word in _PRICING_WORDS):
            return "Pricing issue"
    return None  # "No flow recorded"


def _first_tag_value(tags: Iterable[str], prefix: str) -> str | None:
    for tag in tags:
        if tag.lower().startswith(prefix):
            return tag[len(prefix) :] or None
    return None


# ---------------------------------------------------------------------------
# Row building
# ---------------------------------------------------------------------------
def build_ticket_row(raw: dict[str, Any], source_file: str) -> dict[str, Any] | None:
    ticket_id = raw.get("id")
    if not isinstance(ticket_id, int):
        return None

    description: str | None = raw.get("description")
    fields = parse_description_fields(description)
    tags = [str(tag) for tag in (raw.get("tags") or [])]
    tag_set = {tag.lower() for tag in tags}

    ship_name = clean(fields.get("ship_name"))
    cruise_line = canonical_cruise_line(fields.get("cruise_line"))
    if cruise_line is None:
        # Ship box holds the line name (the "Holland America" case), or the line
        # is only named in the guest's own words further down the ticket.
        cruise_line = infer_line_from_ship(ship_name) or infer_line_from_free_text(description)

    via = raw.get("via") or {}
    via_source = via.get("source") or {}
    satisfaction = raw.get("satisfaction_rating") or {}

    inquiry_type = _derive_flow(tag_set, description)
    order_route = next((label for tag, label in ORDER_ROUTE_TAGS.items() if tag in tag_set), None)
    return_reason = None
    if inquiry_type == "Return inquiry":
        # Every return ticket carries exactly one reason tag; only read it on a
        # return so a non-return "other" tag cannot invent a return reason.
        return_reason = next(
            (label for tag, label in RETURN_REASON_TAGS.items() if tag in tag_set), None
        )

    sentiment_raw = _first_tag_value(tag_set, "sentiment__")
    sentiment = SENTIMENT_LABELS.get(sentiment_raw or "", sentiment_raw)

    charge = parse_amount(fields.get("charge_amount"))

    return {
        "ticket_id": ticket_id,
        "subject": clean(raw.get("subject")) or clean(raw.get("raw_subject")),
        "description": description,
        "status": clean(raw.get("status")),
        "priority": clean(raw.get("priority")),
        "ticket_type": clean(raw.get("type")),
        "created_at": parse_iso(raw.get("created_at")),
        "updated_at": parse_iso(raw.get("updated_at")),
        "via_channel": clean(via.get("channel")),
        "via_source_rel": clean(via_source.get("rel")),
        "requester_id": raw.get("requester_id"),
        "submitter_id": raw.get("submitter_id"),
        "assignee_id": raw.get("assignee_id"),
        "group_id": raw.get("group_id"),
        "brand_id": raw.get("brand_id"),
        "is_bot_raised": bool(tag_set & BOT_TAGS),
        "cruise_line": cruise_line,
        "ship_name": ship_name,
        "sail_start": parse_date_loose(fields.get("sail_start")),
        "sail_end": parse_date_loose(fields.get("sail_end")),
        "service_date": parse_date_loose(fields.get("service_date")),
        "cabin_number": clean(fields.get("cabin_number")),
        "charge_amount": charge,
        "spa_guest_name": clean(fields.get("spa_guest_name")) or clean(fields.get("guest_name")),
        "inquiry_type": inquiry_type,
        "order_route": order_route,
        "return_reason": return_reason,
        "sentiment": sentiment,
        "sentiment_conf": _first_tag_value(tag_set, "sentiment_confidence__"),
        "intent_tag": _first_tag_value(tag_set, "intent__"),
        "intent_conf": _first_tag_value(tag_set, "intent_confidence__"),
        "language_tag": _first_tag_value(tag_set, "language__"),
        "satisfaction_score": clean(satisfaction.get("score")),
        "tags": tags,
        "custom_fields": json.dumps(raw.get("custom_fields") or []),
        "raw": json.dumps({"source_file": source_file, "ticket": raw}),
        "correlated_session_id": None,
    }


_TICKET_UPSERT = """
INSERT INTO tickets (
    ticket_id, subject, description, status, priority, ticket_type,
    created_at, updated_at, via_channel, via_source_rel,
    requester_id, submitter_id, assignee_id, group_id, brand_id, is_bot_raised,
    cruise_line, ship_name, sail_start, sail_end, service_date,
    cabin_number, charge_amount, spa_guest_name,
    inquiry_type, order_route, return_reason,
    sentiment, sentiment_conf, intent_tag, intent_conf, language_tag,
    satisfaction_score, tags, custom_fields, raw
) VALUES (
    %(ticket_id)s, %(subject)s, %(description)s, %(status)s, %(priority)s, %(ticket_type)s,
    %(created_at)s, %(updated_at)s, %(via_channel)s, %(via_source_rel)s,
    %(requester_id)s, %(submitter_id)s, %(assignee_id)s, %(group_id)s, %(brand_id)s, %(is_bot_raised)s,
    %(cruise_line)s, %(ship_name)s, %(sail_start)s, %(sail_end)s, %(service_date)s,
    %(cabin_number)s, %(charge_amount)s, %(spa_guest_name)s,
    %(inquiry_type)s, %(order_route)s, %(return_reason)s,
    %(sentiment)s, %(sentiment_conf)s, %(intent_tag)s, %(intent_conf)s, %(language_tag)s,
    %(satisfaction_score)s, %(tags)s, %(custom_fields)s, %(raw)s
)
ON CONFLICT (ticket_id) DO UPDATE SET
    subject = EXCLUDED.subject,
    description = EXCLUDED.description,
    status = EXCLUDED.status,
    priority = EXCLUDED.priority,
    ticket_type = EXCLUDED.ticket_type,
    created_at = EXCLUDED.created_at,
    updated_at = EXCLUDED.updated_at,
    via_channel = EXCLUDED.via_channel,
    via_source_rel = EXCLUDED.via_source_rel,
    requester_id = EXCLUDED.requester_id,
    submitter_id = EXCLUDED.submitter_id,
    assignee_id = EXCLUDED.assignee_id,
    group_id = EXCLUDED.group_id,
    brand_id = EXCLUDED.brand_id,
    is_bot_raised = EXCLUDED.is_bot_raised,
    cruise_line = EXCLUDED.cruise_line,
    ship_name = EXCLUDED.ship_name,
    sail_start = EXCLUDED.sail_start,
    sail_end = EXCLUDED.sail_end,
    service_date = EXCLUDED.service_date,
    cabin_number = EXCLUDED.cabin_number,
    charge_amount = EXCLUDED.charge_amount,
    spa_guest_name = EXCLUDED.spa_guest_name,
    inquiry_type = EXCLUDED.inquiry_type,
    order_route = EXCLUDED.order_route,
    return_reason = EXCLUDED.return_reason,
    sentiment = EXCLUDED.sentiment,
    sentiment_conf = EXCLUDED.sentiment_conf,
    intent_tag = EXCLUDED.intent_tag,
    intent_conf = EXCLUDED.intent_conf,
    language_tag = EXCLUDED.language_tag,
    satisfaction_score = EXCLUDED.satisfaction_score,
    tags = EXCLUDED.tags,
    custom_fields = EXCLUDED.custom_fields,
    raw = EXCLUDED.raw
"""


def load(result: StageResult) -> None:
    """Parse every Zendesk envelope we hold and land the ticket tables."""
    rows: dict[int, dict[str, Any]] = {}
    envelope_notes: list[str] = []

    for relative in ZENDESK_FILES:
        payload = load_json(relative)
        if payload is None:
            result.warn(f"missing Zendesk extract: {relative}")
            continue
        results = payload.get("results") if isinstance(payload, dict) else None
        if not isinstance(results, list):
            result.warn(f"unexpected Zendesk shape in {relative}: no results[]")
            continue
        reported = payload.get("count")
        has_next = bool(payload.get("next_page"))
        envelope_notes.append(
            f"{relative}: held={len(results)} reported={reported} more_pages={has_next}"
        )
        for raw in results:
            if not isinstance(raw, dict):
                continue
            row = build_ticket_row(raw, relative)
            if row is None:
                continue
            # Later files must not overwrite an earlier parse of the same id; the
            # two extracts come from different Zendesk instances and ids do not
            # collide in practice, but keep the first parse deterministic.
            rows.setdefault(row["ticket_id"], row)

    if not rows:
        result.warn("no Zendesk tickets parsed; ticket tables left untouched")
        return

    ordered = [rows[key] for key in sorted(rows)]
    tag_rows = [
        (row["ticket_id"], tag, tag_family(tag))
        for row in ordered
        for tag in sorted({t for t in row["tags"]})
    ]

    # Backend failure signals, counted over bot-raised tickets only (the analysed
    # cohort). Aggregated here rather than in a view so the panel can show a
    # label and a pipeline stage next to each count.
    failure_counts: dict[str, int] = {}
    for row in ordered:
        if not row["is_bot_raised"]:
            continue
        for tag in {t.lower() for t in row["tags"]}:
            if tag_family(tag) == "backend":
                failure_counts[tag] = failure_counts.get(tag, 0) + 1

    with get_pool().connection() as conn:
        with conn.cursor() as cur:
            cur.executemany(_TICKET_UPSERT, ordered)
            result.add("tickets", len(ordered))

            # A ticket's tag set can shrink between extracts, so replace rather
            # than merge: delete this ticket's tags, then insert what we hold.
            cur.executemany(
                "DELETE FROM ticket_tags WHERE ticket_id = %s",
                [(row["ticket_id"],) for row in ordered],
            )
            cur.executemany(
                """
                INSERT INTO ticket_tags (ticket_id, tag, family)
                VALUES (%s, %s, %s)
                ON CONFLICT (ticket_id, tag) DO UPDATE SET family = EXCLUDED.family
                """,
                tag_rows,
            )
            result.add("ticket_tags", len(tag_rows))

            if failure_counts:
                # backend_failures has a serial PK, so upsert-by-tag is emulated.
                cur.executemany(
                    "DELETE FROM backend_failures WHERE tag = %s",
                    [(tag,) for tag in failure_counts],
                )
                failure_rows = []
                for index, (tag, count) in enumerate(
                    sorted(failure_counts.items(), key=lambda kv: (-kv[1], kv[0])), start=1
                ):
                    label, stage = BACKEND_FAILURE_META.get(
                        tag, (_failure_label(tag), _failure_stage(tag) or "")
                    )
                    failure_rows.append((tag, label, count, stage or None, index))
                cur.executemany(
                    """
                    INSERT INTO backend_failures (tag, label, ticket_count, stage, sort_order)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    failure_rows,
                )
                result.add("backend_failures", len(failure_counts))

            # Correlate to Kore.ai sessions by ticket number. Runs as a set-based
            # update so it is correct whichever order the loaders ran in.
            cur.execute(
                """
                UPDATE tickets t
                   SET correlated_session_id = c.session_id
                  FROM conversations c
                 WHERE c.ticket_id = t.ticket_id
                   AND (t.correlated_session_id IS DISTINCT FROM c.session_id)
                """
            )
            correlated = cur.rowcount if cur.rowcount and cur.rowcount > 0 else 0
        conn.commit()

    bot_raised = sum(1 for row in ordered if row["is_bot_raised"])
    named_lines = sum(1 for row in ordered if row["is_bot_raised"] and row["cruise_line"])
    result.detail = (
        f"{len(ordered)} tickets, {bot_raised} bot-raised, "
        f"{named_lines} name a cruise line, {correlated} correlated to a session"
    )
    for note in envelope_notes:
        log.info("[load_zendesk] %s", note)


def run() -> StageResult:
    with run_stage("load_zendesk", "Zendesk search pages -> tickets, ticket_tags") as result:
        load(result)
    return result
