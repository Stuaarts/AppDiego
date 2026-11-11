from __future__ import annotations

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
        session_factory = _session_factory(settings)
    except Exception as exc:
        st.error("Falha ao iniciar a aplicacao.")
        st.code(str(exc))
        return

    if not require_auth(settings):
        return

    st.sidebar.title(TEXT["app_title"])
    render_logout(settings)
    page = st.sidebar.radio(
        "Navegacao",
        [
            TEXT["search"],
            TEXT["import"],
            TEXT["dashboard"],
            TEXT["products"],
            TEXT["stores"],
            TEXT["history"],
            TEXT["runs"],
            TEXT["settings"],
        ],
    )

    if page == TEXT["search"]:
        search.render()
    elif page == TEXT["import"]:
        import_report.render()
    elif page == TEXT["dashboard"]:
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
