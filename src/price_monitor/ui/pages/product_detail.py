from __future__ import annotations

import streamlit as st
from sqlalchemy.orm import Session, sessionmaker

from price_monitor.config import Settings
from price_monitor.ui.components import page_header


def render(_session_factory: sessionmaker[Session], _settings: Settings) -> None:
    page_header("Detalhe do produto")
    st.info("Use a pagina Produtos para visualizar listagens e atualizar um produto especifico.")
