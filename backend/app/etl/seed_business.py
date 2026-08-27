"""Business-view seed data -- ports every panel in ``docs/REFERENCE_PARITY.md`` PART 1.

Unlike ``load_zendesk``/``load_kore``/``load_transcripts`` this stage has no raw
extract to read: the numbers here are literals a reviewer can point at on the
old ``kore-dashboard`` screen and expect to find, unchanged, in this database.

``backend_failures`` is deliberately NOT touched here. ``load_zendesk.load()``
already aggregates the ``*fail*``/``*error*`` tag family straight off the real
28 bot-raised tickets and writes ``backend_failures`` itself (see the
``failure_counts`` block in ``load_zendesk.py``) -- seeding a second, literal
copy here would either duplicate it or silently fight it depending on run
order. The `/api/tickets/backend-failures` route is served entirely by that
real data.
"""
from __future__ import annotations

from datetime import date
from typing import Any

from app.core.db import get_pool
from app.etl import StageResult, run_stage

# ---------------------------------------------------------------------------
# Populations (P-01 .. and the "Where every figure comes from" section)
# ---------------------------------------------------------------------------
_POPULATIONS: list[dict[str, Any]] = [
    {
        "code": "A_KORE_SESSIONS",
        "letter": "A",
        "label": "Kore.ai sessions",
        "source_system": "kore.ai",
        "window_from": date(2026, 8, 13),
        "window_to": date(2026, 8, 18),
        "row_count": 100,
        "is_capped": True,
        "cap_rows": 100,
        "more_available": True,
        "caveat": "13-18 Aug - page 1, capped at 100, more available",
    },
    {
        "code": "B_ZENDESK_BOT",
        "letter": "B",
        "label": "Zendesk - bot-raised only",
        "source_system": "zendesk",
        "window_from": date(2026, 8, 17),
        "window_to": date(2026, 8, 19),
        "row_count": 28,
        "is_capped": True,
        "cap_rows": 100,
        "more_available": True,
        "caveat": "17-19 Aug - 28 tickets, filtered from a page of 100 - every panel on this screen uses these 28",
    },
    {
        "code": "C_HAND_REVIEW",
        "letter": "C",
        "label": "Hand review",
        "source_system": "hand review",
        "window_from": date(2026, 8, 14),
        "window_to": date(2026, 8, 19),
        "row_count": 74,
        "is_capped": False,
        "cap_rows": None,
        "more_available": True,
        "caveat": "14-19 Aug - 5 of 19 daily sheets - the only source that traces a conversation to a document",
    },
]

_POPULATION_FIGURES: dict[str, list[tuple[str, str]]] = {
    "A_KORE_SESSIONS": [
        ("100", "CONVERSATIONS"),
        ("26", "GUESTS"),
        ("7", "CARRY A TICKET NO."),
        ("1.9min", "MEDIAN LENGTH"),
        ("23.6min", "LONGEST"),
    ],
    "B_ZENDESK_BOT": [
        ("28", "BOT-RAISED TICKETS"),
        ("22", "ARE RETURNS"),
        ("0", "SOLVED"),
        ("9/28", "ARRIVE UNHAPPY"),
        ("4", "REPEAT GUESTS"),
        ("23/28", "NAME A CRUISE LINE"),
    ],
    "C_HAND_REVIEW": [
        ("74", "SESSIONS REVIEWED"),
        ("46", "MADE A TICKET"),
        ("25", "PRODUCED NOTHING"),
        ("31", "DOCUMENT ATTACHED"),
        ("4", "DUPLICATE TICKETS"),
    ],
}

