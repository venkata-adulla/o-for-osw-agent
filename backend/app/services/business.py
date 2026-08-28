"""Business-view query functions -- one plain function per panel.

Every figure the business half of O for OSW shows is produced here and nowhere
else. The routers are thin wrappers that add the provenance envelope, and the
LLM tools behind ``/api/ask`` import these same functions, so a chat answer and
a screen figure are physically incapable of disagreeing.

Three conventions are load-bearing:

* **NULL is not zero.** ``daily_activity`` (and any other source that records a
  calendar day absent from an extract) stores NULL on purpose. Those NULLs are
  passed straight through as JSON ``null`` so the UI can render "--" plus the
  reason instead of a fake zero.
* **Timestamps are filtered half-open.** ``>= from AND < exclusive_upper(to)``,
  never ``BETWEEN`` -- a ``BETWEEN`` on a ``timestamptz`` silently drops
  same-day rows, which has already cost this project once.
* **Dates are opt-in.** Every figure on the business screens is a *page*, not a
  period total (see docs/REFERENCE_PARITY.md). When the caller supplies no
  dates, no date predicate is applied at all and the panel reports the whole
  extract it holds -- which is what the reference dashboard's basis lines
  describe. A supplied ``date_from``/``date_to`` narrows it, via
  ``validate_date_range``.

Identifiers are never formatted into SQL from user input: the handful of places
that need a variable column or a comparison value guard it with an explicit
allowlist and raise ``ValueError`` otherwise.
"""
from __future__ import annotations

import os
import re
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Final, Iterable, Sequence

from app.core.db import (
    exclusive_upper,
    fetch_all,
    fetch_one,
    fetch_value,
    validate_date_range,
)
from app.core.envelope import POPULATION_BASIS

# --------------------------------------------------------------------------- #
# Allowlists. Anything that could reach SQL as more than a bound parameter has
# to appear in one of these.
# --------------------------------------------------------------------------- #

VIEWS: Final[frozenset[str]] = frozenset({"business", "technical"})
STATES: Final[frozenset[str]] = frozenset({"healthy", "incident"})
JOURNEY_SOURCES: Final[frozenset[str]] = frozenset({"telemetry", "review"})
CONTAINMENT_TYPES: Final[frozenset[str]] = frozenset(
    {"self_service", "drop_off", "agent_transfer"}
)

# Columns a caller-supplied date window may be applied to.
_RANGE_COLUMNS: Final[frozenset[str]] = frozenset(
    {
        "created_at",
        "started_at",
        "observed_at",
        "occurred_at",
        "finished_at",
        "day",
        "review_date",
    }
)

MAX_PAGE_LIMIT: Final[int] = 200
DEFAULT_PAGE_LIMIT: Final[int] = 50

# The flows the One Spa World intake form offers. Held here as a *catalogue*,
# not as a figure: P-16's "everything else produced nothing at all" readout is
# only honest if we know what the form could have produced. Counts always come
# from the database.
FORM_FLOWS: Final[tuple[str, ...]] = (
    "Return inquiry",
    "Spa product",
    "Pricing issue",
    "HD order",
    "Medi-Spa",
    "Acupuncture",
    "Fitness",
    "Wellness",
    "Thermal Suite",
    "Pre-booking",
)

_SENTIMENT_TONE: Final[dict[str, str]] = {
    "positive": "good",
    "neutral": "neutral",
    "negative": "warning",
    "very negative": "critical",
}

_STATUS_TONE: Final[dict[str, str]] = {
    # On this screen "new" is the bad outcome: a bot-raised ticket nobody has
    # touched. See P-45.
    "new": "warning",
    "open": "neutral",
    "pending": "neutral",
    "hold": "warning",
    "solved": "good",
    "closed": "good",
}

_UNHAPPY_SENTIMENTS: Final[tuple[str, ...]] = ("negative", "very negative")

# Which metric instruments stand behind each telemetry funnel stage. Matched
# against the stage code/title by keyword so the seed can name stages freely.
_STAGE_INSTRUMENTS: Final[tuple[tuple[str, tuple[str, ...]], ...]] = (
    ("document", ("osw.document.attached",)),
    ("enrichment", ("osw.enrichment.operation", "osw.enrichment.duration")),
    ("ticket", ("osw.ticket.created",)),
    ("conversation", ("osw.conversation.started", "osw.conversation.duration")),
)


# --------------------------------------------------------------------------- #
# Small coercion helpers. psycopg hands back Decimal for numeric columns; the
# UI wants plain JSON numbers, and NULL has to survive the trip as None.
# --------------------------------------------------------------------------- #


