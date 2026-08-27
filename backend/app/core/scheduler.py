"""In-process ETL scheduler.

`/api/meta/freshness` has always computed "next run" as last success plus
PIPELINE_CRON's cadence (see `business._cadence_minutes`), but nothing ever
executed on that cadence -- the ETL only ran when a human triggered it by
hand, so the freshness banner quietly asserted a schedule nobody was
keeping. This loop is what makes that assertion true: it runs the full
pipeline on the same cadence the freshness API already advertises, in
process, so it needs no extra container, cron daemon or Docker socket
access.

Set ETL_SCHEDULER_ENABLED=false to turn it off, e.g. for a one-off manual
run where an automatic pass landing mid-way through would be unwelcome.
"""
from __future__ import annotations

import asyncio
import logging
import os

from app.etl.run import run_all
from app.services.business import _cadence_minutes

log = logging.getLogger("osw.scheduler")


def enabled() -> bool:
    return (os.environ.get("ETL_SCHEDULER_ENABLED") or "true").strip().lower() not in (
        "false",
        "0",
        "no",
        "off",
    )


async def etl_loop() -> None:
    """Run the pipeline immediately, then again every `_cadence_minutes()`.

    A failing run is logged and swallowed, never raised -- the next
    scheduled run is exactly how the pipeline is meant to recover, so one
    bad pass must not take the loop (or the process) down with it.
    Cancellation (on app shutdown) is let through so the task actually ends.
    """
    while True:
        try:
            log.info("[scheduler] starting scheduled ETL run")
            code = await asyncio.to_thread(run_all, True)
            log.info("[scheduler] ETL run finished, exit code %d", code)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - one bad run must not kill the loop
            log.exception("[scheduler] ETL run raised unexpectedly")

        await asyncio.sleep(max(60, _cadence_minutes() * 60))
