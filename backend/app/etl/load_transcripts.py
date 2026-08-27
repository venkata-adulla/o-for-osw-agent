"""Transcript loader -- the chat text itself.

Each date folder holds one CSV per conversation with the columns
``Bot Name,User,Channel,Language,Bot Message,User Message,Timestamp,Email Subject``.
One row can carry a bot turn, a guest turn, or both.

Three decisions worth spelling out:

*   **De-duplication.** Every date folder exists twice on disk -- a sibling with
    a ``(1)`` or `` 1`` suffix holding byte-identical files. Loading both would
    double the conversation volume, so ``paths.transcript_files()`` keys on file
    name and 158 files collapse to 79 conversations.
*   **The ticket number is the second join key.** The bot's closing message says
    ``Your ticket number is *340597*``. That is the only place a transcript and a
    Zendesk ticket meet, so it is extracted with a regex and stored on
    ``conversations.ticket_id``.
*   **PII stays tokenised.** Values arrive already masked as
    ``#*#EMAIL-ms9h4b0q#*#`` / ``#*#PHONE-...#*#`` / ``#*#SENSITIVE-...#*#``.
    They are stored verbatim. No attempt is made to resolve them, and none
    should ever be added.
"""
from __future__ import annotations

import csv
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator

from app.core.db import get_pool
from app.etl import StageResult, clean, log, run_stage, slug
from app.etl.load_kore import _CONVERSATION_UPSERT, _ensure_bots
from app.etl.paths import session_id_from_transcript, transcript_files

# "Sat Aug 01 2026 02:15:07 AM IST" -- not ISO, and the zone is an abbreviation.
_TIMESTAMP_RE = re.compile(
    r"^(?P<dow>[A-Za-z]{3})\s+(?P<mon>[A-Za-z]{3})\s+(?P<day>\d{1,2})\s+(?P<year>\d{4})\s+"
    r"(?P<time>\d{1,2}:\d{2}:\d{2})\s*(?P<ampm>[AP]M)?\s*(?P<zone>[A-Z]{2,4})?$"
)

# Fixed offsets, chosen for the August window the transcripts cover (so ET is
# EDT). Abbreviations are ambiguous by nature; a fixed table keeps the loader
# deterministic instead of guessing a political timezone per row.
_ZONE_OFFSETS: dict[str, timedelta] = {
    "IST": timedelta(hours=5, minutes=30),
    "UTC": timedelta(0),
    "GMT": timedelta(0),
    "ET": timedelta(hours=-4),
    "EDT": timedelta(hours=-4),
    "EST": timedelta(hours=-5),
    "CT": timedelta(hours=-5),
    "CDT": timedelta(hours=-5),
    "CST": timedelta(hours=-6),
    "MT": timedelta(hours=-6),
    "MDT": timedelta(hours=-6),
    "MST": timedelta(hours=-7),
    "PT": timedelta(hours=-7),
    "PDT": timedelta(hours=-7),
    "PST": timedelta(hours=-8),
}

# "Your ticket number is *340597*" (asterisks are the bot's bold markers).
TICKET_NUMBER_RE = re.compile(r"ticket\s*(?:number|no\.?|#)?\s*is\s*\*?(\d{4,12})\*?", re.IGNORECASE)

# Kept so a reader can see the tokens are recognised and deliberately preserved.
PII_TOKEN_RE = re.compile(r"#\*#(SENSITIVE|EMAIL|PHONE|NAME|ADDRESS|CARD)-[A-Za-z0-9]+#\*#")

BOT_NAME_TO_ID = {"marina": "marina", "serena": "serena", "aiva": "aiva"}

_CHANNEL_MAP = {
    "web/mobile client": "web",
    "web client": "web",
    "webclient": "web",
    "rtm": "rtm",
}


def parse_transcript_timestamp(value: Any) -> datetime | None:
    text = clean(value)
    if not text:
        return None
    match = _TIMESTAMP_RE.match(text)
    if not match:
        return None
    time_fmt = "%I:%M:%S" if match.group("ampm") else "%H:%M:%S"
    stamp_text = f"{match.group('mon')} {match.group('day')} {match.group('year')} {match.group('time')}"
    if match.group("ampm"):
        stamp_text = f"{stamp_text} {match.group('ampm')}"
        fmt = f"%b %d %Y {time_fmt} %p"
    else:
        fmt = f"%b %d %Y {time_fmt}"
    try:
        naive = datetime.strptime(stamp_text, fmt)
    except ValueError:
        return None
    offset = _ZONE_OFFSETS.get((match.group("zone") or "UTC").upper(), timedelta(0))
    return naive.replace(tzinfo=timezone(offset))


def _bot_id(bot_name: Any) -> str:
    text = (clean(bot_name) or "marina").lower()
    return BOT_NAME_TO_ID.get(text, slug(text, 64))


def _channel(value: Any) -> str | None:
    text = clean(value)
    if not text:
        return None
    return _CHANNEL_MAP.get(text.lower(), text.lower())


def _read_rows(path: Path) -> Iterator[dict[str, str]]:
    """csv.DictReader handles the embedded newlines inside quoted bot messages."""
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        yield from csv.DictReader(handle)


