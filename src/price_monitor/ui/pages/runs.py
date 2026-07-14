from __future__ import annotations

import pandas as pd
import streamlit as st
from sqlalchemy.orm import Session, sessionmaker

from price_monitor.config import Settings
from price_monitor.repositories.runs import latest_runs
from price_monitor.ui.components import page_header
from price_monitor.ui.formatting import local_datetime


def render(session_factory: sessionmaker[Session], settings: Settings) -> None:
    page_header("Execucoes", "Historico de coletas manuais e agendadas.")
    with session_factory() as session:
        runs = latest_runs(session, limit=50)
    if not runs:
        st.info("Nenhuma execucao registrada.")
        return
    rows = [
        {
            "ID": run.id,
            "Inicio": local_datetime(run.started_at, settings.display_timezone),
            "Fim": local_datetime(run.finished_at, settings.display_timezone),
            "Origem": run.trigger_source,
            "Status": run.status,
            "Total": run.total_listings,
            "Sucessos": run.successful_listings,
            "Falhas": run.failed_listings,
            "Duracao ms": run.duration_ms,
        }
        for run in runs
    ]
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