def _i(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, Decimal, float)):
        return int(value)
    try:
        return int(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def _f(value: Any, digits: int = 1) -> float | None:
    if value is None:
        return None
    try:
        return round(float(value), digits)
    except (TypeError, ValueError):
        return None


def _pct(numerator: Any, denominator: Any, digits: int = 1) -> float | None:
    """Percentage, or None when either side is missing or the divisor is zero.

    Never returns 0.0 for "we do not know" -- that is the whole point.
    """
    num, den = _i(numerator), _i(denominator)
    if num is None or den is None or den == 0:
        return None
    return round(num * 100.0 / den, digits)


_LEADING_INT = re.compile(r"^\s*(\d[\d,]*)\b")


def _leading_int(text: str | None) -> int | None:
    """Parse a count off the *front* of a seeded label ("1,284 conversations").

    Deliberately anchored: a number buried inside prose is far more likely to be
    a percentage or a version than the figure we want, so it is ignored.
    """
    if not text:
        return None
    match = _LEADING_INT.match(text)
    if not match:
        return None
    return _i(match.group(1))


def _range_clause(
    column: str,
    date_from: date | None,
    date_to: date | None,
    params: list[Any],
) -> str:
    """Half-open date predicate, appended to ``params`` in SQL order.

    Returns "" when the caller supplied no dates -- see the module docstring on
    why the default is the whole extract rather than a rolling window.
    """
    if column not in _RANGE_COLUMNS:  # pragma: no cover - programmer error
        raise ValueError(f"unsupported date column: {column!r}")
    if date_from is None and date_to is None:
        return ""
    lower, upper = validate_date_range(date_from, date_to)
    params.extend([lower, exclusive_upper(upper)])
    return f" AND {column} >= %s AND {column} < %s"


def _bot_clause(column: str, bot_id: str | None, params: list[Any]) -> str:
    if not bot_id:
        return ""
    if column not in {"bot_id"}:  # pragma: no cover - programmer error
        raise ValueError(f"unsupported bot column: {column!r}")
    params.append(bot_id)
    return f" AND {column} = %s"


def _require(value: str | None, allowed: Iterable[str], name: str, default: str) -> str:
    """Validate a caller-supplied enum against an allowlist."""
    chosen = (value or default).strip().lower()
    allowed_set = set(allowed)
    if chosen not in allowed_set:
        raise ValueError(f"{name} must be one of {sorted(allowed_set)}")
    return chosen


def _clamp_limit(limit: int | None, default: int = DEFAULT_PAGE_LIMIT) -> int:
    if limit is None:
        return default
    if limit < 1:
        raise ValueError("limit must be at least 1")
    return min(limit, MAX_PAGE_LIMIT)


def _clamp_offset(offset: int | None) -> int:
    if offset is None:
        return 0
    if offset < 0:
        raise ValueError("offset must be zero or greater")
    return offset


def _fmt_day(value: date | None) -> str:
    return "" if value is None else f"{value.day} {value:%b}"


def _live_population_stats(letter: str) -> dict[str, Any] | None:
    """Real counts for a population, read from the table the ETL actually fills.

    Populations A and B are re-derived from live data on every call: the ETL can
    load a broader real extract than the reference dashboard's frozen sample (our
    Zendesk pull holds 123 tickets, 51 bot-raised, against the reference's 28), so
    a basis line built from the *seed* would describe a different number than the
    figure sitting next to it on screen -- which is worse than no caveat at all.
    Population C has no live source (hand review is a manual process this system
    does not re-run), so it is deliberately excluded and always reads the seed.
    """
    if letter == "A":
        row = fetch_one(
            "SELECT COUNT(*) AS n, MIN(started_at) AS lo, MAX(started_at) AS hi FROM conversations"
        )
        label = "Kore.ai conversations"
    elif letter == "B":
        row = fetch_one(
            "SELECT COUNT(*) AS n, MIN(created_at) AS lo, MAX(created_at) AS hi "
            "FROM tickets WHERE is_bot_raised"
        )
        label = "Zendesk bot-raised tickets"
    else:
        return None
    count = _i(row.get("n")) if row else None
    if not count:
        return None
    return {"count": count, "label": label, "lo": row.get("lo"), "hi": row.get("hi")}


def _population_basis(letter: str, fallback: str | None = None) -> str:
    """A human basis line for a population letter.

    A and B are computed live (see ``_live_population_stats``); C reads the
    seeded reference row, since the hand-review population has no live source.
    Falls back to the static string in ``envelope.POPULATION_BASIS`` when
    neither live data nor a seed row exists yet.
    """
    live = _live_population_stats(letter)
    if live:
        parts = [f"{live['count']} {live['label']}"]
        window = " to ".join(
            p
            for p in (
                _fmt_day(live["lo"].date() if isinstance(live["lo"], datetime) else live["lo"]),
                _fmt_day(live["hi"].date() if isinstance(live["hi"], datetime) else live["hi"]),
            )
            if p
        )
        if window:
            parts.append(window)
        return ", ".join(parts)

    row = fetch_one(
        """
        SELECT label, row_count, window_from, window_to
        FROM populations
        WHERE letter = %s
        ORDER BY code
        LIMIT 1
        """,
        (letter,),
    )
    if not row:
        return fallback or POPULATION_BASIS.get(letter, "")
    parts: list[str] = []
    count = _i(row.get("row_count"))
    label = (row.get("label") or "").strip()
    parts.append(f"{count} {label}".strip() if count is not None else label)
    window = " to ".join(
        p for p in (_fmt_day(row.get("window_from")), _fmt_day(row.get("window_to"))) if p
    )
    if window:
        parts.append(window)
    basis = ", ".join(p for p in parts if p)
    return basis or (fallback or POPULATION_BASIS.get(letter, ""))


# =========================================================================== #
# System -- /api/meta
# =========================================================================== #


def list_bots() -> dict[str, Any]:
    """Every bot known to the platform, instrumented or not.

    Population: the bot registry itself. Serena appears with ``data_held``
    false -- that absence is a finding, so the row is returned rather than
    filtered out.
    """
    rows = fetch_all(
        """
        SELECT bot_id, bot_name, environment, instrumented, data_held, note
        FROM bots
        ORDER BY instrumented DESC, bot_name, bot_id
        """
    )
    return {
        "items": rows,
        "basis": "Bot registry -- Marina is instrumented first; Serena holds no data yet",
    }


def _fmt_minutes(seconds: Any) -> str:
    value = _i(seconds)
    if value is None:
        return "—"
    return f"{value / 60:.1f}min"


def _live_population_a() -> dict[str, Any] | None:
    """Population A, recomputed from the real ``conversations`` table.

    Mirrors ``_live_population_stats`` but also carries the five headline
    figures this page shows -- those are frozen-seed literals otherwise, and
    would go on describing the reference dashboard's 100-session sample long
    after the real ETL holds more.
    """
    row = fetch_one(
        """
        SELECT COUNT(*)                                                   AS n,
               COUNT(DISTINCT channel_user_id)                            AS guests,
               COUNT(*) FILTER (WHERE ticket_id IS NOT NULL)               AS carrying,
               percentile_cont(0.5) WITHIN GROUP (ORDER BY duration_seconds) AS median_s,
               MAX(duration_seconds)                                       AS longest_s,
               MIN(started_at)                                             AS lo,
               MAX(started_at)                                             AS hi
        FROM conversations
        """
    )
    total = _i(row.get("n")) if row else None
    if not row or not total:
        return None
    return {
        "row_count": total,
        "window_from": row["lo"].date() if isinstance(row["lo"], datetime) else row["lo"],
        "window_to": row["hi"].date() if isinstance(row["hi"], datetime) else row["hi"],
        "figures": [
            {"value_text": str(total), "label": "CONVERSATIONS"},
            {"value_text": str(_i(row.get("guests")) or 0), "label": "GUESTS"},
            {"value_text": str(_i(row.get("carrying")) or 0), "label": "CARRY A TICKET NO."},
            {"value_text": _fmt_minutes(row.get("median_s")), "label": "MEDIAN LENGTH"},
            {"value_text": _fmt_minutes(row.get("longest_s")), "label": "LONGEST"},
        ],
        "caveat": (
            f"Real ETL pull, {total} conversations held so far -- Kore.ai's own "
            "session API still reports more available beyond any one page"
        ),
    }


def _live_population_b() -> dict[str, Any] | None:
    """Population B, recomputed from the real bot-raised ``tickets`` rows."""
    row = fetch_one(
        """
        SELECT COUNT(*)                                                        AS n,
               COUNT(*) FILTER (WHERE inquiry_type ILIKE %s)                    AS returns,
               COUNT(*) FILTER (WHERE lower(coalesce(status,'')) IN
                                ('solved','closed'))                            AS solved,
               COUNT(*) FILTER (WHERE lower(coalesce(sentiment,'')) = ANY(%s))  AS unhappy,
               COUNT(*) FILTER (WHERE nullif(cruise_line, '') IS NOT NULL)      AS named_line,
               MIN(created_at)                                                 AS lo,
               MAX(created_at)                                                 AS hi
        FROM tickets
        WHERE is_bot_raised
        """,
        ("%return%", list(_UNHAPPY_SENTIMENTS)),
    )
    total = _i(row.get("n")) if row else None
    if not row or not total:
        return None
    repeat_row = fetch_one(
        """
        WITH per_guest AS (
            SELECT requester_id, COUNT(*) AS tickets, bool_or(via_source_rel = 'follow_up') AS chased
            FROM tickets
            WHERE is_bot_raised AND requester_id IS NOT NULL
            GROUP BY requester_id
        )
        SELECT COUNT(*) FILTER (WHERE tickets > 1 OR chased) AS repeats
        FROM per_guest
        """
    )
    repeats = _i((repeat_row or {}).get("repeats")) or 0
    return {
        "row_count": total,
        "window_from": row["lo"].date() if isinstance(row["lo"], datetime) else row["lo"],
        "window_to": row["hi"].date() if isinstance(row["hi"], datetime) else row["hi"],
        "figures": [
            {"value_text": str(total), "label": "BOT-RAISED TICKETS"},
            {"value_text": str(_i(row.get("returns")) or 0), "label": "ARE RETURNS"},
            {"value_text": str(_i(row.get("solved")) or 0), "label": "SOLVED"},
            {"value_text": f"{_i(row.get('unhappy')) or 0}/{total}", "label": "ARRIVE UNHAPPY"},
            {"value_text": str(repeats), "label": "REPEAT GUESTS"},
            {"value_text": f"{_i(row.get('named_line')) or 0}/{total}", "label": "NAME A CRUISE LINE"},
        ],
        "caveat": (
            f"Real ETL pull, {total} bot-raised tickets held so far -- every "
            "figure on this page is computed from these, live"
        ),
    }


def list_populations() -> dict[str, Any]:
    """The three extracts every business figure is drawn from, plus their
    headline figures.

    Population: all (A, B, C and T described side by side). A and B are
    recomputed live (``_live_population_a`` / ``_live_population_b``): this
    page's whole job is to say what backs every other figure, so it is the
    last place that claim should go stale. C has no live source -- hand
    review is a manual process this system does not re-run -- so it keeps
    reading the seeded reference row, same as everywhere else C appears.
    """
    rows = fetch_all(
        """
        SELECT code, letter, label, source_system, window_from, window_to,
               row_count, is_capped, cap_rows, more_available, caveat
        FROM populations
        ORDER BY letter, code
        """
    )
    figures = fetch_all(
        """
        SELECT population_code, value_text, label
        FROM population_figures
        ORDER BY population_code, sort_order, id
        """
    )
    by_code: dict[str, list[dict[str, Any]]] = {}
    for figure in figures:
        by_code.setdefault(figure["population_code"], []).append(
            {"value_text": figure["value_text"], "label": figure["label"]}
        )

    live_by_letter = {"A": _live_population_a(), "B": _live_population_b()}

    items = []
    for row in rows:
        live = live_by_letter.get(row["letter"])
        items.append(
            {
                "code": row["code"],
                "letter": row["letter"],
                "label": row["label"],
                "source_system": row["source_system"],
                "window_from": (live or row)["window_from"],
                "window_to": (live or row)["window_to"],
                "row_count": (live or {}).get("row_count", _i(row["row_count"])),
                "is_capped": row["is_capped"] if not live else False,
                "cap_rows": _i(row["cap_rows"]),
                "more_available": row["more_available"],
                "caveat": (live or row)["caveat"],
                "figures": (live or {}).get("figures") or by_code.get(row["code"], []),
                "is_live": live is not None,
            }
        )
    return {
        "items": items,
        "basis": (
            "Three separate extracts: A Kore.ai sessions, B Zendesk bot-raised "
            "tickets, C Kore.ai extended session detail. A and B recompute live "
            "on every request; C reads a fixed reference window"
        ),
    }


def coverage() -> dict[str, Any]:
    """The data-coverage strip: what fraction of records actually carry each
    field.

    Population: B (bot-raised tickets) except where a row's own basis says
    otherwise. Four of the seven rows have a live source and are recomputed
    from it (mood scored, flow recorded, cruise line named, conversation ->
    ticket); the other three describe the hand-reviewed population, which has
    none, so they keep reading the seeded reference row.
    """
    rows = fetch_all(
        """
        SELECT code, label, numerator, denominator, pct, basis
        FROM coverage_metrics
        ORDER BY sort_order, code
        """
    )

    ticket_row = fetch_one(
        """
        SELECT COUNT(*)                                                   AS total,
               COUNT(*) FILTER (WHERE nullif(sentiment, '') IS NOT NULL)   AS scored,
               COUNT(*) FILTER (WHERE nullif(inquiry_type, '') IS NOT NULL) AS flowed,
               COUNT(*) FILTER (WHERE nullif(cruise_line, '') IS NOT NULL) AS lined
        FROM tickets
        WHERE is_bot_raised
        """
    )
    conv_row = fetch_one(
        "SELECT COUNT(*) AS total, COUNT(*) FILTER (WHERE ticket_id IS NOT NULL) AS carrying "
        "FROM conversations"
    )
    ticket_total = _i((ticket_row or {}).get("total")) or 0
    conv_total = _i((conv_row or {}).get("total")) or 0
    live_by_code = (
        {
            "mood_scored": (_i(ticket_row.get("scored")) or 0, ticket_total),
            "flow_recorded": (_i(ticket_row.get("flowed")) or 0, ticket_total),
            "cruise_line_named": (_i(ticket_row.get("lined")) or 0, ticket_total),
            "conversation_to_ticket": (_i((conv_row or {}).get("carrying")) or 0, conv_total),
        }
        if ticket_total
        else {}
    )

    items = []
    for row in rows:
        live = live_by_code.get(row["code"])
        numerator = live[0] if live else _i(row["numerator"])
        denominator = live[1] if live else _i(row["denominator"])
        items.append(
            {
                "code": row["code"],
                "label": row["label"],
                "numerator": numerator,
                "denominator": denominator,
                "pct": _pct(numerator, denominator),
                "basis": row["basis"] if not live else "of bot-raised tickets held, live",
            }
        )
    return {
        "items": items,
        "basis": (
            f"Of the {ticket_total} bot-raised tickets held, live, except where a "
            "row says otherwise"
        ),
    }


def _cadence_minutes() -> int:
    """Minutes between ETL runs, read off the PIPELINE_CRON minute field.

    Simplification, documented on purpose: only the ``*/N`` form is
    interpreted. Anything else (named minutes, ranges, lists) falls back to 10,
    which is the project default cadence. That is enough for a "next run"
    hint -- the scheduler, not this API, owns the real schedule.
    """
    cron = (os.environ.get("PIPELINE_CRON") or "*/10 * * * *").strip()
    minute_field = cron.split()[0] if cron else "*/10"
    if minute_field.startswith("*/"):
        parsed = _i(minute_field[2:])
        if parsed is not None and 1 <= parsed <= 1440:
            return parsed
    return 10


def freshness() -> dict[str, Any]:
    """Latest ETL run per source, plus when the next one is due.

    ``next_run_at`` is the last successful finish plus the PIPELINE_CRON
    cadence (default +10 minutes). It is a hint, not a promise: this API does
    not run the scheduler, so a paused pipeline will show a next-run time in
    the past rather than pretending to know better.
    """
    rows = fetch_all(
        """
        SELECT DISTINCT ON (source)
               source, status, rows_loaded, started_at, finished_at,
               detail, error_message
        FROM etl_runs
        ORDER BY source, started_at DESC, id DESC
        """
    )
    sources = [
        {
            "source": row["source"],
            "status": row["status"],
            "rows_loaded": _i(row["rows_loaded"]),
            "finished_at": row["finished_at"],
            "started_at": row["started_at"],
            "detail": row["detail"],
            "error_message": row["error_message"],
        }
        for row in rows
    ]
    sources.sort(key=lambda item: item["source"] or "")

    marker = fetch_one(
        """
        SELECT MAX(finished_at) FILTER (WHERE status = 'success') AS last_success,
               MAX(GREATEST(finished_at, started_at))             AS last_activity
        FROM etl_runs
        """
    ) or {}
    last_success: datetime | None = marker.get("last_success")
    updated_at: datetime | None = last_success or marker.get("last_activity")
    next_run_at = (
        last_success + timedelta(minutes=_cadence_minutes()) if last_success else None
    )
    return {
        "updated_at": updated_at,
        "next_run_at": next_run_at,
        "cadence_minutes": _cadence_minutes(),
        "sources": sources,
        "basis": (
            "etl_runs -- the latest run recorded for each source · next run is "
            f"the last success plus {_cadence_minutes()} minutes"
        ),
    }


# =========================================================================== #
# Command centre -- /api/overview
# =========================================================================== #


def _kpi_tile(
    code: str,
    label: str,
    value_text: str,
    unit: str,
    sub_text: str,
    footnote: str,
    tone: str = "neutral",
) -> dict[str, Any]:
    return {
        "code": code,
        "label": label,
        "value_text": value_text,
        "unit": unit,
        "sub_text": sub_text,
        "delta_text": None,
        "delta_direction": None,
        "delta_is_good": None,
        "tone": tone,
        "panel_id": "",
        "footnote": footnote,
    }


def _live_business_kpis() -> list[dict[str, Any]]:
    """Business-view KPI tiles, computed live from the same queries Tickets,
    Conversations and Customers already use for the same facts.

    These used to be frozen `kpi_snapshots` rows describing the original
    ~100-row reference sample. That drifted the moment the real ETL held
    more than the sample did -- Command Centre kept saying "100 conversations"
    long after Tickets/Conversations/Provenance correctly said the real,
    larger number, which is confusing in exactly the way a leadership
    dashboard can't afford to be. Computing these tiles from the same
    functions those other pages call means they can never disagree again.
    """
    live_a = _live_population_a() or {}
    summary = ticket_summary()
    repeats = repeat_guests()

    guests_text = next(
        (f["value_text"] for f in live_a.get("figures", []) if f["label"] == "GUESTS"), "0"
    )
    window_from, window_to = live_a.get("window_from"), live_a.get("window_to")
    window_text = (
        f"{_fmt_day(window_from)} - {_fmt_day(window_to)}" if window_from and window_to else ""
    )

    still = summary.get("still_waiting", {})
    untouched = _i(still.get("untouched")) or 0
    bot_raised = _i(summary.get("bot_raised")) or 0
    requests_pct = summary.get("requests_pct")

    return [
        _kpi_tile(
            "conversations",
            "Conversations",
            str(live_a.get("row_count") or summary.get("conversations") or 0),
            "",
            f"{window_text} - live" if window_text else "Kore.ai session page",
            live_a.get("caveat")
            or "Real ETL pull -- Kore.ai's own session API may report more available.",
        ),
        _kpi_tile(
            "guests_served",
            "Guests served",
            guests_text,
            "",
            f"{guests_text} distinct - sessions only",
            "Distinct people in the session page. Repeat contact is measured on tickets, not "
            f"sessions - see Customers, where {_i(repeats.get('repeat_guests')) or 0} guests "
            "came back.",
        ),
        _kpi_tile(
            "requests_raised",
            "Requests raised",
            str(_i(summary.get("requests_raised")) or 0),
            "",
            f"{requests_pct}% of conversations" if requests_pct is not None else "of conversations",
            "Conversations that produced a Zendesk ticket, matched by ticket number.",
        ),
        _kpi_tile(
            "still_waiting",
            "Still waiting",
            f"{untouched} of {bot_raised}",
            "",
            f"Untouched - {_i(still.get('open')) or 0} open, {_i(still.get('solved')) or 0} solved",
            still.get("note") or "",
            "critical" if untouched else "good",
        ),
    ]


def kpis(view: str | None = None, state: str = "healthy") -> dict[str, Any]:
    """The headline tile strip for one view in one incident state.

    Population: A/B for the business view (computed live), T for the
    technical view (stored rows, since those describe the incident
    simulation's two fixed healthy/incident states rather than something
    live-queryable).
    """
    chosen_view = _require(view, VIEWS, "view", "business")
    chosen_state = _require(state, STATES, "state", "healthy")
    if chosen_view == "business":
        items = _live_business_kpis()
        basis = _population_basis("A")
    else:
        items = fetch_all(
            """
            SELECT code, label, value_text, unit, sub_text, delta_text,
                   delta_direction, delta_is_good, tone, panel_id, footnote
            FROM kpi_snapshots
            WHERE view = %s AND state = %s
            ORDER BY sort_order, id
            """,
            (chosen_view, chosen_state),
        )
        basis = f"OpenTelemetry signals, last 24 hours · state {chosen_state}"
    return {
        "view": chosen_view,
        "state": chosen_state,
        "items": items,
        "basis": basis,
    }


def _incident_row() -> dict[str, Any] | None:
    row = fetch_one(
        """
        SELECT code, title, detail, severity, started_at, is_simulated
        FROM incidents
        ORDER BY id
        LIMIT 1
        """
    )
    if not row:
        return None
    return {
        "code": row["code"],
        "title": row["title"],
        "detail": row["detail"],
        "severity": row["severity"],
        "started_at": row["started_at"],
        "is_simulated": row["is_simulated"],
    }


def system_health(state: str = "healthy") -> dict[str, Any]:
    """The health banner: how many services report, and what is wrong if
    anything is.

    Population: T. ``last_signal_seconds`` is measured against the newest
    signal actually held (logs or traces) and is null when nothing has landed
    yet -- it is never faked to a comfortable number.
    """
    chosen_state = _require(state, STATES, "state", "healthy")
    counts = fetch_one(
        """
        SELECT COUNT(*) FILTER (WHERE NOT is_collector)                    AS services_total,
               COUNT(*) FILTER (WHERE NOT is_collector AND is_reporting)   AS services_reporting
        FROM services
        """
    ) or {}
    services_total = _i(counts.get("services_total")) or 0
    services_reporting = _i(counts.get("services_reporting")) or 0

    signal = fetch_one(
        """
        SELECT GREATEST(
                 (SELECT MAX(observed_at) FROM log_records),
                 (SELECT MAX(started_at)  FROM traces)
               ) AS last_signal_at
        """
    ) or {}
    last_signal_at: datetime | None = signal.get("last_signal_at")
    last_signal_seconds: int | None = None
    if last_signal_at is not None:
        now = datetime.now(timezone.utc)
        if last_signal_at.tzinfo is None:  # pragma: no cover - schema is timestamptz
            last_signal_at = last_signal_at.replace(tzinfo=timezone.utc)
        last_signal_seconds = max(0, int((now - last_signal_at).total_seconds()))

    incident = _incident_row() if chosen_state == "incident" else None

    if chosen_state == "incident" and incident:
        headline = incident["title"]
        detail = incident["detail"]
        tone = "critical"
    elif chosen_state == "incident":
        headline = "Service degradation detected"
        detail = "The incident simulation is on but no incident row is seeded."
        tone = "critical"
    else:
        headline = "All OSW services are operational"
        # Not "... · last signal N seconds ago" here: that phrase already
        # lives on the line below, computed from `last_signal_seconds` and
        # formatted for whichever unit (s/m/h/d) actually reads clearly --
        # duplicating it here in raw seconds would just be the same fact
        # asserted twice, once unreadable.
        detail = f"{services_reporting} services reporting · OTLP export healthy"
        tone = "good"

    return {
        "state": chosen_state,
        "headline": headline,
        "detail": detail,
        "tone": tone,
        "services_reporting": services_reporting,
        "services_total": services_total,
        "last_signal_seconds": last_signal_seconds,
        "last_signal_at": last_signal_at,
        "incident": incident,
        "basis": "Service registry and the newest signal held (logs and traces)",
    }


def _hop_tone(state: str, healthy_ms: int | None, incident_ms: int | None) -> str:
    """A hop is only called out when the incident genuinely hurt it.

    "Materially worse" is half again as slow, or a full second slower --
    the seeded enrichment hop (852ms -> 4.7s) clears both. Hops whose timing is
    unchanged stay neutral so the eye lands on the one that moved.
    """
    if state != "incident" or healthy_ms is None or incident_ms is None:
        return "neutral"
    delta = incident_ms - healthy_ms
    if incident_ms >= healthy_ms * 1.5 or delta >= 1000:
        return "critical"
    if incident_ms >= healthy_ms * 1.2 or delta >= 250:
        return "warning"
    return "neutral"


def topology(state: str = "healthy") -> dict[str, Any]:
    """The ordered business request path, timed for the current state, with the
    telemetry path shown separately.

    Population: T. Durations come from ``topology_hops.healthy_ms`` or
    ``incident_ms`` -- the two states are seeded rows, not a multiplier applied
    in the browser.
    """
    chosen_state = _require(state, STATES, "state", "healthy")
    rows = fetch_all(
        """
        SELECT hop_no, service_name, display_name, operation, is_origin,
               healthy_ms, incident_ms, is_telemetry_path
        FROM topology_hops
        ORDER BY hop_no
        """
    )

    request_path: list[dict[str, Any]] = []
    collector: dict[str, Any] | None = None
    for row in rows:
        healthy_ms, incident_ms = _i(row["healthy_ms"]), _i(row["incident_ms"])
        duration_ms = incident_ms if chosen_state == "incident" else healthy_ms
        if row["is_origin"]:
            duration_ms = None  # the guest is the origin; it has no server timing
        entry = {
            "hop_no": _i(row["hop_no"]),
            "service_name": row["service_name"],
            "display_name": row["display_name"],
            "operation": row["operation"],
            "duration_ms": duration_ms,
            "healthy_ms": healthy_ms,
            "incident_ms": incident_ms,
            "is_origin": row["is_origin"],
            "tone": _hop_tone(chosen_state, healthy_ms, incident_ms),
        }
        if row["is_telemetry_path"]:
            if collector is None:
                collector = {
                    "display_name": row["display_name"],
                    "detail": row["operation"],
                    "duration_ms": duration_ms,
                }
            continue
        request_path.append(entry)

    if collector is None:
        fallback = fetch_one(
            """
            SELECT display_name, role
            FROM services
            WHERE is_collector
            ORDER BY service_name
            LIMIT 1
            """
        )
        if fallback:
            collector = {
                "display_name": fallback["display_name"],
                "detail": fallback["role"] or "Receives and routes signals",
                "duration_ms": None,
            }

    reporting = fetch_one(
        """
        SELECT COUNT(*) FILTER (WHERE NOT is_collector)                  AS total,
               COUNT(*) FILTER (WHERE NOT is_collector AND is_reporting) AS reporting
        FROM services
        """
    ) or {}
    total = _i(reporting.get("total")) or 0
    live = _i(reporting.get("reporting")) or 0

    return {
        "state": chosen_state,
        "request_path": request_path,
        "telemetry_path": {
            "title": "Telemetry path · separate from the request",
            "detail": "Every service exports traces, metrics and logs",
            "collector": collector,
        },
        "reporting_text": f"{live} / {total} reporting",
        "basis": f"Seeded hop timings for state {chosen_state}",
    }


def signals() -> dict[str, Any]:
    """Signal coverage: five signals, one context.

    Population: T.
    """
    rows = fetch_all(
        """
        SELECT signal, glyph, volume_text, coverage_text, description, route
        FROM signal_coverage
        ORDER BY sort_order, signal
        """
    )
    return {
        "items": rows,
        "basis": "Signal coverage across the instrumented services",
    }


def _stage_shape(
    stage_no: int,
    code: str,
    label: str,
    reached: int | None,
    pct_of_sample: float | None,
    lost_here: int | None,
    why: str,
    basis_change: bool,
    basis: str = "",
) -> dict[str, Any]:
    """One funnel stage. Identical shape for both journey sources so a single
    component can render either."""
    return {
        "stage_no": stage_no,
        "code": code,
        "label": label,
        "reached": reached,
        "pct_of_sample": pct_of_sample,
        "lost_here": lost_here,
        "why": why,
        "basis": basis,
        "basis_change": basis_change,
    }


def _review_stages() -> list[dict[str, Any]]:
    rows = fetch_all(
        """
        SELECT stage_no, code, label, reached, pct_of_sample, lost_here,
               why, basis, basis_change
        FROM journey_stages
        ORDER BY stage_no
        """
    )
    return [
        _stage_shape(
            stage_no=_i(row["stage_no"]) or 0,
            code=row["code"],
            label=row["label"],
            reached=_i(row["reached"]),
            pct_of_sample=_f(row["pct_of_sample"]),
            lost_here=_i(row["lost_here"]),
            why=row["why"],
            basis_change=row["basis_change"],
            basis=row["basis"],
        )
        for row in rows
    ]


def _metric_totals() -> dict[str, int]:
    """Total observations per instrument, from whichever metric table holds it.

    Precedence: recorded time series, then outcome dimensions, then histogram
    buckets. All three are sums of the same underlying instrument, so the first
    one present wins and the rest are ignored.
    """
    totals: dict[str, int] = {}
    for sql in (
        "SELECT instrument, SUM(value) AS total FROM metric_series GROUP BY instrument",
        "SELECT instrument, SUM(count) AS total FROM metric_outcomes GROUP BY instrument",
        "SELECT instrument, SUM(count) AS total FROM metric_histogram_buckets GROUP BY instrument",
    ):
        for row in fetch_all(sql):
            name, total = row["instrument"], _i(row["total"])
            if name and total is not None:
                totals.setdefault(name, total)
    return totals


def _enrichment_success_total() -> int | None:
    """Successful enrichment operations -- the count that stands behind
    "document attached" when ``osw.document.attached`` has no rows of its own."""
    return _i(
        fetch_value(
            """
            SELECT SUM(count) AS total
            FROM metric_outcomes
            WHERE instrument = %s AND NOT is_error AND result ILIKE %s
            """,
            ("osw.enrichment.operation", "%success%"),
        )
    )


def _kpi_conversation_total(state: str) -> int | None:
    row = fetch_one(
        """
        SELECT value_text
        FROM kpi_snapshots
        WHERE view = 'technical' AND state = %s AND code ILIKE %s
        ORDER BY sort_order, id
        LIMIT 1
        """,
        (state, "%conversation%"),
    )
    return _leading_int(row["value_text"]) if row else None


def _telemetry_stages(state: str) -> list[dict[str, Any]]:
    """The OTel guest-journey funnel, assembled from the seeded telemetry.

    Stage names and order come from ``operating_model`` (kind ``journey_stage``).
    Each stage's count is resolved in a fixed order so the answer is
    reproducible: the instrument that measures the stage, then the technical
    KPI tile (conversations only), then a count seeded at the front of the
    stage's own body text. A stage with no source stays ``null`` rather than
    dropping to zero.
    """
    rows = fetch_all(
        """
        SELECT code, title, body
        FROM operating_model
        WHERE kind = 'journey_stage'
        ORDER BY sort_order, code
        """
    )
    if not rows:
        return []

    totals = _metric_totals()
    stages: list[dict[str, Any]] = []
    previous: int | None = None
    first: int | None = None

    for index, row in enumerate(rows, start=1):
        haystack = f"{row['code']} {row['title']}".lower()
        # Most specific stage first, so "document attached to ticket" resolves to
        # the document stage rather than the ticket one.
        matched_keyword: str | None = None
        instruments: tuple[str, ...] = ()
        for keyword, candidates in _STAGE_INSTRUMENTS:
            if keyword in haystack:
                matched_keyword, instruments = keyword, candidates
                break

        reached: int | None = None
        if matched_keyword == "conversation":
            # The headline conversation count is the funnel's denominator, so it
            # is taken from the KPI tile the screen already shows rather than
            # from a series that might be seeded as a rate.
            reached = _kpi_conversation_total(state)
        if reached is None:
            for instrument in instruments:
                if instrument in totals:
                    reached = totals[instrument]
                    break
        if reached is None and matched_keyword == "document":
            reached = _enrichment_success_total()
        if reached is None:
            reached = _leading_int(row["body"])

        if index == 1:
            first = reached
        lost_here: int | None = None
        if previous is not None and reached is not None and previous >= reached:
            lost_here = previous - reached

        stages.append(
            _stage_shape(
                stage_no=index,
                code=row["code"],
                label=row["title"],
                reached=reached,
                pct_of_sample=_pct(reached, first),
                lost_here=lost_here,
                why=row["body"] or "",
                basis_change=False,
                basis="telemetry",
            )
        )
        previous = reached

    return stages


def _sample_stage(stages: Sequence[dict[str, Any]]) -> dict[str, Any] | None:
    """The stage the percentages are measured against.

    For the hand-reviewed chain that is the stage flagged ``basis_change``
    (stage 2 -- the 74 reviewed sessions, which are *not* a subset of the API
    page above them). For telemetry it is simply stage 1.
    """
    if not stages:
        return None
    for stage in stages:
        if stage.get("basis_change"):
            return stage
    return stages[0]


def _funnel_callouts(
    stages: Sequence[dict[str, Any]],
    *,
    biggest_loss_detail: str | None = None,
    lost_after_ticket_detail: str | None = None,
) -> list[dict[str, Any]]:
    """The four callout cards, derived from the funnel rather than stored.

    Keeping them derived means a reseeded funnel cannot leave a stale callout
    behind. Any callout whose inputs are missing is omitted rather than shown
    as zero.

    ``biggest_loss_detail``/``lost_after_ticket_detail`` override the default
    text for those two callouts specifically -- used by the hand-reviewed
    chain (``journey_chain``) to name the real drop-off categories instead of
    the generic per-stage "why", without changing what the live telemetry
    funnel (``journey_overview``) shows, since that call leaves them unset.
    """
    if not stages:
        return []
    sample = _sample_stage(stages)
    final = stages[-1]
    callouts: list[dict[str, Any]] = []

    if sample and final.get("reached") is not None and sample.get("reached") is not None:
        pct = _pct(final["reached"], sample["reached"])
        callouts.append(
            {
                "code": "COMPLETES_CHAIN",
                "label": "Completes the chain",
                "value_text": f"{final['reached']} of {sample['reached']}",
                "body": (
                    f"{pct}% -- reached {final['label'].lower()}"
                    if pct is not None
                    else f"reached {final['label'].lower()}"
                ),
                "tone": "good",
            }
        )

    losses = [s for s in stages if s.get("lost_here")]
    if losses:
        worst = max(losses, key=lambda s: s["lost_here"])
        stage_no = worst["stage_no"]
        detail = biggest_loss_detail if biggest_loss_detail is not None else worst.get("why")
        callouts.append(
            {
                "code": "BIGGEST_LOSS",
                "label": "Biggest single loss",
                "value_text": str(worst["lost_here"]),
                "body": (
                    f"lost between stage {stage_no - 1} and {stage_no}"
                    + (f" -- {detail}" if detail else "")
                ),
                "tone": "critical",
            }
        )

    ticket_index = next(
        (
            i
            for i, s in enumerate(stages)
            if "ticket" in f"{s.get('code','')} {s.get('label','')}".lower()
        ),
        None,
    )
    if ticket_index is not None:
        after = [s["lost_here"] for s in stages[ticket_index + 1 :] if s.get("lost_here")]
        if after:
            callouts.append(
                {
                    "code": "LOST_AFTER_TICKET",
                    "label": "Lost after the ticket",
                    "value_text": str(sum(after)),
                    "body": lost_after_ticket_detail
                    or (
                        "ticket raised but no document reached it -- the guest has "
                        "already been told their request is in hand"
                    ),
                    "tone": "critical",
                }
            )

    spoke = next(
        (
            s
            for s in stages
            if "spoke" in f"{s.get('code','')} {s.get('label','')}".lower()
        ),
        None,
    )
    if spoke and spoke.get("lost_here"):
        callouts.append(
            {
                "code": "NEVER_SPOKE",
                "label": "Never a bot problem",
                "value_text": str(spoke["lost_here"]),
                "body": "greeted and left without typing",
                "tone": "neutral",
            }
        )

    return callouts


def journey_overview(source: str | None = None, state: str = "healthy") -> dict[str, Any]:
    """The guest-journey funnel from either source, in one shape.

    ``source=telemetry`` is population T -- the live OTel funnel, every stage
    measured by an instrument. ``source=review`` is population C -- the
    hand-reviewed chat-to-document chain, where stage 2 changes basis (the 74
    reviewed sessions are not a subset of the capped API page above them).
    """
    chosen = _require(source, JOURNEY_SOURCES, "source", "telemetry")
    chosen_state = _require(state, STATES, "state", "healthy")
    if chosen == "review":
        stages = _review_stages()
        basis = _population_basis("C", "Kore.ai extended session detail")
    else:
        stages = _telemetry_stages(chosen_state)
        window = fetch_one(
            "SELECT window_label AS window FROM metric_summaries ORDER BY sort_order, code LIMIT 1"
        )
        window_text = (window or {}).get("window") or "24h"
        sample = _sample_stage(stages)
        reached = (sample or {}).get("reached")
        basis = (
            f"{reached} conversations, last {window_text} · OpenTelemetry signals"
            if reached is not None
            else f"OpenTelemetry signals, last {window_text}"
        )
    return {
        "source": chosen,
        "state": chosen_state,
        "basis": basis,
        "stages": stages,
        "callouts": _funnel_callouts(stages),
    }


def operating_model() -> dict[str, Any]:
    """The four-pillar operating-model slide, as rows rather than layout.

    Population: all -- this is the narrative frame around the figures, not a
    figure itself.
    """
    rows = fetch_all(
        """
        SELECT kind, code, title, body
        FROM operating_model
        ORDER BY kind, sort_order, code
        """
    )
    grouped: dict[str, list[dict[str, Any]]] = {
        "pillar": [],
        "signal": [],
        "journey_stage": [],
        "privacy": [],
        "scale": [],
    }
    for row in rows:
        grouped.setdefault(row["kind"], []).append(
            {"code": row["code"], "title": row["title"], "body": row["body"]}
        )
    return {
        "pillars": grouped.get("pillar", []),
        "signals": grouped.get("signal", []),
        "journey_stages": grouped.get("journey_stage", []),
        "privacy": grouped.get("privacy", []),
        "scale": grouped.get("scale", []),
        "basis": "Operating model -- illustrative product views for discussion",
    }


# =========================================================================== #
# Guest journey -- /api/journey  (population C unless stated)
# =========================================================================== #


def journey_chain() -> dict[str, Any]:
    """P-54, chat to document: the hand-reviewed six-stage chain.

    Population: C -- 74 reviewed sessions over 5 of 19 days. Stage 1 is the
    Kore.ai API page, carried for scale only; the double bar on stage 2 marks
    the change of basis, not a drop.
    """
    stages = _review_stages()
    table = [
        {
            "stage": stage["label"],
            "reached": stage["reached"],
            "of_sample": stage["pct_of_sample"],
            "lost_here": stage["lost_here"],
            "why": stage["why"],
        }
        for stage in stages
    ]
    return {
        "basis": _population_basis("C", "Kore.ai extended session detail"),
        "stages": stages,
        "callouts": _funnel_callouts(
            stages,
            biggest_loss_detail=(
                "Talk to Human, Other/Fallback, Career Opportunities, Product "
                "information (SearchAI), FAQ's, drop-off during mid conversation"
            ),
            lost_after_ticket_detail=(
                "Missing required values within the flow conversation for the "
                "enrichment, TTH, Other/Fallback, Career Opportunities"
            ),
        ),
        "table": table,
    }


def quit_reasons() -> dict[str, Any]:
    """Where guests quit: the question that ended the conversation.

    Population: C. ``mid_flow`` is everything that is not "never spoke" --
    five guests who never typed are not a bot problem, and mixing them into the
    drop-off count would overstate it.
    """
    rows = fetch_all(
        """
        SELECT code, label, count, category
        FROM quit_reasons
        ORDER BY sort_order, count DESC, code
        """
    )
    items = [
        {
            "code": row["code"],
            "label": row["label"],
            "count": _i(row["count"]),
            "category": row["category"],
        }
        for row in rows
    ]
    never_spoke = sum(
        item["count"] or 0 for item in items if item["category"] == "never_spoke"
    )
    paperwork = sum(
        item["count"] or 0 for item in items if item["category"] == "paperwork"
    )
    total = sum(item["count"] or 0 for item in items)
    return {
        "items": items,
        "totals": {
            "never_spoke": never_spoke,
            "paperwork": paperwork,
            "mid_flow": total - never_spoke,
            "all_reasons": total,
        },
        "basis": _population_basis("C", "Kore.ai extended session detail"),
    }


def journey_outcomes() -> dict[str, Any]:
    """P-32, what the conversation produced, with the per-day review table.

    Population: C. ``duplicates`` is derived (tickets minus requests that got
    one) rather than stored, because the queue being larger than the demand
    behind it is the finding. Day rows keep their NULLs: a day that was not
    read is not a day with no traffic.
    """
    days = fetch_all(
        """
        SELECT review_date AS day, reviewed, ticket_created, no_ticket, was_read, note
        FROM hand_review_days
        ORDER BY review_date
        """
    )
    by_day = [
        {
            "day": row["day"],
            "reviewed": _i(row["reviewed"]),
            "ticket_created": _i(row["ticket_created"]),
            "no_ticket": _i(row["no_ticket"]),
            "was_read": row["was_read"],
            "note": row["note"],
        }
        for row in days
    ]
    totals = fetch_one(
        """
        SELECT SUM(reviewed)       AS reviewed,
               SUM(ticket_created) AS got_ticket,
               SUM(no_ticket)      AS no_ticket
        FROM hand_review_days
        """
    ) or {}
    reviewed = _i(totals.get("reviewed"))
    got_ticket = _i(totals.get("got_ticket"))
    no_ticket = _i(totals.get("no_ticket"))

    sessions = fetch_one(
        """
        SELECT COUNT(*)                                          AS rows_held,
               COUNT(*) FILTER (WHERE guest_spoke)               AS made_request,
               COUNT(*) FILTER (WHERE NOT guest_spoke)           AS never_spoke
        FROM hand_review_sessions
        """
    ) or {}
    rows_held = _i(sessions.get("rows_held")) or 0

    if rows_held:
        made_request = _i(sessions.get("made_request"))
        never_spoke = _i(sessions.get("never_spoke"))
    else:
        # Session-level rows have not landed yet: fall back to the quit-reason
        # sheet for "never spoke" instead.
        never_spoke = _i(
            fetch_value(
                "SELECT SUM(count) AS n FROM quit_reasons WHERE category = %s",
                ("never_spoke",),
            )
        )
        made_request = (
            reviewed - never_spoke
            if reviewed is not None and never_spoke is not None
            else None
        )

    # `tickets`/`duplicates` always come from the day-level totals plus the
    # duplicate-pairs count, never from a per-session ticket_id tally: the
    # session-level rows are an illustrative reconciliation of the aggregates
    # below, not an independent ticket count, so counting distinct ticket ids
    # on them can disagree with the totals they were built to match.
    extra = _i(fetch_value("SELECT COUNT(*) AS n FROM duplicate_pairs"))
    tickets = (
        got_ticket + extra
        if got_ticket is not None and extra is not None
        else got_ticket
    )
    duplicates = (
        tickets - got_ticket
        if tickets is not None and got_ticket is not None
        else None
    )
    return {
        "reviewed": reviewed,
        "made_request": made_request,
        "never_spoke": never_spoke,
        "got_ticket": got_ticket,
        "no_ticket": no_ticket,
        "tickets": tickets,
        "duplicates": duplicates,
        "by_day": by_day,
        "basis": _population_basis("C", "Kore.ai extended session detail"),
    }


def _automation_gaps(panel_id: str) -> list[dict[str, Any]]:
    """Fixes that would make a hand-kept panel automatic.

    Filtered to the panel when it has rows of its own; otherwise every gap is
    returned, so a seed that files them under one id still renders.
    """
    rows = fetch_all(
        """
        SELECT change, effect
        FROM automation_gaps
        WHERE panel_id = %s
        ORDER BY sort_order, id
        """,
        (panel_id,),
    )
    if rows:
        return [{"change": r["change"], "effect": r["effect"]} for r in rows]
    rows = fetch_all(
        "SELECT change, effect FROM automation_gaps ORDER BY panel_id, sort_order, id"
    )
    return [{"change": r["change"], "effect": r["effect"]} for r in rows]


def enrichment() -> dict[str, Any]:
    """P-55, document enrichment: did the paperwork actually reach the ticket?

    Population: C -- the only source that can answer this at all, because the
    Zendesk ticket API returns no attachments field. ``failures`` carries
    ``is_intake`` so the panel can show that the pipeline is not the fault.
    """
    outcomes = fetch_all(
        """
        SELECT code, label, count, meaning
        FROM enrichment_outcomes
        ORDER BY sort_order, code
        """
    )
    failures = fetch_all(
        """
        SELECT code, label, count, is_intake
        FROM enrichment_failures
        ORDER BY sort_order, code
        """
    )
    return {
        "outcomes": [
            {
                "code": r["code"],
                "label": r["label"],
                "count": _i(r["count"]),
                "meaning": r["meaning"],
            }
            for r in outcomes
        ],
        "failures": [
            {
                "code": r["code"],
                "label": r["label"],
                "count": _i(r["count"]),
                "is_intake": r["is_intake"],
            }
            for r in failures
        ],
        "automation_gaps": _automation_gaps("P-55"),
        "basis": _population_basis("C", "Kore.ai extended session detail"),
    }


def duplicates() -> dict[str, Any]:
    """Duplicate tickets: is the service team being asked to do the same job
    twice?

    Population: C. ``sessions`` counts the distinct duplicate groups found in
    the review; ``extra_tickets`` counts the surplus tickets those groups
    produced.
    """
    pairs = fetch_all(
        """
        SELECT ticket_a, ticket_b, is_exact_repeat, evidence, cause
        FROM duplicate_pairs
        ORDER BY id
        """
    )
    grouped = _i(
        fetch_value(
            """
            SELECT COUNT(DISTINCT duplicate_group) AS n
            FROM hand_review_sessions
            WHERE duplicate_group IS NOT NULL AND duplicate_group <> ''
            """
        )
    )
    sessions = grouped if grouped else len(pairs)
    cause = next((p["cause"] for p in pairs if p["cause"]), "")
    return {
        "sessions": sessions,
        "extra_tickets": len(pairs),
        "exact_repeats": sum(1 for p in pairs if p["is_exact_repeat"]),
        "pairs": [
            {
                "ticket_a": p["ticket_a"],
                "ticket_b": p["ticket_b"],
                "is_exact_repeat": p["is_exact_repeat"],
                "evidence": p["evidence"],
            }
            for p in pairs
        ],
        "cause": cause,
        "basis": _population_basis("C", "Kore.ai extended session detail"),
    }


def _duration_text(seconds: float | None) -> str | None:
    if seconds is None:
        return None
    if seconds < 60:
        return f"{seconds:.1f} sec"
    return f"{seconds / 60:.1f} min"


def durations(
    bot_id: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> dict[str, Any]:
    """P-36, length and duration: how long the bot holds a guest.

    Population: A -- the Kore.ai session page. Typical is the median, not the
    mean, because one 23-minute return would otherwise drag it. Every session
    in this page reports closed, so the API cannot tell an idle timeout from a
    satisfied guest; only the hand review can.
    """
    params: list[Any] = []
    sql = (
        """
        SELECT COUNT(duration_seconds)                                        AS scored,
               COUNT(*)                                                       AS sessions,
               MIN(duration_seconds)                                          AS fastest,
               PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY duration_seconds)   AS typical,
               MAX(duration_seconds)                                          AS longest
        FROM conversations
        WHERE 1 = 1
        """
        + _bot_clause("bot_id", bot_id, params)
        + _range_clause("started_at", date_from, date_to, params)
    )
    row = fetch_one(sql, params) or {}
    sessions = _i(row.get("sessions")) or 0
    fastest, typical, longest = (
        _f(row.get("fastest"), 1),
        _f(row.get("typical"), 1),
        _f(row.get("longest"), 1),
    )
    basis = (
        f"Across the {sessions} sessions in the API page."
        if sessions
        else "No sessions held for this selection yet."
    )
    return {
        "fastest_text": _duration_text(fastest),
        "typical_text": _duration_text(typical),
        "longest_text": _duration_text(longest),
        "fastest_seconds": fastest,
        "typical_seconds": typical,
        "longest_seconds": longest,
        "sessions": sessions,
        "basis": basis,
    }


# =========================================================================== #
# Tickets -- /api/tickets  (population B unless stated)
# =========================================================================== #


def ticket_summary(
    bot_id: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> dict[str, Any]:
    """P-43 + P-45: how many requests the bot raised, and how many are still
    waiting.

    Population: B for the ticket counts, A for the conversation divisor behind
    ``requests_pct`` -- the two are different extracts, which is exactly why
    the percentage is computed inside the conversation page and never across
    both.
    """
    ticket_params: list[Any] = []
    ticket_sql = (
        """
        SELECT COUNT(*)                                                             AS total,
               COUNT(*) FILTER (WHERE is_bot_raised)                                AS bot_raised,
               COUNT(*) FILTER (WHERE is_bot_raised
                                AND lower(coalesce(status,'')) = 'new')             AS untouched,
               COUNT(*) FILTER (WHERE is_bot_raised
                                AND lower(coalesce(status,'')) = 'open')            AS open_count,
               COUNT(*) FILTER (WHERE is_bot_raised
                                AND lower(coalesce(status,'')) IN ('solved','closed')) AS solved,
               COUNT(*) FILTER (WHERE NOT is_bot_raised
                                AND lower(coalesce(status,'')) = 'open')            AS other_open
        FROM tickets
        WHERE 1 = 1
        """
        + _range_clause("created_at", date_from, date_to, ticket_params)
    )
    tickets = fetch_one(ticket_sql, ticket_params) or {}

    conv_params: list[Any] = []
    conv_sql = (
        """
        SELECT COUNT(*)                                        AS conversations,
               COUNT(*) FILTER (WHERE ticket_id IS NOT NULL)    AS carrying
        FROM conversations
        WHERE 1 = 1
        """
        + _bot_clause("bot_id", bot_id, conv_params)
        + _range_clause("started_at", date_from, date_to, conv_params)
    )
    conversations = fetch_one(conv_sql, conv_params) or {}

    bot_raised = _i(tickets.get("bot_raised")) or 0
    untouched = _i(tickets.get("untouched")) or 0
    open_count = _i(tickets.get("open_count")) or 0
    solved = _i(tickets.get("solved")) or 0
    other_open = _i(tickets.get("other_open")) or 0
    requests_raised = _i(conversations.get("carrying")) or 0

    if bot_raised:
        note = (
            f"{untouched} of {bot_raised} bot-raised tickets are still new -- "
            f"{open_count} open, {solved} solved."
        )
        if other_open:
            note += (
                f" The {other_open} tickets at open elsewhere in the queue arrived by "
                "web, phone and email -- none of them from the bot."
            )
    else:
        note = "No bot-raised tickets in this selection."

    return {
        "total": _i(tickets.get("total")) or 0,
        "bot_raised": bot_raised,
        "requests_raised": requests_raised,
        "requests_pct": _pct(requests_raised, conversations.get("conversations")),
        "conversations": _i(conversations.get("conversations")) or 0,
        "still_waiting": {
            "untouched": untouched,
            "open": open_count,
            "solved": solved,
            "note": note,
        },
        "basis": _population_basis("B"),
    }


def ticket_status(
    date_from: date | None = None,
    date_to: date | None = None,
    bot_raised: bool | None = True,
) -> dict[str, Any]:
    """Bot-raised tickets by Zendesk status.

    Population: B by default. ``new`` carries the warning tone because on this
    screen an untouched ticket is the problem, not the neutral starting point.
    """
    params: list[Any] = []
    clause = ""
    if bot_raised is not None:
        params.append(bot_raised)
        clause = " AND is_bot_raised = %s"
    sql = (
        """
        SELECT coalesce(nullif(status, ''), 'unknown') AS status, COUNT(*) AS count
        FROM tickets
        WHERE 1 = 1
        """
        + clause
        + _range_clause("created_at", date_from, date_to, params)
        # Positional ordering: the grouped expression is an alias, so ordering by
        # position leaves no doubt which one Postgres resolves.
        + " GROUP BY 1 ORDER BY 2 DESC, 1"
    )
    rows = fetch_all(sql, params)
    return {
        "items": [
            {
                "status": row["status"],
                "count": _i(row["count"]),
                "tone": _STATUS_TONE.get((row["status"] or "").lower(), "neutral"),
            }
            for row in rows
        ],
        "basis": _population_basis("B") if bot_raised else "Every ticket held",
    }


def activity(
    date_from: date | None = None,
    date_to: date | None = None,
) -> dict[str, Any]:
    """P-07, activity over time: conversations against bot-raised tickets.

    Population: A and B side by side, on purpose -- the Kore page covers
    13-18 Aug and the Zendesk export 17-19 Aug, so the one overlapping day is
    the only day the two systems can be compared. A NULL is a day absent from
    that extract, not a day when nothing happened, and it is returned as
    ``null`` so the chart can say so.
    """
    params: list[Any] = []
    sql = (
        """
        SELECT day, conversations, bot_tickets, reviewed, review_ticket_created,
               review_no_ticket, in_kore_extract, in_zendesk_extract, was_reviewed
        FROM daily_activity
        WHERE 1 = 1
        """
        + _range_clause("day", date_from, date_to, params)
        + " ORDER BY day"
    )
    rows = fetch_all(sql, params)
    items = [
        {
            "day": row["day"],
            "conversations": _i(row["conversations"]),
            "bot_tickets": _i(row["bot_tickets"]),
            "reviewed": _i(row["reviewed"]),
            "review_ticket_created": _i(row["review_ticket_created"]),
            "review_no_ticket": _i(row["review_no_ticket"]),
            "in_kore_extract": row["in_kore_extract"],
            "in_zendesk_extract": row["in_zendesk_extract"],
            "was_reviewed": row["was_reviewed"],
        }
        for row in rows
    ]
    totals = {
        "conversations": sum(i["conversations"] or 0 for i in items) if items else None,
        "bot_tickets": sum(i["bot_tickets"] or 0 for i in items) if items else None,
    }
    return {
        "items": items,
        "totals": totals,
        "basis": (
            "Kore page and Zendesk export on one axis · tickets are bot-raised "
            "only · null means the day is absent from that extract, not that "
            "nothing happened"
        ),
    }


def conversation_ticket_correlation(
    bot_id: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> dict[str, Any]:
    """P-43, conversation to ticket: does the link between the two systems
    hold?

    Population: A. ``carry_ticket_number`` counts sessions with a TicketID
    session tag; ``backend_step_done`` counts those whose lifecycle event says
    the Zendesk call succeeded. The tag is written on a handful of sessions
    only, so this proves the link works -- it does not measure how often it is
    used.
    """
    # The success pattern is a bound parameter, not an interpolated literal, so
    # no percent-escaping games are needed in the SQL text.
    params: list[Any] = ["%success%"]
    sql = (
        """
        SELECT COUNT(*)                                              AS conversations,
               COUNT(*) FILTER (WHERE ticket_id IS NOT NULL)          AS carry_ticket_number,
               COUNT(*) FILTER (WHERE ticket_id IS NOT NULL
                                AND event_name ILIKE %s)              AS backend_step_done
        FROM conversations
        WHERE 1 = 1
        """
        + _bot_clause("bot_id", bot_id, params)
        + _range_clause("started_at", date_from, date_to, params)
    )
    row = fetch_one(sql, params) or {}
    conversations = _i(row.get("conversations")) or 0
    carry = _i(row.get("carry_ticket_number")) or 0
    done = _i(row.get("backend_step_done")) or 0
    pct = _pct(carry, conversations)
    note = (
        f"The TicketID tag is written on {carry} of {conversations} sessions"
        + (f" ({pct}%)" if pct is not None else "")
        + f", and {done} of those record a successful back-end step. "
        "A proof of concept, not a measurement."
    )
    return {
        "conversations": conversations,
        "carry_ticket_number": carry,
        "backend_step_done": done,
        "carry_pct": pct,
        "note": note,
        "basis": _population_basis("A"),
    }


def backend_failures(
    date_from: date | None = None,
    date_to: date | None = None,
) -> dict[str, Any]:
    """Back-end and automation failure signals carried on bot-raised tickets.

    Population: B. ``affected`` is the number of distinct tickets carrying at
    least one failure tag, which is smaller than the sum of the rows because
    one ticket can fail twice.
    """
    rows = fetch_all(
        """
        SELECT tag, label, ticket_count, stage
        FROM backend_failures
        ORDER BY sort_order, ticket_count DESC, tag
        """
    )
    items = [
        {
            "tag": row["tag"],
            "label": row["label"],
            "ticket_count": _i(row["ticket_count"]),
            "stage": row["stage"],
        }
        for row in rows
    ]

    params: list[Any] = []
    total_sql = (
        """
        SELECT COUNT(*) AS n
        FROM tickets
        WHERE is_bot_raised
        """
        + _range_clause("created_at", date_from, date_to, params)
    )
    total = _i(fetch_value(total_sql, params)) or 0

    affected: int | None = None
    tags = [item["tag"] for item in items if item["tag"]]
    if tags:
        affected = _i(
            fetch_value(
                """
                SELECT COUNT(DISTINCT tt.ticket_id) AS n
                FROM ticket_tags tt
                JOIN tickets t ON t.ticket_id = tt.ticket_id
                WHERE t.is_bot_raised AND tt.tag = ANY(%s)
                """,
                (tags,),
            )
        )
    if not affected:
        # No tag rows loaded yet: the seeded per-tag counts are the best floor
        # available, and a ticket that failed twice would inflate this -- said
        # plainly in the panel note rather than silently.
        affected = sum(item["ticket_count"] or 0 for item in items) or None

    return {
        "items": items,
        "affected": affected,
        "total": total,
        "basis": _population_basis("B"),
    }


def recent_tickets(
    limit: int | None = DEFAULT_PAGE_LIMIT,
    bot_raised: bool | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> dict[str, Any]:
    """The most recent tickets held, newest first.

    Population: B when ``bot_raised`` is true, otherwise the whole Zendesk page
    we hold (which is itself capped at 100 rows).
    """
    capped = _clamp_limit(limit)
    params: list[Any] = []
    clause = ""
    if bot_raised is not None:
        params.append(bot_raised)
        clause = " AND is_bot_raised = %s"
    sql = (
        """
        SELECT t.ticket_id, t.created_at, t.status, t.priority, t.cruise_line, t.ship_name,
               t.inquiry_type, t.sentiment, t.is_bot_raised, c.session_id
        FROM tickets t
        LEFT JOIN conversations c ON c.ticket_id = t.ticket_id
        WHERE 1 = 1
        """
        + clause.replace("is_bot_raised", "t.is_bot_raised")
        + _range_clause("created_at", date_from, date_to, params)
        + " ORDER BY t.created_at DESC NULLS LAST, t.ticket_id DESC LIMIT %s"
    )
    params.append(capped)
    rows = fetch_all(sql, params)
    return {
        "items": rows,
        "limit": capped,
        "basis": (
            _population_basis("B")
            if bot_raised
            else "Every ticket held -- itself one Zendesk page, capped at 100 rows"
        ),
    }


# =========================================================================== #
# Cruise lines -- /api/lines  (population B)
# =========================================================================== #


def line_contacts(
    date_from: date | None = None,
    date_to: date | None = None,
) -> dict[str, Any]:
    """P-09, contacts by cruise line.

    Population: B. Shares are of the tickets that *name* a line, not of all
    bot-raised tickets -- the line is parsed out of free text, so the unnamed
    remainder is reported separately instead of being spread across partners.
    Raw counts, with no sailing or passenger divisor, so the biggest partner
    always ranks worst.
    """
    params: list[Any] = []
    counts_sql = (
        """
        SELECT COUNT(*)                                                       AS total,
               COUNT(*) FILTER (WHERE nullif(cruise_line, '') IS NOT NULL)     AS named
        FROM tickets
        WHERE is_bot_raised
        """
        + _range_clause("created_at", date_from, date_to, params)
    )
    counts = fetch_one(counts_sql, params) or {}
    named = _i(counts.get("named")) or 0

    group_params: list[Any] = []
    group_sql = (
        """
        SELECT cruise_line, COUNT(*) AS ticket_count
        FROM tickets
        WHERE is_bot_raised AND nullif(cruise_line, '') IS NOT NULL
        """
        + _range_clause("created_at", date_from, date_to, group_params)
        + " GROUP BY cruise_line ORDER BY ticket_count DESC, cruise_line"
    )
    rows = fetch_all(group_sql, group_params)
    total = _i(counts.get("total")) or 0
    return {
        "named": named,
        "total": total,
        "basis": (
            f"{named} of {total} bot-raised tickets name a cruise line · shares "
            "are of the named subset, and are raw counts with no sailing or "
            "passenger divisor"
        ),
        "items": [
            {
                "cruise_line": row["cruise_line"],
                "ticket_count": _i(row["ticket_count"]),
                "share_pct": _pct(row["ticket_count"], named),
            }
            for row in rows
        ],
    }


def ships(
    date_from: date | None = None,
    date_to: date | None = None,
) -> dict[str, Any]:
    """Contacts by ship, with the line each ship belongs to.

    Population: B, and only the tickets that name a ship. Ship names arrive as
    free text ("Holland America Westerdam" was rejected until the guest
    simplified it), so this is a naming-gap panel as much as a demand panel.
    """
    params: list[Any] = []
    sql = (
        """
        SELECT ship_name, cruise_line, COUNT(*) AS ticket_count
        FROM tickets
        WHERE is_bot_raised AND nullif(ship_name, '') IS NOT NULL
        """
        + _range_clause("created_at", date_from, date_to, params)
        + " GROUP BY ship_name, cruise_line ORDER BY ticket_count DESC, ship_name"
    )
    rows = fetch_all(sql, params)
    return {
        "items": [
            {
                "ship_name": row["ship_name"],
                "cruise_line": row["cruise_line"],
                "ticket_count": _i(row["ticket_count"]),
            }
            for row in rows
        ],
        "basis": "Bot-raised tickets that name a ship · parsed from free text",
    }


def _cruise_line_thin_note(date_from: date | None, date_to: date | None) -> dict[str, str] | None:
    """The "not split by cruise line" caveat, sized to the real data held.

    The old reference dashboard's version of this note hardcoded "23 of 28
    name one ... 2 to 9 tickets per partner" -- a real ETL can hold a much
    wider range (this one goes up to 19), which can quietly stop being "too
    thin" for the biggest partners even while it stays true for the smallest.
    Recomputing it live means the conclusion always matches the range it is
    actually describing.
    """
    params: list[Any] = []
    sql = (
        """
        SELECT cruise_line, COUNT(*) AS n
        FROM tickets
        WHERE is_bot_raised AND nullif(cruise_line, '') IS NOT NULL
        """
        + _range_clause("created_at", date_from, date_to, params)
        + " GROUP BY cruise_line"
    )
    rows = fetch_all(sql, params)
    if not rows:
        return None
    counts = sorted(_i(r["n"]) or 0 for r in rows)
    lo, hi, partners = counts[0], counts[-1], len(counts)
    if hi >= 15:
        body = (
            f"Not split by cruise line yet. Per-partner counts now run {lo} to {hi} "
            f"across {partners} named lines -- still too thin for the smallest, but "
            "the largest may already support a partner-level view."
        )
    else:
        body = (
            f"Not split by cruise line yet. Per-partner counts run {lo} to {hi} "
            f"across {partners} named lines -- too thin to show a partner."
        )
    return {"severity": "thin", "body": body}


def guest_mood(
    date_from: date | None = None,
    date_to: date | None = None,
) -> dict[str, Any]:
    """P-13, guest mood on arrival.

    Population: B. Every bot-raised ticket is scored, so unlike the other
    channels there is no coverage gap here -- ``scored`` and ``total`` are
    both returned so the panel can prove it. The cruise-line note is computed
    live by ``_cruise_line_thin_note`` -- see that function for why.
    """
    params: list[Any] = []
    counts_sql = (
        """
        SELECT COUNT(*)                                                      AS total,
               COUNT(*) FILTER (WHERE nullif(sentiment, '') IS NOT NULL)      AS scored,
               COUNT(*) FILTER (WHERE lower(coalesce(sentiment,'')) = ANY(%s)) AS unhappy
        FROM tickets
        WHERE is_bot_raised
        """
    )
    params.append(list(_UNHAPPY_SENTIMENTS))
    counts_sql += _range_clause("created_at", date_from, date_to, params)
    counts = fetch_one(counts_sql, params) or {}

    group_params: list[Any] = []
    group_sql = (
        """
        SELECT sentiment, COUNT(*) AS count
        FROM tickets
        WHERE is_bot_raised AND nullif(sentiment, '') IS NOT NULL
        """
        + _range_clause("created_at", date_from, date_to, group_params)
        + " GROUP BY sentiment ORDER BY count DESC, sentiment"
    )
    rows = fetch_all(group_sql, group_params)
    total = _i(counts.get("total")) or 0
    unhappy = _i(counts.get("unhappy")) or 0
    scored = _i(counts.get("scored")) or 0
    cruise_line_note = _cruise_line_thin_note(date_from, date_to)
    return {
        "scored": scored,
        "total": total,
        "unhappy": unhappy,
        "unhappy_pct": _pct(unhappy, total),
        "basis": (
            f"{scored} of {total} bot-raised tickets are sentiment-scored -- no "
            "coverage gap on this channel"
        ),
        "extra_notes": [cruise_line_note] if cruise_line_note else [],
        "items": [
            {
                "sentiment": row["sentiment"],
                "count": _i(row["count"]),
                "tone": _SENTIMENT_TONE.get((row["sentiment"] or "").lower(), "neutral"),
            }
            for row in rows
        ],
    }


# =========================================================================== #
# Products -- /api/products  (population B)
# =========================================================================== #


def inquiry_types(
    date_from: date | None = None,
    date_to: date | None = None,
) -> dict[str, Any]:
    """P-16, what guests come to us about. One flow per ticket.

    Population: B. ``unused_flows`` is the intake form's own catalogue minus
    what actually appeared -- a scope finding, not a demand finding: the bot
    only runs the returns and billing flows, so it can only report on them.
    """
    params: list[Any] = []
    sql = (
        """
        SELECT coalesce(nullif(inquiry_type, ''), 'No flow recorded') AS inquiry_type,
               COUNT(*) AS count
        FROM tickets
        WHERE is_bot_raised
        """
        + _range_clause("created_at", date_from, date_to, params)
        + " GROUP BY 1 ORDER BY 2 DESC, 1"
    )
    rows = fetch_all(sql, params)
    items = [
        {"inquiry_type": row["inquiry_type"], "count": _i(row["count"])} for row in rows
    ]
    total = sum(item["count"] or 0 for item in items)
    seen = {(item["inquiry_type"] or "").strip().lower() for item in items}
    unused = [flow for flow in FORM_FLOWS if flow.lower() not in seen]
    basis = (
        f"Bot-raised tickets only -- {total}. One flow per ticket. Flows are the "
        "Inquiry Type values from the One Spa World form."
    )
    return {"basis": basis, "total": total, "items": items, "unused_flows": unused}


def returns_breakdown(
    date_from: date | None = None,
    date_to: date | None = None,
) -> dict[str, Any]:
    """P-44, inside the returns flow: ordered how, sent back why?

    Population: B, restricted to return tickets. Every return carries exactly
    three tags -- the return itself, one order route, one reason -- so both
    breakdowns sum to the return total with nothing missing. Missing values are
    surfaced as their own label rather than dropped, so the sums stay honest.
    """
    where = " AND inquiry_type ILIKE %s"
    pattern = "%return%"

    total_params: list[Any] = [pattern]
    total_sql = (
        "SELECT COUNT(*) AS n FROM tickets WHERE is_bot_raised" + where
    )
    total_sql += _range_clause("created_at", date_from, date_to, total_params)
    total = _i(fetch_value(total_sql, total_params)) or 0

    def _breakdown(column: str, missing_label: str) -> list[dict[str, Any]]:
        if column not in {"order_route", "return_reason"}:  # pragma: no cover
            raise ValueError(f"unsupported breakdown column: {column!r}")
        params: list[Any] = [missing_label, pattern]
        sql = (
            f"""
            SELECT coalesce(nullif({column}, ''), %s) AS label, COUNT(*) AS count
            FROM tickets
            WHERE is_bot_raised
            """
            + where
        )
        sql += _range_clause("created_at", date_from, date_to, params)
        sql += " GROUP BY 1 ORDER BY 2 DESC, 1"
        return [
            {"label": row["label"], "count": _i(row["count"])}
            for row in fetch_all(sql, params)
        ]

    reasons = _breakdown("return_reason", "Other")
    extra_notes: list[dict[str, str]] = []

    # Which reason leads can change as more tickets load -- recomputed live so
    # the claim never names a reason the numbers next to it no longer support.
    named_reasons = [r for r in reasons if r["label"] != "Other"]
    if len(named_reasons) >= 2 and total:
        top, second = named_reasons[0], named_reasons[1]
        top_pct = round(100.0 * (top["count"] or 0) / total)
        extra_notes.append(
            {
                "severity": "critical",
                "body": (
                    f"{top['label']} is the single biggest reason a guest returns "
                    f"something -- {top['count']} of {total} ({top_pct}%), ahead of "
                    f"{second['label'].lower()} at {second['count']}."
                ),
            }
        )

    other = next((r for r in reasons if r["label"] == "Other"), None)
    if other and total and named_reasons:
        other_count = other["count"] or 0
        other_pct = round(100.0 * other_count / total)
        biggest_named = max(r["count"] or 0 for r in named_reasons)
        comparison = (
            "as large as the biggest named reason"
            if other_count >= biggest_named
            else "smaller than the biggest named reason, but still worth splitting out"
        )
        extra_notes.append(
            {
                "severity": "thin",
                "body": (
                    f"'Other' is {other_count} of {total} ({other_pct}%) -- {comparison} "
                    "before anyone reads a trend off this."
                ),
            }
        )

    return {
        "total": total,
        "order_route": _breakdown("order_route", "Not recorded"),
        "return_reason": reasons,
        "basis": (
            f"{total} return tickets · one order route and one reason each, so "
            "both breakdowns sum to the total with nothing missing"
        ),
        "extra_notes": extra_notes,
    }


# =========================================================================== #
# Customers -- /api/customers  (population B)
# =========================================================================== #


def repeat_guests(
    date_from: date | None = None,
    date_to: date | None = None,
) -> dict[str, Any]:
    """P-30 / P-48, guests who came back.

    Population: B. A guest counts as repeating either by raising two or more
    bot tickets or by Zendesk's own ``via.source.rel = follow_up`` link -- no
    name matching, so this is a floor: repeat contact arriving by email or
    phone is not counted, and the ticket a follow-up points back to is usually
    older than this page.
    """
    params: list[Any] = []
    sql = (
        """
        WITH scoped AS (
            SELECT requester_id, via_source_rel
            FROM tickets
            WHERE is_bot_raised AND requester_id IS NOT NULL
        """
        + _range_clause("created_at", date_from, date_to, params)
        + """
        ),
        per_guest AS (
            SELECT requester_id,
                   COUNT(*)                                         AS tickets,
                   bool_or(via_source_rel = 'follow_up')             AS chased
            FROM scoped
            GROUP BY requester_id
        )
        SELECT (SELECT COUNT(*) FROM per_guest)                                   AS guests,
               (SELECT COUNT(*) FROM per_guest WHERE tickets > 1 OR chased)        AS repeat_guests,
               (SELECT COUNT(*) FROM per_guest WHERE tickets > 1)                  AS raised_two_plus,
               (SELECT COUNT(*) FROM scoped WHERE via_source_rel = 'follow_up')    AS chasing_older,
               (SELECT coalesce(SUM(tickets), 0) FROM per_guest
                 WHERE tickets > 1 OR chased)                                      AS their_tickets
        """
    )
    row = fetch_one(sql, params) or {}
    guests = _i(row.get("guests")) or 0
    repeats = _i(row.get("repeat_guests")) or 0
    their_tickets = _i(row.get("their_tickets")) or 0

    # Which real guests these are -- requester_id only (pseudonymous, same
    # privacy stance as everywhere else), not a name -- so "9 repeat guests"
    # is a checkable list, not just a count.
    top_params: list[Any] = list(params)
    top_sql = (
        """
        WITH scoped AS (
            SELECT t.requester_id, t.ticket_id, t.via_source_rel, t.created_at, c.session_id
            FROM tickets t
            LEFT JOIN conversations c ON c.ticket_id = t.ticket_id
            WHERE t.is_bot_raised AND t.requester_id IS NOT NULL
        """
        + _range_clause("created_at", date_from, date_to, top_params)
        + """
        )
        SELECT requester_id,
               COUNT(*)                                          AS ticket_count,
               array_agg(ticket_id ORDER BY created_at)           AS ticket_ids,
               -- Aligned index-for-index with ticket_ids (same ORDER BY): a
               -- guest's Nth ticket links to a conversation exactly when
               -- session_ids[N] is not null. Most will be -- only tickets
               -- that carry a TicketID session tag have one at all.
               array_agg(session_id ORDER BY created_at)          AS session_ids,
               bool_or(via_source_rel = 'follow_up')              AS chased,
               MAX(created_at)                                    AS last_ticket_at
        FROM scoped
        GROUP BY requester_id
        HAVING COUNT(*) > 1 OR bool_or(via_source_rel = 'follow_up')
        ORDER BY COUNT(*) DESC, MAX(created_at) DESC
        LIMIT 10
        """
    )
    top_rows = fetch_all(top_sql, top_params)

    return {
        "guests": guests,
        "repeat_guests": repeats,
        "repeat_pct": _pct(repeats, guests),
        "their_tickets": their_tickets,
        "basis": (
            f"Bot-raised only -- {their_tickets} tickets from {repeats} repeat "
            f"guests, out of {guests} who used it. A floor, not a ceiling"
        ),
        "raised_two_plus": _i(row.get("raised_two_plus")) or 0,
        "chasing_older": _i(row.get("chasing_older")) or 0,
        "method": (
            "Identified from requester_id and Zendesk's own via.source.rel = "
            "follow_up link, so no name matching."
        ),
        "top_repeat_guests": [
            {
                "requester_id": str(r["requester_id"]),
                "ticket_count": _i(r["ticket_count"]),
                "ticket_ids": [str(t) for t in (r["ticket_ids"] or [])],
                "session_ids": [(str(s) if s else None) for s in (r["session_ids"] or [])],
                "chasing_older": bool(r["chased"]),
                "last_ticket_at": r["last_ticket_at"],
            }
            for r in top_rows
        ],
    }


# =========================================================================== #
# Conversations -- /api/conversations  (population A)
# =========================================================================== #


def list_conversations(
    bot_id: str | None = None,
    limit: int | None = DEFAULT_PAGE_LIMIT,
    offset: int | None = 0,
    channel: str | None = None,
    containment_type: str | None = None,
    q: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> dict[str, Any]:
    """The session list, newest first, with total-before-paging.

    Population: A -- the Kore.ai session page, which is capped and reports more
    available, so ``total`` is the number of rows *held*, never the number that
    exist. ``q`` searches the session id and the channel user id only; free-text
    transcript search is deliberately not offered here.
    """
    capped = _clamp_limit(limit)
    skip = _clamp_offset(offset)

    where = " WHERE 1 = 1"
    params: list[Any] = []
    where += _bot_clause("bot_id", bot_id, params)
    if channel:
        params.append(channel)
        where += " AND channel = %s"
    if containment_type:
        chosen = _require(
            containment_type, CONTAINMENT_TYPES, "containment_type", "self_service"
        )
        params.append(chosen)
        where += " AND containment_type = %s"
    if q:
        pattern = f"%{q.strip()}%"
        params.extend([pattern, pattern])
        where += " AND (session_id ILIKE %s OR channel_user_id ILIKE %s)"
    where += _range_clause("started_at", date_from, date_to, params)

    total = _i(fetch_value("SELECT COUNT(*) AS n FROM conversations" + where, params)) or 0

    page_params = list(params) + [capped, skip]
    rows = fetch_all(
        """
        SELECT session_id, bot_id, channel, channel_user_id, language, started_at,
               ended_at, duration_seconds, message_count, task_count,
               containment_type, session_status, ticket_id, inquiry_type, event_name
        FROM conversations
        """
        + where
        + " ORDER BY started_at DESC NULLS LAST, session_id LIMIT %s OFFSET %s",
        page_params,
    )
    items = [
        {
            **row,
            "duration_seconds": _i(row["duration_seconds"]),
            "message_count": _i(row["message_count"]),
            "task_count": _i(row["task_count"]),
        }
        for row in rows
    ]
    return {
        "items": items,
        "total": total,
        "limit": capped,
        "offset": skip,
        "basis": _population_basis("A"),
    }


def conversation_detail(session_id: str) -> dict[str, Any] | None:
    """One session, its ordered turns, and any traces that carry its id.

    Population: A for the session and its messages, T for the trace ids --
    which is the whole point of the join: the business record and the technical
    evidence are the same context. Returns None when the session is not held,
    so the router can answer 404.
    """
    conversation = fetch_one(
        """
        SELECT session_id, bot_id, channel, channel_user_id, language, started_at,
               ended_at, duration_seconds, message_count, task_count,
               containment_type, session_status, is_developer, ticket_id,
               inquiry_type, event_name, alt_text, source_file
        FROM conversations
        WHERE session_id = %s
        """,
        (session_id,),
    )
    if not conversation:
        return None

    messages = fetch_all(
        """
        SELECT message_id, turn_no, direction, body, component_type, task_name,
               intent, created_at, is_template
        FROM messages
        WHERE session_id = %s
        ORDER BY coalesce(turn_no, 2147483647), created_at, message_id
        """,
        (session_id,),
    )
    trace_rows = fetch_all(
        """
        SELECT trace_id
        FROM traces
        WHERE conversation_id = %s
        ORDER BY started_at, trace_id
        """,
        (session_id,),
    )
    return {
        "conversation": {
            **conversation,
            "duration_seconds": _i(conversation["duration_seconds"]),
            "message_count": _i(conversation["message_count"]),
            "task_count": _i(conversation["task_count"]),
        },
        "messages": [
            {
                "message_id": row["message_id"],
                "turn_no": _i(row["turn_no"]),
                "direction": row["direction"],
                "body": row["body"],
                "component_type": row["component_type"],
                "task_name": row["task_name"],
                "intent": row["intent"],
                "created_at": row["created_at"],
                "is_template": row["is_template"],
            }
            for row in messages
        ],
        "trace_ids": [row["trace_id"] for row in trace_rows],
        "basis": _population_basis("A"),
    }
