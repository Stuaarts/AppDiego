from __future__ import annotations

import asyncio
from collections.abc import Callable
from hashlib import sha256
from uuid import uuid4

import pandas as pd
import streamlit as st
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from price_monitor.config import Settings
from price_monitor.database import session_scope
from price_monitor.services.link_report import MAX_REPORT_LINKS, report_link_prices
from price_monitor.services.price_report import (
    EXCEL_EXTENSIONS,
    IMPORT_EXTENSIONS,
    MAX_SEARCHES,
    ImportedTable,
    PriceReport,
    import_prices,
    import_sheet_names,
    lookup_prices,
    normalize_header,
    read_import,
    report_to_xlsx,
    with_confirmed_offers,
)
from price_monitor.services.product_import import save_products
from price_monitor.ui.i18n import TEXT
from price_monitor.ui.pages.search import lookup

PRODUCT_HEADERS = ("nome do produto", "produto", "product name", "product", "nome", "name")
PRICE_HEADERS = ("preco", "preco atual", "valor", "price", "current price")
SELLER_HEADERS = ("vendedor", "seller", "seller name", "loja", "store")
QUERY_HEADERS = ("ean", "gtin", "upc", "codigo de barras", "barcode", "sku", *PRODUCT_HEADERS)
MIME_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
LINK_PRICES = "Verificar links do arquivo"
CATALOG_PRICES = "Buscar por nome, SKU ou EAN"
FILE_PRICES = "Usar preços do arquivo"


def render(
    settings: Settings,
    *,
    database_factory: Callable[[], sessionmaker[Session]] | None = None,
) -> None:
    st.title(TEXT["import"])
    uploaded = st.file_uploader("Base de produtos ou ofertas", type=IMPORT_EXTENSIONS)
    st.caption("CSV, TSV, XLSX ou XLSM com cabeçalhos na primeira linha. Até 5 MB.")
    if uploaded is None:
        st.session_state.pop("price_import_table", None)
        st.session_state.pop("price_import_report", None)
        st.session_state.pop("price_import_sheets", None)
        return

    data = uploaded.getvalue()
    extension = uploaded.name.lower().rsplit(".", 1)[-1]
    digest = sha256(data).hexdigest()
    is_excel = extension in EXCEL_EXTENSIONS
    sheet_name = None
    if is_excel:
        try:
            sheet_name = _select_sheet(data, digest)
        except ValueError as exc:
            st.error(str(exc))
            return
    file_key = (digest, extension, sheet_name)
    cached = st.session_state.get("price_import_table")
    if cached is None or cached[0] != file_key:
        st.session_state.pop("price_import_report", None)
        try:
            cached = (file_key, read_import(data, is_excel=is_excel, sheet_name=sheet_name))
        except ValueError as exc:
            st.error(str(exc))
            return
        st.session_state["price_import_table"] = cached
    table = cached[1]
    detected_links = _detected_links(table)
    if database_factory is not None:
        _render_monitor_import(table, detected_links, database_factory, settings.default_currency)

    headers = table.headers
    price_default = _find_column(headers, PRICE_HEADERS)
    if detected_links:
        default_mode = LINK_PRICES
    else:
        default_mode = CATALOG_PRICES if price_default is None else FILE_PRICES
    modes = [LINK_PRICES, CATALOG_PRICES, FILE_PRICES]
    mode = st.radio(
        "Origem dos preços",
        modes,
        index=modes.index(default_mode),
        key=f"price_import_mode_{digest}_{sheet_name}",
        horizontal=True,
    )
    if mode == LINK_PRICES:
        st.caption(f"Consulta as páginas da planilha. Até {MAX_REPORT_LINKS} links por relatório.")
        columns = (
            _column("Nome do produto", headers, PRODUCT_HEADERS),
            *_link_columns(headers, detected_links, "Colunas com links para consultar"),
        )
    elif mode == CATALOG_PRICES:
        st.caption(f"Até {MAX_SEARCHES} consultas distintas por arquivo.")
        columns = (_column("Nome, SKU ou EAN", headers, QUERY_HEADERS),)
    else:
        columns = (
            _column("Nome do produto", headers, PRODUCT_HEADERS),
            _column("Preço em reais", headers, PRICE_HEADERS),
            _column("Vendedor", headers, SELLER_HEADERS),
        )

    ready = (
        None not in columns
        and len(set(columns)) == len(columns)
        and (mode != LINK_PRICES or len(columns) > 1)
    )
    if not ready:
        st.info("Selecione uma coluna diferente para cada campo.")
    signature = (file_key, mode, columns)
    if st.button("Gerar relatório", type="primary", disabled=not ready):
        st.session_state.pop("price_import_report", None)
        selected = tuple(column for column in columns if column is not None)
        try:
            with st.spinner("Gerando relatório..."):
                if mode == LINK_PRICES:
                    report = asyncio.run(
                        report_link_prices(table, selected[0], selected[1:], settings)
                    )
                elif mode == CATALOG_PRICES:
                    report = lookup_prices(table, selected[0], lookup)
                else:
                    product, price, seller = selected
                    report = import_prices(table, product=product, price=price, seller=seller)
                st.session_state["price_import_report"] = (signature, report, uuid4().hex)
        except ValueError as exc:
            st.error(str(exc))

    saved = st.session_state.get("price_import_report")
    if saved is not None and saved[0] == signature:
        _, report, run_key = saved
        if report.reviews:
            report = _review_offers(report, run_key)
        rows, issues = len(report.rows), len(report.issues) + len(report.reviews)
        if rows:
            st.write(f"{rows} ofertas no relatório.")
        else:
            st.warning("Nenhum preço verificado. O Excel abre na aba Pendências.")
        if issues:
            st.warning(f"{issues} ocorrências na aba Pendências.")
        st.download_button(
            "Baixar Excel",
            data=report_to_xlsx(report),
            file_name="relatorio_de_precos.xlsx",
            mime=MIME_XLSX,
        )


