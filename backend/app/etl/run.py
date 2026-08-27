"""ETL CLI entry point.

    python -m app.etl.run [--only STAGE] [--reset] [--continue-on-error]

Default (no ``--only``) runs the whole pipeline in the one order that makes
every foreign key line up:

    seed_business -> seed_telemetry -> zendesk -> kore -> transcripts -> derive_spans

``seed_business``/``seed_telemetry`` are the literal reference-parity seeds and
have no dependency on the raw extracts, so they go first. ``zendesk``,
``kore`` and ``transcripts`` are the three raw-extract loaders: they are
independent of each other (each keys on its own natural id and only touches
its own tables plus the shared ``conversations``/``bots`` tables via
``ON CONFLICT``), so one of them failing must not stop the other two from
being attempted. ``derive_spans`` runs last because it reads real rows
``kore`` lands in ``conversations`` and needs the ``services`` rows
``seed_telemetry`` seeds for its spans' foreign key -- it only runs if
``kore`` actually succeeded *this run*.

Failure handling: every stage's own ``run_stage`` context manager already
writes a ``failed`` row to ``etl_runs`` and re-raises. This CLI lets that
exception end the run (non-zero exit) unless ``--continue-on-error`` is
passed -- except for the zendesk/kore/transcripts trio, where all three are
always attempted regardless of one failing; the run still ends non-zero
afterwards if any of them failed and ``--continue-on-error`` was not given.
"""
from __future__ import annotations

import argparse
import logging
import sys
from typing import Callable

from app.core.db import get_pool
from app.etl import StageResult, log
from app.etl import derive_spans, load_kore, load_transcripts, load_zendesk, seed_business, seed_telemetry

STAGE_FUNCS: dict[str, Callable[[], StageResult]] = {
    "seed_business": seed_business.run,
    "seed_telemetry": seed_telemetry.run,
    "zendesk": load_zendesk.run,
    "kore": load_kore.run,
    "transcripts": load_transcripts.run,
    "derive_spans": derive_spans.run,
}

# Every table this package writes to, i.e. everything in the osw schema except
# `etl_runs` (the audit log itself -- a --reset should not erase the history of
# resets) and the two views (`bot_tickets`, `journey_funnel`, which TRUNCATE
# cannot target anyway). Listed explicitly per-table rather than discovered, so
# a schema change is a visible diff here rather than a silent scope change.
_RESETTABLE_TABLES: tuple[str, ...] = (
    "populations", "population_figures", "panel_notes", "coverage_metrics",
    "bots", "conversations", "messages", "nlu_events",
    "tickets", "ticket_tags", "backend_failures",
    "hand_review_days", "hand_review_sessions", "journey_stages", "quit_reasons",
    "enrichment_outcomes", "enrichment_failures", "duplicate_pairs", "automation_gaps",
    "daily_activity", "kpi_snapshots",
    "services", "telemetry_conversations", "traces", "spans", "span_attributes",
    "log_records",
    "metric_instruments", "metric_summaries", "metric_histogram_buckets",
    "metric_outcomes", "metric_series",
    "baggage_fields", "baggage_blocked_fields", "baggage_requests",
    "baggage_hops", "baggage_hop_fields",
    "profiles", "profile_frames", "profile_hot_functions",
    "topology_hops", "signal_coverage", "incidents",
    "otel_requirements", "otel_checklist", "collector_path_steps",
    "diagnose_steps", "operating_model",
    "otlp_ingest",
)


def reset_data_tables() -> None:
    """TRUNCATE every data table -- never DROP, never touch a table definition."""
    table_list = ", ".join(_RESETTABLE_TABLES)
    log.warning("[run] --reset: truncating %d tables", len(_RESETTABLE_TABLES))
    with get_pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(f"TRUNCATE TABLE {table_list} RESTART IDENTITY CASCADE")
        conn.commit()


def _run_stage(name: str, fn: Callable[[], StageResult]) -> tuple[StageResult | None, Exception | None]:
    try:
        result = fn()
    except Exception as exc:  # noqa: BLE001 - reported to the caller, not swallowed
        print(f"[{name}] FAILED -- {type(exc).__name__}: {exc}")
        log.error("[run] stage '%s' failed: %s", name, exc)
        return None, exc
    print(f"[{name}] OK -- {result.summary()}")
    return result, None


def run_only(stage: str, continue_on_error: bool) -> int:
    result, error = _run_stage(stage, STAGE_FUNCS[stage])
    if error is not None and not continue_on_error:
        raise error
    return 0 if error is None else 1


def run_all(continue_on_error: bool) -> int:
    failed_stages: list[str] = []
    total_rows = 0

    for name in ("seed_business", "seed_telemetry"):
        result, error = _run_stage(name, STAGE_FUNCS[name])
        if error is not None:
            failed_stages.append(name)
            if not continue_on_error:
                raise error
        else:
            total_rows += result.rows  # type: ignore[union-attr]

    # The raw-extract trio: independent of each other, so every one of them is
    # attempted even if an earlier one in the trio failed. Exceptions are
    # collected, not raised here, so all three get their chance to run.
    kore_ok = False
    for name in ("zendesk", "kore", "transcripts"):
        result, error = _run_stage(name, STAGE_FUNCS[name])
        if error is not None:
            failed_stages.append(name)
        else:
            total_rows += result.rows  # type: ignore[union-attr]
            if name == "kore":
                kore_ok = True

    if kore_ok:
        result, error = _run_stage("derive_spans", STAGE_FUNCS["derive_spans"])
        if error is not None:
            failed_stages.append("derive_spans")
            if not continue_on_error:
                raise error
        else:
            total_rows += result.rows  # type: ignore[union-attr]
    else:
        print("[derive_spans] SKIPPED -- load_kore did not succeed this run")
        log.warning("[run] derive_spans skipped: load_kore did not succeed this run")

    print(f"TOTAL rows loaded: {total_rows}")
    if failed_stages:
        print(f"FAILED stages: {', '.join(failed_stages)}")
        if not continue_on_error:
            raise RuntimeError(f"ETL run had failing stage(s): {', '.join(failed_stages)}")
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m app.etl.run",
        description="Load/seed the osw schema: reference-parity seeds plus the real Kore.ai/Zendesk/transcript extracts.",
    )
    parser.add_argument(
        "--only",
        choices=sorted(STAGE_FUNCS),
        default=None,
        help="Run exactly one stage instead of the full pipeline.",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="TRUNCATE every osw data table (not etl_runs, not the schema/table definitions) before loading.",
    )
    parser.add_argument(
        "--continue-on-error",
        action="store_true",
        help="Log a failing stage and keep going instead of exiting non-zero.",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    if args.reset:
        reset_data_tables()

    try:
        if args.only:
            return run_only(args.only, args.continue_on_error)
        return run_all(args.continue_on_error)
    except Exception as exc:  # noqa: BLE001 - final backstop so main() always returns an int
        log.exception("[run] aborting: %s", exc)
        print(f"ETL run aborted: {type(exc).__name__}: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
