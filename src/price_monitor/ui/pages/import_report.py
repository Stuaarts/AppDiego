from __future__ import annotations

from hashlib import sha256

import streamlit as st

from price_monitor.services.price_report import (
    MAX_SEARCHES,
    import_prices,
    lookup_prices,
    normalize_header,
    read_import,
    report_to_xlsx,
)
from price_monitor.ui.i18n import TEXT
from price_monitor.ui.pages.search import lookup

PRODUCT_HEADERS = ("nome do produto", "produto", "product name", "product", "nome", "name")
PRICE_HEADERS = ("preco", "preco atual", "valor", "price", "current price")
SELLER_HEADERS = ("vendedor", "seller", "seller name", "loja", "store")
QUERY_HEADERS = ("ean", "gtin", "upc", "codigo de barras", "barcode", "sku", *PRODUCT_HEADERS)
MIME_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def render() -> None:
    st.title(TEXT["import"])
    uploaded = st.file_uploader("Base de produtos ou ofertas", type=["csv", "xlsx"])
    st.caption("CSV ou primeira aba do Excel, com cabeçalhos na primeira linha. Até 5 MB.")
    if uploaded is None:
        st.session_state.pop("price_import_table", None)
        st.session_state.pop("price_import_report", None)
        return

    data = uploaded.getvalue()
    is_excel = uploaded.name.lower().endswith(".xlsx")
    file_key = (sha256(data).hexdigest(), is_excel)
    cached = st.session_state.get("price_import_table")
    if cached is None or cached[0] != file_key:
        st.session_state.pop("price_import_report", None)
        try:
            cached = (file_key, read_import(data, is_excel=is_excel))
        except ValueError as exc:
            st.error(str(exc))
            return
        st.session_state["price_import_table"] = cached
    table = cached[1]
    headers = table.headers
    price_default = _find_column(headers, PRICE_HEADERS)
    search_mode = st.radio(
        "Origem dos preços",
        [False, True],
        index=int(price_default is None),
        format_func=lambda search: "Buscar nas lojas" if search else "Usar preços do arquivo",
        key=f"price_import_mode_{file_key[0]}",
        horizontal=True,
    )
    if search_mode:
        st.caption(f"Até {MAX_SEARCHES} consultas distintas por arquivo.")
        columns = (_column("Nome, SKU ou EAN", headers, QUERY_HEADERS),)
    else:
        columns = (
            _column("Nome do produto", headers, PRODUCT_HEADERS),
            _column("Preço em reais", headers, PRICE_HEADERS),
            _column("Vendedor", headers, SELLER_HEADERS),
        )

    ready = None not in columns and len(set(columns)) == len(columns)
    if not ready:
        st.info("Selecione uma coluna diferente para cada campo.")
    signature = (file_key, search_mode, columns)
    if st.button("Gerar relatório", type="primary", disabled=not ready):
        st.session_state.pop("price_import_report", None)
        selected = tuple(column for column in columns if column is not None)
        try:
            with st.spinner("Gerando relatório..."):
                if search_mode:
                    report = lookup_prices(table, selected[0], lookup)
                else:
                    product, price, seller = selected
                    report = import_prices(table, product=product, price=price, seller=seller)
                st.session_state["price_import_report"] = (
                    signature,
                    len(report.rows),
                    len(report.issues),
                    report_to_xlsx(report),
                )
        except ValueError as exc:
            st.error(str(exc))

    saved = st.session_state.get("price_import_report")
    if saved is not None and saved[0] == signature:
        _, rows, issues, workbook = saved
        st.write(f"{rows} ofertas no relatório.")
        if issues:
            st.warning(f"{issues} ocorrências na aba Pendências.")
        st.download_button(
            "Baixar Excel",
            data=workbook,
            file_name="relatorio_de_precos.xlsx",
            mime=MIME_XLSX,
        )


def _find_column(headers: tuple[str, ...], aliases: tuple[str, ...]) -> int | None:
    normalized = [normalize_header(header) for header in headers]
    return next((normalized.index(alias) for alias in aliases if alias in normalized), None)


def _column(label: str, headers: tuple[str, ...], aliases: tuple[str, ...]) -> int | None:
    preferred = _find_column(headers, aliases)
    return st.selectbox(
        label,
        options=list(range(len(headers))),
        index=preferred,
        format_func=lambda index: f"{index + 1}. {headers[index]}",
        placeholder="Selecione a coluna",
    )
