from __future__ import annotations

from collections.abc import Callable
from hashlib import sha256

import streamlit as st
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from price_monitor.database import session_scope
from price_monitor.services.price_report import (
    EXCEL_EXTENSIONS,
    IMPORT_EXTENSIONS,
    MAX_SEARCHES,
    ImportedTable,
    import_prices,
    import_sheet_names,
    lookup_prices,
    normalize_header,
    read_import,
    report_to_xlsx,
)
from price_monitor.services.product_import import save_products
from price_monitor.ui.i18n import TEXT
from price_monitor.ui.pages.search import lookup

PRODUCT_HEADERS = ("nome do produto", "produto", "product name", "product", "nome", "name")
PRICE_HEADERS = ("preco", "preco atual", "valor", "price", "current price")
SELLER_HEADERS = ("vendedor", "seller", "seller name", "loja", "store")
QUERY_HEADERS = ("ean", "gtin", "upc", "codigo de barras", "barcode", "sku", *PRODUCT_HEADERS)
MIME_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def render(
    *,
    database_factory: Callable[[], sessionmaker[Session]] | None = None,
    currency: str = "BRL",
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
    if database_factory is not None:
        _render_monitor_import(table, database_factory, currency)

    headers = table.headers
    price_default = _find_column(headers, PRICE_HEADERS)
    search_mode = st.radio(
        "Origem dos preços",
        [False, True],
        index=int(price_default is None),
        format_func=lambda search: "Buscar nas lojas" if search else "Usar preços do arquivo",
        key=f"price_import_mode_{digest}_{sheet_name}",
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
    database_factory: Callable[[], sessionmaker[Session]],
    currency: str,
) -> None:
    headers = table.headers
    detected = [
        index
        for index, header in enumerate(headers)
        if (name := normalize_header(header)).startswith(("link ", "url "))
        or name in {"url", "link"}
    ]
    with st.expander("Salvar produtos para monitoramento", expanded=bool(detected)):
        product = _column("Nome para monitoramento", headers, PRODUCT_HEADERS)
        id_column = _column("Identificador opcional", headers, ("id", "codigo", "sku", "ean"))
        links = st.multiselect(
            "Colunas com links de produtos",
            options=list(range(len(headers))),
            default=detected,
            format_func=lambda index: f"{index + 1}. {headers[index]}",
        )
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


def _column(label: str, headers: tuple[str, ...], aliases: tuple[str, ...]) -> int | None:
    preferred = _find_column(headers, aliases)
    return st.selectbox(
        label,
        options=list(range(len(headers))),
        index=preferred,
        format_func=lambda index: f"{index + 1}. {headers[index]}",
        placeholder="Selecione a coluna",
    )
