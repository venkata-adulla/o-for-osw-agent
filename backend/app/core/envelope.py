"""The provenance envelope.

No figure leaves this API without the population it came from. That is the single
most important property carried over from the business dashboard: a count that
looks like a period total, but is really one capped API page, misleads a
leadership audience in a way no amount of chart polish can undo.
"""
from __future__ import annotations

from typing import Any, Iterable

from app.core.db import fetch_all

# Short, human basis strings per population letter.
POPULATION_BASIS = {
    "A": "Kore.ai session page -- capped at 100 rows, more available",
    "B": "Zendesk bot-raised tickets only",
    "C": "Kore.ai extended session detail",
    "T": "OpenTelemetry signals from instrumented services",
}


def notes_for(panel_id: str) -> list[dict[str, str]]:
    rows = fetch_all(
        """
        SELECT severity, body
        FROM panel_notes
        WHERE panel_id = %s
        ORDER BY sort_order, id
        """,
        (panel_id,),
    )
    return [{"severity": r["severity"], "body": r["body"]} for r in rows]


def meta(
    panel_id: str,
    population: str,
    basis: str | None = None,
    extra_notes: Iterable[dict[str, str]] | None = None,
) -> dict[str, Any]:
    notes = notes_for(panel_id)
    if extra_notes:
        notes.extend(extra_notes)
    return {
        "panel_id": panel_id,
        "population": population,
        "basis": basis or POPULATION_BASIS.get(population, ""),
        "notes": notes,
    }


def envelope(payload: dict[str, Any], **meta_kwargs: Any) -> dict[str, Any]:
    """Merge a payload with its provenance meta block."""
    return {**payload, "meta": meta(**meta_kwargs)}
