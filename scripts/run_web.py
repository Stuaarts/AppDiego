from __future__ import annotations

import asyncio
import logging
import os
import subprocess
import sys
import threading
import time
from datetime import timedelta

from sqlalchemy import select

from price_monitor.config import load_settings
from price_monitor.database import make_engine, make_session_factory
from price_monitor.models import ScrapeRun
from price_monitor.services.scrape_service import ScrapeAlreadyRunningError, scrape
from price_monitor.time import ensure_aware_utc, utc_now

LOGGER = logging.getLogger("price_monitor.scheduler")


def main() -> int:
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
    settings = load_settings()
    if settings.enable_internal_scheduler:
        thread = threading.Thread(target=_scheduler_loop, daemon=True)
        thread.start()
    port = os.getenv("PORT", "8501")
    return subprocess.call(
        [
            sys.executable,
            "-m",
            "streamlit",
            "run",
            "app.py",
            "--server.address=0.0.0.0",
            f"--server.port={port}",
            "--server.headless=true",
        ]
    )


def _scheduler_loop() -> None:
    settings = load_settings()
    engine = make_engine(settings)
    session_factory = make_session_factory(engine)
    interval = timedelta(hours=settings.internal_scrape_interval_hours)
    while True:
        try:
            if _scheduled_run_due(session_factory, interval):
                LOGGER.info("starting scheduled price collection")
                asyncio.run(
                    scrape(
                        session_factory,
                        settings,
                        trigger_source="scheduled_github",
                    )
                )
        except ScrapeAlreadyRunningError:
            LOGGER.info("scheduled price collection skipped because another run is active")
        except Exception:
            LOGGER.exception("scheduled price collection failed")
        time.sleep(min(300, max(60, int(interval.total_seconds() / 6))))


def _scheduled_run_due(session_factory, interval: timedelta) -> bool:
    cutoff = utc_now() - interval
    with session_factory() as session:
        latest = session.scalar(
            select(ScrapeRun)
            .where(ScrapeRun.trigger_source == "scheduled_github")
            .order_by(ScrapeRun.started_at.desc())
            .limit(1)
        )
        return latest is None or ensure_aware_utc(latest.started_at) < cutoff


if __name__ == "__main__":
    raise SystemExit(main())
