from __future__ import annotations

import pandas as pd
import streamlit as st
from sqlalchemy.orm import Session, sessionmaker

from price_monitor.config import Settings, redact_database_url
from price_monitor.ui.components import page_header


def render(_session_factory: sessionmaker[Session], settings: Settings) -> None:
    page_header("Configuracoes", "Valores efetivos sem revelar segredos.")
    rows = [
        ("Ambiente", settings.app_env),
        ("Banco", redact_database_url(settings.database_url)),
        ("Schema", settings.database_schema or "padrao"),
        ("Autenticacao desativada", settings.auth_disabled),
        ("Moeda padrao", settings.default_currency),
        ("Timeout HTTP", settings.request_timeout_seconds),
        ("Tentativas", settings.max_retries),
        ("Concorrencia global", settings.global_scrape_concurrency),
        ("Concorrencia por dominio", settings.domain_scrape_concurrency),
        ("Concorrencia navegador", settings.browser_concurrency),
        ("Limite resposta bytes", settings.max_response_bytes),
        ("Preco stale apos horas", settings.stale_after_hours),
        ("Timezone exibicao", settings.display_timezone),
        ("Playwright habilitado", settings.playwright_enabled),
    ]
    st.dataframe(
        pd.DataFrame(rows, columns=["Chave", "Valor"]), use_container_width=True, hide_index=True
    )
    st.info(
        "Em producao, configure DATABASE_URL e APP_PASSWORD_HASH no Render. "
        "Gere o hash com: python -m price_monitor.cli hash-password sua-senha"
    )
