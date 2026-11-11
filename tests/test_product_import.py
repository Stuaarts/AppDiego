from io import BytesIO

from openpyxl import Workbook
from sqlalchemy import func, select

from price_monitor.models import Listing, Product
from price_monitor.security import UrlValidationResult
from price_monitor.services.price_report import import_sheet_names, read_import
from price_monitor.services.product_import import save_products


def test_select_workbook_sheet_and_register_links_once(session_factory, monkeypatch) -> None:
    workbook = Workbook()
    workbook.active.title = "Instructions"
    products = workbook.create_sheet("Produtos")
    products.append(["ID", "Produto", "Link Amazon", "Link Site Próprio"])
    products.append([1, "Fragmentadora", "https://store.example/product", ","])
    products.append([2, "Sem URL", ",", "file:///test"])
    buffer = BytesIO()
    workbook.save(buffer)
    assert import_sheet_names(buffer.getvalue()) == ["Instructions", "Produtos"]
    table = read_import(buffer.getvalue(), is_excel=True, sheet_name="Produtos")

    def validate(url: str) -> UrlValidationResult:
        return UrlValidationResult(ok=url.startswith("https://"), normalized_url=url)

    monkeypatch.setattr("price_monitor.services.product_import.normalize_public_url", validate)
    for expected in (1, 0):
        with session_factory() as session:
            result = save_products(
                session,
                table,
                product_column=1,
                link_columns=(2, 3),
                id_column=0,
                currency="BRL",
            )
            session.commit()
            assert result.products_created == result.listings_created == expected
            assert result.listings_existing == 1 - expected
            assert all(line == 3 for line, _ in result.issues)
            assert session.scalar(select(func.count(Product.id))) == 1
            assert session.scalar(select(Listing.scraping_method)) == "structured"


def test_excel_unicode_tsv_keeps_tabular_values() -> None:
    data = "Produto\tPreço\tVendedor\nPeça\t19,99\tLoja".encode("utf-16")
    table = read_import(data, is_excel=False)
    assert table.headers == ("Produto", "Preço", "Vendedor")
    assert table.rows == [(2, ("Peça", "19,99", "Loja"))]