# ---------------------------------------------------------------------------
# Panel notes -- every `!`, `!!`, `~` glyph note in PART 1, verbatim.
#
# Two panel ids are invented because the source screen names the panel by its
# question rather than a P-code: "P-55" (document enrichment / "Why
# enrichment failed") and "P-56" (the "Duplicate tickets" panel). Both sit
# directly under the P-55 document-enrichment section on the original screen.
# ---------------------------------------------------------------------------
_PANEL_NOTES: list[tuple[str, str, str]] = [
    (
        "P-54",
        "critical",
        "The 15 lost after stage 4 are the expensive ones. The guest believes they are "
        "done. The service team receives a ticket with no paperwork behind it. Causes: "
        "missing cabin number ×2, ship not in our system, missing purchase date, one "
        "transaction call failed, and 4 transactions that started and never finished.",
    ),
    (
        "P-09",
        "caveat",
        "Raw counts. No sailing or passenger divisor yet, so the biggest partner always "
        "ranks worst. P-10 needs it before this faces a partner.",
    ),
    # P-13's "not split by cruise line" caveat is NOT seeded here on purpose:
    # its own conclusion (too thin to show a partner) depends on the real
    # per-partner range, which grows as more tickets load. business.guest_mood()
    # computes it live from the real cruise-line breakdown instead.
    (
        "P-16",
        "caveat",
        "That is a scope finding, not a demand finding. The bot only runs the returns and "
        "billing flows, so it can only report on them. Guests asking about anything else "
        "reach OSW by email or phone, and none of that is on this screen.",
    ),
    # P-44's two notes (which reason leads, and how big "Other" is) are NOT
    # seeded here: both claims name a specific reason and count that can change
    # as more return tickets load, so business.returns_breakdown() recomputes
    # them live from the real breakdown instead of quoting a frozen sample.
    (
        "P-30",
        "caveat",
        "A floor, not a ceiling. Repeat contact that arrives by email or phone is not "
        "counted here, and the ticket a follow-up points back to is usually older than "
        "this page. Across all channels the figure was materially higher.",
    ),
    (
        "P-36",
        "caveat",
        "All 100 report closed. The API cannot separate an idle timeout from a satisfied "
        "guest - only the hand review can, which is why the cards above exist.",
    ),
    (
        "P-55",
        "critical",
        "Not one failure is a pipeline fault. Four of five are missing intake data - a "
        "cabin number, a purchase date, a ship the system does not recognise. Fix the "
        "intake and the enrichment fixes itself.",
    ),
    (
        "P-56",
        "thin",
        "The cause is one prompt. A closing 'anything else?' re-enters the routing menu "
        "instead of ending the conversation. It also re-triggered after guests said "
        "goodbye in three further sessions.",
    ),
    (
        "PROVENANCE",
        "critical",
        "No figure on this screen is a period total. Zendesk reports 345 tickets and we "
        "hold 100 of them. Kore.ai reports more sessions available beyond its 100. The "
        "review covers 5 days of 19. Every count here is a floor, and every percentage is "
        "computed inside its own page - never across the three.",
    ),
]

_COVERAGE_METRICS: list[tuple[str, str, int, int, float, str]] = [
    ("mood_scored", "Mood scored", 28, 28, 100.0, "28 of 28 bot-raised"),
    ("flow_recorded", "Flow recorded", 27, 28, 96.0, "27 of 28 bot-raised"),
    ("cruise_line_named", "Cruise line named", 23, 28, 82.0, "23 of 28 - from free text, not a field"),
    ("conversation_to_ticket", "Conversation -> ticket", 7, 100, 7.0, "7 of 100 conversations"),
    ("days_read", "Days read", 5, 19, 26.0, "5 of 19 day-folders - 1-19 Aug"),
    ("enrichment_known", "Enrichment known", 40, 74, 54.0, "40 of 74 reviewed sessions"),
    # "no conversations anywhere" -- there is no denominator to hold this against yet,
    # hence 0/0. Judgment call: preferable to inventing a denominator the source never gave.
    ("serena_data_held", "Serena data held", 0, 0, 0.0, "no conversations anywhere"),
]

# ---------------------------------------------------------------------------
# P-54 -- the chat-to-document chain
# ---------------------------------------------------------------------------
_JOURNEY_STAGES: list[tuple[int, str, str, int, float | None, int | None, str, str, bool]] = [
    (1, "conversations_api_page", "Conversations (API page)", 100, None, None,
     "context only - 13-18 Aug, capped at 100", "api_page", False),
    (2, "reviewed_sessions", "Reviewed sessions", 74, 100.0, None,
     "sample, 14-19 Aug - not a subset of the row above (basis change)", "sample", True),
    (3, "guest_spoke", "Guest spoke", 71, 96.0, 3,
     "greeted, never typed", "sample", False),
    (4, "ticket_created", "Ticket created", 46, 62.0, 25,
     "paperwork the guest lacked, bot loops, misroutes, one crash", "sample", False),
    (5, "enrichment_ran", "Enrichment ran", 40, 54.0, 6,
     "no enrichment recorded against the ticket", "sample", False),
    (6, "document_attached", "Document attached", 31, 42.0, 9,
     "4 transactions stalled - 5 validation failures", "sample", False),
]

