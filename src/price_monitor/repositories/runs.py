from __future__ import annotations

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from price_monitor.models import ScrapeRun


def latest_runs(session: Session, limit: int = 20) -> list[ScrapeRun]:
    return list(
        session.scalars(select(ScrapeRun).order_by(desc(ScrapeRun.started_at)).limit(limit))
    )
