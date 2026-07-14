from __future__ import annotations

import asyncio

import pandas as pd
import streamlit as st
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload, sessionmaker

from price_monitor.config import Settings
from price_monitor.models import Listing, Product, Store
from price_monitor.repositories.listings import create_listing
from price_monitor.repositories.products import create_product
from price_monitor.services.product_service import parse_optional_decimal
from price_monitor.services.scrape_service import scrape
from price_monitor.ui.components import page_header
from price_monitor.ui.formatting import local_datetime


def render(session_factory: sessionmaker[Session], settings: Settings) -> None:
    page_header("Produtos", "Cadastre produtos e suas URLs exatas por loja.")
    with st.expander("Novo produto", expanded=False):
        with st.form("product_form", clear_on_submit=True):
            col1, col2, col3 = st.columns(3)
            name = col1.text_input("Nome do produto")
            internal_code = col2.text_input("Codigo interno")
            category = col3.text_input("Categoria")
            col4, col5, col6 = st.columns(3)
            manufacturer = col4.text_input("Fabricante")
            model_number = col5.text_input("Modelo")
            sku = col6.text_input("SKU / UPC / EAN")
            target_price = st.text_input("Preco alvo opcional")
            description = st.text_area("Descricao opcional")
            submitted = st.form_submit_button("Salvar produto")
        if submitted:
            try:
                with session_factory() as session:
                    create_product(
                        session,
                        name=name,
                        internal_code=internal_code,
                        manufacturer=manufacturer,
                        model_number=model_number,
                        sku=sku,
                        upc_or_ean=sku,
                        category=category,
                        description=description,
                        target_price=parse_optional_decimal(target_price),
                        default_currency=settings.default_currency,
                    )
                    session.commit()
                st.success("Produto criado.")
                st.rerun()
            except Exception as exc:
                st.error(str(exc))

    with session_factory() as session:
        products = session.scalars(
            select(Product)
            .options(selectinload(Product.listings).selectinload(Listing.store))
            .order_by(Product.name)
        ).all()
        stores = session.scalars(
            select(Store).where(Store.active.is_(True)).order_by(Store.name)
        ).all()

    if not products:
        st.info("Nenhum produto cadastrado.")
        return

    product_rows = [
        {
            "ID": product.id,
            "Produto": product.name,
            "Codigo": product.internal_code,
            "Categoria": product.category,
            "Ativo": product.active,
            "Listagens": len([listing for listing in product.listings if listing.active]),
        }
        for product in products
    ]
    st.dataframe(pd.DataFrame(product_rows), use_container_width=True, hide_index=True)

    selected_id = st.selectbox(
        "Produto selecionado",
        options=[product.id for product in products],
        format_func=lambda value: next(product.name for product in products if product.id == value),
    )
    selected = next(product for product in products if product.id == selected_id)

    left, right = st.columns([2, 1])
    with left:
        st.subheader("Listagens")
        listing_rows = [
            {
                "ID": listing.id,
                "Loja": listing.store.name,
                "URL": listing.url,
                "Moeda": listing.currency,
                "Metodo": listing.scraping_method,
                "Falhas": listing.consecutive_failures,
                "Ultimo sucesso": local_datetime(
                    listing.last_success_at, settings.display_timezone
                ),
                "Ativa": listing.active,
            }
            for listing in selected.listings
        ]
        if listing_rows:
            st.dataframe(pd.DataFrame(listing_rows), use_container_width=True, hide_index=True)
        else:
            st.info("Produto sem listagens.")
    with right:
        if st.button("Atualizar este produto", use_container_width=True):
            with st.spinner("Coletando listagens do produto..."):
                result = asyncio.run(
                    scrape(
                        session_factory,
                        settings,
                        trigger_source="manual_dashboard",
                        product_id=selected.id,
                    )
                )
            st.success(f"{result.successful} sucesso(s), {result.failed} falha(s).")

    st.subheader("Adicionar listagem")
    if not stores:
        st.warning("Cadastre uma loja antes de adicionar listagens.")
        return
    with st.form("listing_form", clear_on_submit=True):
        store_id = st.selectbox(
            "Loja",
            options=[store.id for store in stores],
            format_func=lambda value: next(store.name for store in stores if store.id == value),
        )
        url = st.text_input("URL exata do produto")
        col1, col2 = st.columns(2)
        seller_name = col1.text_input("Vendedor opcional")
        store_sku = col2.text_input("SKU da loja opcional")
        col3, col4 = st.columns(2)
        currency = col3.text_input("Moeda", value=settings.default_currency)
        scraping_method = col4.selectbox("Metodo", ["auto", "http", "browser"])
        st.caption("Seletores CSS opcionais para lojas que nao expõem metadados estruturados.")
        price_selector = st.text_input("Seletor de preco")
        regular_price_selector = st.text_input("Seletor de preco regular")
        availability_selector = st.text_input("Seletor de disponibilidade")
        title_selector = st.text_input("Seletor de titulo")
        submitted_listing = st.form_submit_button("Salvar listagem")
    if submitted_listing:
        try:
            with session_factory() as session:
                create_listing(
                    session,
                    product_id=selected.id,
                    store_id=store_id,
                    url=url,
                    store_sku=store_sku,
                    seller_name=seller_name,
                    currency=currency,
                    scraping_method=scraping_method,
                    price_selector=price_selector,
                    regular_price_selector=regular_price_selector,
                    availability_selector=availability_selector,
                    title_selector=title_selector,
                )
                session.commit()
            st.success("Listagem criada.")
            st.rerun()
        except Exception as exc:
            st.error(str(exc))
