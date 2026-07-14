from __future__ import annotations

import pandas as pd
import streamlit as st
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from price_monitor.config import Settings
from price_monitor.models import Store
from price_monitor.repositories.stores import create_store
from price_monitor.scraping.registry import ADAPTERS
from price_monitor.ui.components import page_header


def render(session_factory: sessionmaker[Session], settings: Settings) -> None:
    page_header("Lojas", "Configure lojas, dominios, adaptadores e comportamento de coleta.")
    with st.expander("Nova loja", expanded=False):
        with st.form("store_form", clear_on_submit=True):
            col1, col2 = st.columns(2)
            name = col1.text_input("Nome")
            domain = col2.text_input("Dominio ou URL")
            col3, col4, col5 = st.columns(3)
            default_currency = col3.text_input("Moeda padrao", value=settings.default_currency)
            delay = col4.number_input("Atraso por dominio (s)", min_value=0, max_value=120, value=2)
            adapter_key = col5.selectbox("Adaptador", options=sorted(ADAPTERS))
            requires_browser = st.checkbox("Requer navegador")
            submitted = st.form_submit_button("Salvar loja")
        if submitted:
            try:
                with session_factory() as session:
                    create_store(
                        session,
                        name=name,
                        domain=domain,
                        requires_browser=requires_browser,
                        request_delay_seconds=int(delay),
                        default_currency=default_currency,
                        adapter_key=adapter_key,
                    )
                    session.commit()
                st.success("Loja criada.")
                st.rerun()
            except Exception as exc:
                st.error(str(exc))

    with session_factory() as session:
        stores = session.scalars(select(Store).order_by(Store.name)).all()
    if not stores:
        st.info("Nenhuma loja cadastrada.")
        return
    rows = [
        {
            "ID": store.id,
            "Nome": store.name,
            "Dominio": store.domain,
            "Ativa": store.active,
            "Navegador": store.requires_browser,
            "Atraso": store.request_delay_seconds,
            "Moeda": store.default_currency,
            "Adaptador": store.adapter_key,
        }
        for store in stores
    ]
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