def _parse_file(path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]] | None:
    session_id = session_id_from_transcript(path)
    if not session_id:
        return None

    turns: list[dict[str, Any]] = []
    bot_name: str | None = None
    channel: str | None = None
    language: str | None = None
    channel_user_id: str | None = None
    email_subject: str | None = None
    ticket_id: int | None = None
    pii_tokens = 0

    try:
        rows = list(_read_rows(path))
    except (OSError, csv.Error, UnicodeDecodeError) as exc:
        log.warning("could not read transcript %s: %s", path, exc)
        return None

    for index, row in enumerate(rows, start=1):
        bot_name = bot_name or clean(row.get("Bot Name"))
        channel = channel or _channel(row.get("Channel"))
        language = language or clean(row.get("Language"))
        channel_user_id = channel_user_id or clean(row.get("User"))
        email_subject = email_subject or clean(row.get("Email Subject"))
        stamp = parse_transcript_timestamp(row.get("Timestamp"))

        bot_message = (row.get("Bot Message") or "").strip()
        user_message = (row.get("User Message") or "").strip()

        if bot_message:
            pii_tokens += len(PII_TOKEN_RE.findall(bot_message))
            match = TICKET_NUMBER_RE.search(bot_message)
            if match and ticket_id is None:
                ticket_id = int(match.group(1))
            turns.append(
                {
                    "message_id": f"tr-{session_id}-{index:04d}-o",
                    "direction": "outgoing",
                    "body": bot_message,
                    "created_at": stamp,
                    "_seq": (index, 0),
                }
            )
        if user_message:
            pii_tokens += len(PII_TOKEN_RE.findall(user_message))
            turns.append(
                {
                    "message_id": f"tr-{session_id}-{index:04d}-i",
                    "direction": "incoming",
                    "body": user_message,
                    "created_at": stamp,
                    "_seq": (index, 1),
                }
            )

    if not turns:
        return None

    stamps = [turn["created_at"] for turn in turns if turn["created_at"]]
    started_at = min(stamps) if stamps else None
    ended_at = max(stamps) if stamps else None
    duration = None
    if started_at and ended_at:
        duration = max(int(round((ended_at - started_at).total_seconds())), 0)

    bot_id = _bot_id(bot_name)
    conversation = {
        "session_id": session_id,
        "bot_id": bot_id,
        "channel": channel,
        "channel_user_id": channel_user_id,
        "language": language,
        "started_at": started_at,
        "ended_at": ended_at,
        "duration_seconds": duration,
        "message_count": len(turns),
        "task_count": None,
        "containment_type": None,
        "session_status": None,
        "is_developer": False,
        "ticket_id": ticket_id,
        "inquiry_type": None,
        "event_name": None,
        "alt_text": [],
        "source_file": f"{path.parent.name}/{path.name}",
        "raw": json.dumps(
            {
                "source_file": f"{path.parent.name}/{path.name}",
                "email_subject": email_subject,
                "csv_rows": len(rows),
                "pii_tokens_preserved": pii_tokens,
                "ticket_number_from_closing_message": ticket_id,
            }
        ),
    }

    turns.sort(key=lambda turn: turn["_seq"])
    message_rows = [
        {
            "message_id": turn["message_id"],
            "session_id": session_id,
            "bot_id": bot_id,
            "turn_no": turn_no,
            "direction": turn["direction"],
            "body": turn["body"],
            "component_type": "text",
            "task_name": None,
            "intent": None,
            "created_at": turn["created_at"],
            "is_template": False,
            "tags": json.dumps({"source": "transcript"}),
        }
        for turn_no, turn in enumerate(turns, start=1)
    ]
    return conversation, message_rows


def load(result: StageResult) -> None:
    files = transcript_files()
    if not files:
        result.warn("no transcript CSVs found under the data root")
        return

    conversations: list[dict[str, Any]] = []
    messages: list[dict[str, Any]] = []
    with_ticket = 0

    for path in files:
        parsed = _parse_file(path)
        if parsed is None:
            result.warn(f"unparseable transcript skipped: {path.name}")
            continue
        conversation, turns = parsed
        conversations.append(conversation)
        messages.extend(turns)
        if conversation["ticket_id"]:
            with_ticket += 1

    if not conversations:
        result.warn("every transcript failed to parse; nothing loaded")
        return

    # Identical bot copy across the whole transcript corpus is template text.
    from collections import Counter

    body_counts = Counter(row["body"] for row in messages if row["direction"] == "outgoing")
    for row in messages:
        row["is_template"] = row["direction"] == "outgoing" and body_counts[row["body"]] >= 3

    with get_pool().connection() as conn:
        with conn.cursor() as cur:
            _ensure_bots(cur, (row["bot_id"] for row in conversations), {})
            # COALESCE in the shared upsert means a transcript never overwrites
            # the richer Kore.ai session record if the two ever meet.
            cur.executemany(_CONVERSATION_UPSERT, conversations)
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
                    created_at = EXCLUDED.created_at,
                    is_template = EXCLUDED.is_template,
                    tags = EXCLUDED.tags
                """,
                messages,
            )
        conn.commit()

    result.add("conversations", len(conversations))
    result.add("messages", len(messages))
    result.detail = (
        f"{len(files)} unique CSVs (de-duplicated from the mirrored date folders), "
        f"{len(conversations)} conversations, {with_ticket} carry a ticket number"
    )


def run() -> StageResult:
    with run_stage("load_transcripts", "Transcript CSVs -> conversations, messages") as result:
        load(result)
    return result