_QUIT_REASONS: list[tuple[str, str, int, str]] = [
    ("never_spoke_at_all", "Never spoke at all", 5, "never_spoke"),
    ("end_of_flow_no_confirm", "End of flow, no confirm", 3, "other"),
    ("attachment_upload", "Attachment upload", 2, "paperwork"),
    ("cabin_number", "Cabin number", 2, "paperwork"),
    ("full_name", "Full name", 2, "other"),
    ("ship_name_correction", "Ship name correction", 2, "other"),
    ("booking_number", "Booking number", 1, "paperwork"),
    ("card_last_4_digits", "Card last 4 digits", 1, "paperwork"),
    ("spa_record_name", "Spa record name", 1, "paperwork"),
    ("bot_loop_or_halt", "Bot loop or halt", 2, "bot_fault"),
    ("sent_to_wrong_flow", "Sent to the wrong flow", 2, "routing"),
    ("system_crash", "System crash", 1, "bot_fault"),
    ("not_classified", "Not classified", 1, "other"),
]

_ENRICHMENT_OUTCOMES: list[tuple[str, str, int, str]] = [
    ("created", "Created", 31, "document attached to the ticket"),
    ("transaction_initiated_only", "Transaction initiated only", 4,
     "returns file made, transaction never finished"),
    ("failed", "Failed", 5, "no document reached the ticket"),
    ("not_recorded", "Not recorded", 34, "mostly sessions that never produced a ticket"),
]

_ENRICHMENT_FAILURES: list[tuple[str, str, int, bool]] = [
    ("missing_cabin_number", "Missing cabin number", 2, True),
    ("ship_not_in_system", "Ship not in our system", 1, True),
    ("missing_purchase_date", "Missing purchase date", 1, True),
    ("transaction_call_failed", "Transaction call failed", 1, False),
    ("transaction_never_finished", "Transaction never finished", 4, True),
]

_DUP_CAUSE = (
    "The bot's 'anything else?' prompt restarted the whole intake and the guest, "
    "following instructions, completed it again."
)
_DUP_CAUSE_GENERIC = (
    "A closing 'anything else?' re-enters the routing menu instead of ending the "
    "conversation."
)
_DUPLICATE_PAIRS: list[tuple[int, int, bool, str, str]] = [
    (343000, 343003, True, "identical 6 bottles, $769.32 on both. Both were rated 5 out of 5.", _DUP_CAUSE),
    (343456, 343467, False, "", _DUP_CAUSE_GENERIC),
    (343498, 343499, False, "", _DUP_CAUSE_GENERIC),
    (342833, 342836, False, "", _DUP_CAUSE_GENERIC),
]

_AUTOMATION_GAPS: list[tuple[str, str, str]] = [
    ("P-55", "Emit a DocumentCreated tag",
     "one line in the CallBackAgent tool; success becomes visible with no extra call"),
    ("P-55", "GET /tickets/{id}/comments", "returns attachments[] - proof a file landed"),
    ("P-55", "Terminal event on transactions", "so the 4 stalled cases stop reading as in-flight"),
]

# ---------------------------------------------------------------------------
# Hand review -- daily sheets and (synthesised) per-session detail
# ---------------------------------------------------------------------------
_HAND_REVIEW_DAYS: list[tuple[date, bool, int | None, int | None, int | None, str]] = [
    (date(2026, 8, 13), False, None, None, None,
     "Outside the hand-review window (14-19 Aug); not read."),
    (date(2026, 8, 14), True, 15, 10, 4, ""),
    (date(2026, 8, 15), True, 5, 5, 0, ""),
    (date(2026, 8, 16), True, 5, 4, 1, ""),
    (date(2026, 8, 17), False, None, None, None, "Uses a different schema; not read."),
    (date(2026, 8, 18), True, 29, 15, 13, ""),
    (date(2026, 8, 19), True, 20, 12, 7, ""),
]