def _review_offers(report: PriceReport, run_key: str) -> PriceReport:
    st.subheader("Conferir ofertas pendentes")
    data = pd.DataFrame(
        [
            {
                "Linha": review.line,
                "Produto": review.product,
                "Loja": review.store,
                "Motivo": review.reason,
                "Oferta": review.url,
                "Preço conferido": (
                    float(report.rows[review.price_row_index].price)
                    if review.price_row_index is not None
                    else None
                ),
                "Vendedor conferido": "",
            }
            for review in report.reviews
        ]
    )
    data["Preço conferido"] = data["Preço conferido"].astype(float)
    edited = st.data_editor(
        data,
        hide_index=True,
        disabled=["Linha", "Produto", "Loja", "Motivo", "Oferta"],
        column_order=[
            "Linha",
            "Loja",
            "Produto",
            "Preço conferido",
            "Vendedor conferido",
            "Oferta",
            "Motivo",
        ],
        column_config={
            "Linha": st.column_config.NumberColumn(width="small"),
            "Produto": st.column_config.TextColumn(width="medium"),
            "Oferta": st.column_config.LinkColumn(display_text="Abrir oferta", width="small"),
            "Preço conferido": st.column_config.NumberColumn(
                min_value=0.01, max_value=9999999999.99, step=0.01, format="R$ %.2f"
            ),
            "Vendedor conferido": st.column_config.TextColumn(max_chars=180),
        },
        key=f"offer_review_{run_key}",
    )
    confirmations = (
        (float(price) if pd.notna(price) else "", seller if isinstance(seller, str) else "")
        for price, seller in zip(
            edited["Preço conferido"], edited["Vendedor conferido"], strict=True
        )
    )
    return with_confirmed_offers(report, confirmations)


def _find_column(headers: tuple[str, ...], aliases: tuple[str, ...]) -> int | None:
    normalized = [normalize_header(header) for header in headers]
    return next((normalized.index(alias) for alias in aliases if alias in normalized), None)


def _select_sheet(data: bytes, digest: str) -> str:
    cached = st.session_state.get("price_import_sheets")
    if cached is None or cached[0] != digest:
        cached = (digest, import_sheet_names(data))
        st.session_state["price_import_sheets"] = cached
    sheets = cached[1]
    if not sheets:
        raise ValueError("A planilha não contém abas de dados visíveis.")
    default = sheets.index("Produtos") if "Produtos" in sheets else 0
    return st.selectbox("Aba do Excel", sheets, index=default, key=f"import_sheet_{digest}")


def _render_monitor_import(
    table: ImportedTable,
    detected: list[int],
    database_factory: Callable[[], sessionmaker[Session]],
    currency: str,
) -> None:
    headers = table.headers
    with st.expander("Salvar produtos para monitoramento", expanded=bool(detected)):
        product = _column("Nome para monitoramento", headers, PRODUCT_HEADERS)
        id_column = _column("Identificador opcional", headers, ("id", "codigo", "sku", "ean"))
        links = _link_columns(headers, detected, "Colunas com links de produtos")
        blocked = product is None or not links or product in links or id_column in links
        if st.button("Salvar para monitorar", disabled=blocked) and product is not None:
            try:
                with (
                    st.spinner("Salvando produtos..."),
                    session_scope(database_factory()) as session,
                ):
                    result = save_products(
                        session,
                        table,
                        product_column=product,
                        link_columns=tuple(links),
                        id_column=id_column,
                        currency=currency,
                    )
            except (ValueError, SQLAlchemyError) as exc:
                st.error(str(exc) if isinstance(exc, ValueError) else "Não foi possível salvar.")
                return
            st.success(
                f"{result.products_created} novos produtos, {result.listings_created} novos links "
                f"e {result.listings_existing} links já cadastrados."
            )
            if result.issues:
                st.dataframe(
                    [{"Linha": line, "Motivo": reason} for line, reason in result.issues],
                    hide_index=True,
                )


def _detected_links(table: ImportedTable) -> list[int]:
    return [
        index
        for index, header in enumerate(table.headers)
        if (
            (name := normalize_header(header)).startswith(("link ", "url "))
            or name in {"url", "link"}
        )
        and any(
            str(row[index]).strip(" ,;-").lower().startswith(("https://", "http://"))
            for _, row in table.rows
        )
    ]


def _link_columns(headers: tuple[str, ...], detected: list[int], label: str) -> list[int]:
    return st.multiselect(
        label,
        options=list(range(len(headers))),
        default=detected,
        format_func=lambda index: f"{index + 1}. {headers[index]}",
    )


def _column(label: str, headers: tuple[str, ...], aliases: tuple[str, ...]) -> int | None:
    preferred = _find_column(headers, aliases)
    return st.selectbox(
        label,
        options=list(range(len(headers))),
        index=preferred,
        format_func=lambda index: f"{index + 1}. {headers[index]}",
        placeholder="Selecione a coluna",
    )
