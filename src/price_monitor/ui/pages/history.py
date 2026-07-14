from __future__ import annotations

import plotly.express as px
import streamlit as st
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from price_monitor.config import Settings
from price_monitor.models import Product
from price_monitor.services.dashboard_service import history_dataframe
from price_monitor.services.export_service import dataframe_to_csv_bytes
from price_monitor.ui.components import page_header


def render(session_factory: sessionmaker[Session], _settings: Settings) -> None:
    page_header("Historico", "Observacoes salvas para auditoria e analise de tendencia.")
    with session_factory() as session:
        products = session.scalars(select(Product).order_by(Product.name)).all()
        product_options = [None, *[product.id for product in products]]
        selected = st.selectbox(
            "Produto",
            product_options,
            format_func=lambda value: (
                "Todos"
                if value is None
                else next(product.name for product in products if product.id == value)
            ),
        )
        history = history_dataframe(session, product_id=selected)
    if history.empty:
        st.info("Nenhuma observacao registrada.")
        return
    chart_data = history[history["Sucesso"] & history["Preco"].notna()].copy()
    if not chart_data.empty:
        fig = px.line(
            chart_data,
            x="Data",
            y="Preco",
            color="Loja",
            line_group="Produto",
            hover_data=["Produto", "Disponibilidade"],
        )
        st.plotly_chart(fig, use_container_width=True)
    st.dataframe(history, use_container_width=True, hide_index=True)
    st.download_button(
        "Exportar historico CSV",
        data=dataframe_to_csv_bytes(history),
        file_name="historico_precos.csv",
        mime="text/csv",
    )