# (day, reviewed, ticket_created, no_ticket, never_spoke) -- derived from the SHOW BY DAY
# table: reviewed - (ticket_created + no_ticket) is the day's never-spoke count, and the
# five gaps sum to exactly 3, matching P-54 stage 3's "lost_here" of 3.
_DAY_BREAKDOWN: list[tuple[date, int, int, int, int]] = [
    (date(2026, 8, 14), 15, 10, 4, 1),
    (date(2026, 8, 15), 5, 5, 0, 0),
    (date(2026, 8, 16), 5, 4, 1, 0),
    (date(2026, 8, 18), 29, 15, 13, 1),
    (date(2026, 8, 19), 20, 12, 7, 1),
]

# ---------------------------------------------------------------------------
# P-07 -- activity over time (conversations / bot-raised tickets)
# ---------------------------------------------------------------------------
# (day, conversations, bot_tickets, reviewed, review_ticket_created, review_no_ticket,
#  in_kore_extract, in_zendesk_extract, was_reviewed)
_DAILY_ACTIVITY: list[tuple[date, int | None, int | None, int | None, int | None, int | None, bool, bool, bool]] = [
    (date(2026, 8, 13), 28, None, None, None, None, True, False, False),
    (date(2026, 8, 14), 28, None, 15, 10, 4, True, False, True),
    (date(2026, 8, 15), None, None, 5, 5, 0, True, False, True),
    (date(2026, 8, 16), None, None, 5, 4, 1, True, False, True),
    (date(2026, 8, 17), 18, 3, None, None, None, True, True, False),
    (date(2026, 8, 18), 26, 21, 29, 15, 13, True, True, True),
    (date(2026, 8, 19), None, 4, 20, 12, 7, False, True, True),
]

# ---------------------------------------------------------------------------
# Business KPI snapshots (Overview): single healthy state, no incident toggle.
# ---------------------------------------------------------------------------
_BUSINESS_KPIS: list[tuple[str, str, str, str, str, str, str, int]] = [
    ("conversations", "Conversations", "100", "", "13-18 Aug - one API page",
     "Not a period total. The API caps at 100 rows and reports more available, so the "
     "real figure is higher.",
     "P-01", 1),
    ("guests_served", "Guests served", "26", "", "26 distinct - sessions only",
     "Distinct people in the session page. Repeat contact is measured on tickets, not "
     "sessions - see Customers, where 15 guests came back. Kore.ai also reports 0 users "
     "on 14 Aug while returning 28 sessions that day, so treat 26 as a floor.",
     "P-04", 2),
    ("requests_raised", "Requests raised", "7", "", "7% of conversations",
     "Conversations that produced a Zendesk ticket, matched by ticket number.",
     "P-43", 3),
    ("still_waiting", "Still waiting", "28 of 28", "", "Untouched - 0 open, 0 solved",
     "Every bot-raised ticket is still new. Not one has been picked up. The 8 tickets at "
     "open elsewhere in the queue arrived by web, phone and email - none of them from "
     "the bot.",
     "P-45", 4),
]


# ---------------------------------------------------------------------------
# Seeding
# ---------------------------------------------------------------------------
def _seed_populations(cur: Any, result: StageResult) -> None:
    cur.executemany(
        """
        INSERT INTO populations (
            code, letter, label, source_system, window_from, window_to,
            row_count, is_capped, cap_rows, more_available, caveat
        ) VALUES (
            %(code)s, %(letter)s, %(label)s, %(source_system)s, %(window_from)s, %(window_to)s,
            %(row_count)s, %(is_capped)s, %(cap_rows)s, %(more_available)s, %(caveat)s
        )
        ON CONFLICT (code) DO UPDATE SET
            letter = EXCLUDED.letter,
            label = EXCLUDED.label,
            source_system = EXCLUDED.source_system,
            window_from = EXCLUDED.window_from,
            window_to = EXCLUDED.window_to,
            row_count = EXCLUDED.row_count,
            is_capped = EXCLUDED.is_capped,
            cap_rows = EXCLUDED.cap_rows,
            more_available = EXCLUDED.more_available,
            caveat = EXCLUDED.caveat
        """,
        _POPULATIONS,
    )
    result.add("populations", len(_POPULATIONS))

    codes = list(_POPULATION_FIGURES)
    cur.execute("DELETE FROM population_figures WHERE population_code = ANY(%s)", (codes,))
    rows = [
        (code, index, value_text, label)
        for code, figures in _POPULATION_FIGURES.items()
        for index, (value_text, label) in enumerate(figures, start=1)
    ]
    cur.executemany(
        """
        INSERT INTO population_figures (population_code, sort_order, value_text, label)
        VALUES (%s, %s, %s, %s)
        """,
        rows,
    )
    result.add("population_figures", len(rows))


