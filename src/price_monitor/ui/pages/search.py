from __future__ import annotations

import asyncio

import streamlit as st

from price_monitor.services.catalog_search import (
    CATALOGS,
    CatalogResults,
    normalize_query,
    search_catalogs,
)
from price_monitor.ui.i18n import TEXT


@st.cache_data(ttl=300, max_entries=128, show_spinner=False)
def lookup(query: str) -> CatalogResults:
    return asyncio.run(search_catalogs(query))


def render() -> None:
    st.title(TEXT["search"])
    with st.form("catalog_search"):
        query = st.text_input(
            "Nome do produto, SKU ou código de barras",
            placeholder="Ex.: Cafeteira Oster OCAF550",
            max_chars=100,
        )
        submitted = st.form_submit_button("Buscar", type="primary")

    if submitted:
        st.session_state.pop("catalog_search_results", None)
        st.session_state.pop("catalog_search_barcode", None)
        try:
            with st.spinner("Consultando as lojas..."):
                normalized = normalize_query(query)
                st.session_state["catalog_search_results"] = (normalized, lookup(normalized))
        except ValueError as exc:
            st.warning(str(exc))

    saved = st.session_state.get("catalog_search_results")
    if saved is not None:
        searched, results = saved
        _render_results(searched, results)

    with st.expander(f"Lojas consultadas ({len(CATALOGS)})"):
        st.write(", ".join(CATALOGS))


def _render_results(query: str, results: CatalogResults) -> None:
    if results.unavailable_stores:
        st.warning("Lojas indisponíveis nesta busca: " + ", ".join(results.unavailable_stores))
    if not results.offers:
        if len(results.unavailable_stores) < len(CATALOGS):
            st.info(f'Nenhuma oferta disponível para "{query}" nas lojas que responderam.')
        return

    st.subheader(f'Resultados para "{query}"')
    offers = results.offers
    variants = {offer.barcode: offer.variant for offer in offers if offer.barcode}
    if len(variants) > 1:
        barcode = st.selectbox(
            "Comparar variante por código de barras",
            ["", *variants],
            format_func=lambda value: f"{value} · {variants[value]}" if value else "Todas",
            key="catalog_search_barcode",
        )
        if barcode:
            offers = [offer for offer in offers if offer.barcode == barcode]
    st.caption(
        f"{len(offers)} ofertas em {len({offer.store for offer in offers})} lojas. "
        "Preços em reais, sem frete. Disponibilidade e preço podem variar por CEP."
    )
    st.dataframe(
        [
            {
                "Preço": float(offer.price),
                "Loja": offer.store,
                "Produto": offer.product,
                "Variante": offer.variant,
                "Vendedor": offer.seller,
                "EAN": offer.barcode,
                "SKU da loja": offer.sku,
                "Código exato": offer.exact_code,
                "Link": offer.url,
            }
            for offer in offers
        ],
        hide_index=True,
        column_config={
            "Preço": st.column_config.NumberColumn(format="R$ %.2f"),
            "Link": st.column_config.LinkColumn("Abrir", display_text="Ver oferta"),
            "Código exato": (
                st.column_config.CheckboxColumn() if any(o.exact_code for o in offers) else None
            ),
        },
    )
