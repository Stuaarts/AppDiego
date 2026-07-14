from __future__ import annotations

import asyncio

import plotly.express as px
import streamlit as st
from sqlalchemy.orm import Session, sessionmaker

from price_monitor.config import Settings
from price_monitor.services.dashboard_service import current_snapshot_dataframe, history_dataframe
from price_monitor.services.export_service import dataframe_to_csv_bytes
from price_monitor.services.scrape_service import scrape
from price_monitor.ui.components import page_header


def render(session_factory: sessionmaker[Session], settings: Settings) -> None:
    page_header("Visao geral", "Comparacao atual, alertas de falha e historico recente.")
    col_a, col_b = st.columns([1, 3])
    with col_a:
        if st.button("Atualizar precos", type="primary", use_container_width=True):
            with st.spinner("Coletando precos..."):
                result = asyncio.run(
                    scrape(session_factory, settings, trigger_source="manual_dashboard")
                )
            st.success(
                f"Execucao {result.run_id}: {result.successful} sucesso(s), "
                f"{result.failed} falha(s)."
            )
    with session_factory() as session:
        snapshot = current_snapshot_dataframe(session, settings.stale_after_hours)
        history = history_dataframe(session)

    metric_cols = st.columns(4)
    metric_cols[0].metric("Produtos", len(snapshot))
    valid_prices = int((snapshot.get("Menor preco").notna()).sum()) if not snapshot.empty else 0
    failures = int(snapshot.get("Falhas", []).sum()) if not snapshot.empty else 0
    metric_cols[1].metric("Com preco valido", valid_prices)
    metric_cols[2].metric("Falhas", failures)
    metric_cols[3].metric(
        "Desatualizadas", int(snapshot.get("Desatualizadas", []).sum()) if not snapshot.empty else 0
    )

    st.subheader("Comparacao atual")
    if snapshot.empty:
        st.info("Nenhum produto cadastrado ainda.")
    else:
        st.dataframe(snapshot, use_container_width=True, hide_index=True)
        st.download_button(
            "Exportar comparacao CSV",
            data=dataframe_to_csv_bytes(snapshot),
            file_name="comparacao_atual.csv",
            mime="text/csv",
        )

    st.subheader("Historico de precos")
    if history.empty or "Preco" not in history:
        st.info("Nenhuma observacao registrada.")
        return
    chart_data = history[history["Sucesso"] & history["Preco"].notna()].copy()
    if chart_data.empty:
        st.info("Ainda nao ha observacoes de preco bem-sucedidas.")
        return
    fig = px.line(
        chart_data,
        x="Data",
        y="Preco",
        color="Loja",
        line_group="Produto",
        hover_data=["Produto", "Disponibilidade"],
    )
    st.plotly_chart(fig, use_container_width=True)