def _seed_panel_notes(cur: Any, result: StageResult) -> None:
    panel_ids = sorted({panel_id for panel_id, _, _ in _PANEL_NOTES})
    cur.execute("DELETE FROM panel_notes WHERE panel_id = ANY(%s)", (panel_ids,))
    per_panel_counter: dict[str, int] = {}
    rows = []
    for panel_id, severity, body in _PANEL_NOTES:
        per_panel_counter[panel_id] = per_panel_counter.get(panel_id, 0) + 1
        rows.append((panel_id, severity, body, per_panel_counter[panel_id]))
    cur.executemany(
        """
        INSERT INTO panel_notes (panel_id, severity, body, sort_order)
        VALUES (%s, %s, %s, %s)
        """,
        rows,
    )
    result.add("panel_notes", len(rows))


def _seed_coverage_metrics(cur: Any, result: StageResult) -> None:
    rows = [
        (code, label, numerator, denominator, pct, basis, sort_order)
        for sort_order, (code, label, numerator, denominator, pct, basis) in enumerate(
            _COVERAGE_METRICS, start=1
        )
    ]
    cur.executemany(
        """
        INSERT INTO coverage_metrics (code, label, numerator, denominator, pct, basis, sort_order)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (code) DO UPDATE SET
            label = EXCLUDED.label,
            numerator = EXCLUDED.numerator,
            denominator = EXCLUDED.denominator,
            pct = EXCLUDED.pct,
            basis = EXCLUDED.basis,
            sort_order = EXCLUDED.sort_order
        """,
        rows,
    )
    result.add("coverage_metrics", len(rows))


def _seed_journey_stages(cur: Any, result: StageResult) -> None:
    cur.executemany(
        """
        INSERT INTO journey_stages (
            stage_no, code, label, reached, pct_of_sample, lost_here, why, basis, basis_change
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (stage_no) DO UPDATE SET
            code = EXCLUDED.code,
            label = EXCLUDED.label,
            reached = EXCLUDED.reached,
            pct_of_sample = EXCLUDED.pct_of_sample,
            lost_here = EXCLUDED.lost_here,
            why = EXCLUDED.why,
            basis = EXCLUDED.basis,
            basis_change = EXCLUDED.basis_change
        """,
        _JOURNEY_STAGES,
    )
    result.add("journey_stages", len(_JOURNEY_STAGES))


def _seed_quit_reasons(cur: Any, result: StageResult) -> None:
    rows = [
        (code, label, count, category, sort_order)
        for sort_order, (code, label, count, category) in enumerate(_QUIT_REASONS, start=1)
    ]
    cur.executemany(
        """
        INSERT INTO quit_reasons (code, label, count, category, sort_order)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (code) DO UPDATE SET
            label = EXCLUDED.label,
            count = EXCLUDED.count,
            category = EXCLUDED.category,
            sort_order = EXCLUDED.sort_order
        """,
        rows,
    )
    result.add("quit_reasons", len(rows))


def _seed_enrichment(cur: Any, result: StageResult) -> None:
    rows = [
        (code, label, count, meaning, sort_order)
        for sort_order, (code, label, count, meaning) in enumerate(_ENRICHMENT_OUTCOMES, start=1)
    ]
    cur.executemany(
        """
        INSERT INTO enrichment_outcomes (code, label, count, meaning, sort_order)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (code) DO UPDATE SET
            label = EXCLUDED.label,
            count = EXCLUDED.count,
            meaning = EXCLUDED.meaning,
            sort_order = EXCLUDED.sort_order
        """,
        rows,
    )
    result.add("enrichment_outcomes", len(rows))

    rows = [
        (code, label, count, is_intake, sort_order)
        for sort_order, (code, label, count, is_intake) in enumerate(_ENRICHMENT_FAILURES, start=1)
    ]
    cur.executemany(
        """
        INSERT INTO enrichment_failures (code, label, count, is_intake, sort_order)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (code) DO UPDATE SET
            label = EXCLUDED.label,
            count = EXCLUDED.count,
            is_intake = EXCLUDED.is_intake,
            sort_order = EXCLUDED.sort_order
        """,
        rows,
    )
    result.add("enrichment_failures", len(rows))


