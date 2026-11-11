from __future__ import annotations

import os

import streamlit as st
from sqlalchemy.orm import Session, sessionmaker

from price_monitor.config import Settings, load_settings
from price_monitor.database import check_database, make_engine, make_session_factory
from price_monitor.ui.auth import render_logout, require_auth
from price_monitor.ui.components import inject_style
from price_monitor.ui.i18n import TEXT
from price_monitor.ui.pages import dashboard, history, import_report, products, runs, search, stores
from price_monitor.ui.pages import settings as settings_page


@st.cache_resource
def _settings() -> Settings:
    return load_settings()


@st.cache_resource
def _session_factory(settings: Settings) -> sessionmaker[Session]:
    engine = make_engine(settings)
    check_database(engine)
    return make_session_factory(engine)


def main() -> None:
    st.set_page_config(page_title=TEXT["app_title"], page_icon="R$", layout="wide")
    inject_style()
    try:
        settings = _settings()
    except ValueError:
        st.error("Falha ao iniciar a aplicacao.")
        return

    if not require_auth(settings):
        return

    st.sidebar.title(TEXT["app_title"])
    render_logout(settings)
    options = [TEXT["search"], TEXT["import"]]
    if os.getenv("PRICE_MONITOR_DATABASE_READY") == "0":
        st.sidebar.warning("Banco de dados indisponível. Busca e relatórios estão disponíveis.")
    else:
        options.extend(
            TEXT[key] for key in ("dashboard", "products", "stores", "history", "runs", "settings")
        )
    page = st.sidebar.radio(
        "Navegacao",
        options,
    )

    if page == TEXT["search"]:
        search.render()
        return
    if page == TEXT["import"]:
        import_report.render()
        return
    try:
        session_factory = _session_factory(settings)
    except Exception:
        st.error("Banco de dados indisponível.")
        return

    if page == TEXT["dashboard"]:
        dashboard.render(session_factory, settings)
    elif page == TEXT["products"]:
        products.render(session_factory, settings)
    elif page == TEXT["stores"]:
        stores.render(session_factory, settings)
    elif page == TEXT["history"]:
        history.render(session_factory, settings)
    elif page == TEXT["runs"]:
        runs.render(session_factory, settings)
    else:
        settings_page.render(session_factory, settings)