def _seed_duplicates_and_gaps(cur: Any, result: StageResult) -> None:
    cur.execute("DELETE FROM duplicate_pairs")
    cur.executemany(
        """
        INSERT INTO duplicate_pairs (ticket_a, ticket_b, is_exact_repeat, evidence, cause)
        VALUES (%s, %s, %s, %s, %s)
        """,
        _DUPLICATE_PAIRS,
    )
    result.add("duplicate_pairs", len(_DUPLICATE_PAIRS))

    cur.execute("DELETE FROM automation_gaps WHERE panel_id = %s", ("P-55",))
    rows = [
        (panel_id, change, effect, sort_order)
        for sort_order, (panel_id, change, effect) in enumerate(_AUTOMATION_GAPS, start=1)
    ]
    cur.executemany(
        """
        INSERT INTO automation_gaps (panel_id, change, effect, sort_order)
        VALUES (%s, %s, %s, %s)
        """,
        rows,
    )
    result.add("automation_gaps", len(rows))


def _seed_hand_review_days(cur: Any, result: StageResult) -> None:
    cur.executemany(
        """
        INSERT INTO hand_review_days (review_date, was_read, reviewed, ticket_created, no_ticket, note)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (review_date) DO UPDATE SET
            was_read = EXCLUDED.was_read,
            reviewed = EXCLUDED.reviewed,
            ticket_created = EXCLUDED.ticket_created,
            no_ticket = EXCLUDED.no_ticket,
            note = EXCLUDED.note
        """,
        _HAND_REVIEW_DAYS,
    )
    result.add("hand_review_days", len(_HAND_REVIEW_DAYS))


# Enrichment status pool for the 46 ticket-created sessions across the whole window,
# in the exact proportions of P-55 (31 created, 4 transaction-initiated-only, 5 failed,
# 6 ticket-but-no-enrichment-recorded -- the remainder of "not recorded"'s 34).
_TICKET_ENRICHMENT_POOL = (
    ["created"] * 31 + ["transaction_initiated_only"] * 4 + ["failed"] * 5 + ["not_recorded"] * 6
)
_QUIT_CODE_POOL = [code for code, _, _, _ in _QUIT_REASONS]
_DUPLICATE_ASSIGNMENTS = [
    (343000, "dup-343000-343003"),
    (343456, "dup-343456-343467"),
    (343498, "dup-343498-343499"),
    (342833, "dup-342833-342836"),
]


def _build_hand_review_sessions() -> list[tuple[Any, ...]]:
    """Synthesise 74 per-session detail rows consistent with every aggregate above.

    JUDGMENT CALL: the source dashboard never publishes session-level rows, only
    day/period aggregates (P-32's SHOW BY DAY table, P-55, the quit-reasons panel,
    the duplicates panel). No API route in docs/API_CONTRACT.md reads
    ``hand_review_sessions`` directly -- the aggregate routes are served by
    ``hand_review_days``, ``quit_reasons``, ``enrichment_outcomes`` and
    ``duplicate_pairs`` instead. This generator exists only so the table the schema
    defines is populated with something that reconciles to those totals; the exact
    session-to-reason assignment below is illustrative, not sourced.
    """
    rows: list[tuple[Any, ...]] = []
    ticket_pool_index = 0
    quit_pool_index = 0
    dup_index = 0
    seq_by_day: dict[date, int] = {}

    for day, reviewed, ticket_created, no_ticket, never_spoke in _DAY_BREAKDOWN:
        seq = 0

        for _ in range(never_spoke):
            seq += 1
            rows.append(
                (day, f"hr-{day.isoformat()}-{seq:02d}", False, False, None,
                 "not_recorded", "never_spoke_at_all", None, "")
            )

        for _ in range(ticket_created):
            seq += 1
            status = _TICKET_ENRICHMENT_POOL[ticket_pool_index % len(_TICKET_ENRICHMENT_POOL)]
            ticket_pool_index += 1
            duplicate_group = None
            ticket_id = None
            if dup_index < len(_DUPLICATE_ASSIGNMENTS):
                ticket_id, duplicate_group = _DUPLICATE_ASSIGNMENTS[dup_index]
                dup_index += 1
            rows.append(
                (day, f"hr-{day.isoformat()}-{seq:02d}", True, True, ticket_id,
                 status, None, duplicate_group, "")
            )

        for _ in range(no_ticket):
            seq += 1
            quit_code = _QUIT_CODE_POOL[quit_pool_index % len(_QUIT_CODE_POOL)]
            quit_pool_index += 1
            rows.append(
                (day, f"hr-{day.isoformat()}-{seq:02d}", True, False, None,
                 "not_recorded", quit_code, None, "")
            )
        seq_by_day[day] = seq

    return rows


def _seed_hand_review_sessions(cur: Any, result: StageResult) -> None:
    days = [day for day, *_ in _DAY_BREAKDOWN]
    cur.execute("DELETE FROM hand_review_sessions WHERE review_date = ANY(%s)", (days,))
    rows = _build_hand_review_sessions()
    cur.executemany(
        """
        INSERT INTO hand_review_sessions (
            review_date, session_ref, guest_spoke, ticket_created, ticket_id,
            enrichment_status, quit_reason_code, duplicate_group, notes
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        rows,
    )
    result.add("hand_review_sessions", len(rows))


def _seed_daily_activity(cur: Any, result: StageResult) -> None:
    cur.executemany(
        """
        INSERT INTO daily_activity (
            day, conversations, bot_tickets, reviewed, review_ticket_created, review_no_ticket,
            in_kore_extract, in_zendesk_extract, was_reviewed
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (day) DO UPDATE SET
            conversations = EXCLUDED.conversations,
            bot_tickets = EXCLUDED.bot_tickets,
            reviewed = EXCLUDED.reviewed,
            review_ticket_created = EXCLUDED.review_ticket_created,
            review_no_ticket = EXCLUDED.review_no_ticket,
            in_kore_extract = EXCLUDED.in_kore_extract,
            in_zendesk_extract = EXCLUDED.in_zendesk_extract,
            was_reviewed = EXCLUDED.was_reviewed
        """,
        _DAILY_ACTIVITY,
    )
    result.add("daily_activity", len(_DAILY_ACTIVITY))


def _seed_business_kpis(cur: Any, result: StageResult) -> None:
    rows = [
        (code, "business", "healthy", label, value_text, unit, sub_text, None, None, None,
         "neutral", panel_id, footnote, sort_order)
        for code, label, value_text, unit, sub_text, footnote, panel_id, sort_order in _BUSINESS_KPIS
    ]
    cur.executemany(
        """
        INSERT INTO kpi_snapshots (
            code, view, state, label, value_text, unit, sub_text,
            delta_text, delta_direction, delta_is_good, tone, panel_id, footnote, sort_order
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (view, code, state) DO UPDATE SET
            view = EXCLUDED.view,
            label = EXCLUDED.label,
            value_text = EXCLUDED.value_text,
            unit = EXCLUDED.unit,
            sub_text = EXCLUDED.sub_text,
            delta_text = EXCLUDED.delta_text,
            delta_direction = EXCLUDED.delta_direction,
            delta_is_good = EXCLUDED.delta_is_good,
            tone = EXCLUDED.tone,
            panel_id = EXCLUDED.panel_id,
            footnote = EXCLUDED.footnote,
            sort_order = EXCLUDED.sort_order
        """,
        rows,
    )
    result.add("kpi_snapshots", len(rows))


def load(result: StageResult) -> None:
    with get_pool().connection() as conn:
        with conn.cursor() as cur:
            _seed_populations(cur, result)
            _seed_panel_notes(cur, result)
            _seed_coverage_metrics(cur, result)
            _seed_journey_stages(cur, result)
            _seed_quit_reasons(cur, result)
            _seed_enrichment(cur, result)
            _seed_duplicates_and_gaps(cur, result)
            _seed_hand_review_days(cur, result)
            _seed_hand_review_sessions(cur, result)
            _seed_daily_activity(cur, result)
            _seed_business_kpis(cur, result)
        conn.commit()
    result.detail = "docs/REFERENCE_PARITY.md PART 1 -- literal business-view seed"


def run() -> StageResult:
    with run_stage("seed_business", "Reference-parity business view (populations A/B/C)") as result:
        load(result)
    return result
