from decimal import Decimal
from io import BytesIO

from openpyxl import Workbook, load_workbook

from price_monitor.services.catalog_search import CatalogOffer, CatalogResults
from price_monitor.services.price_report import (
    import_prices,
    lookup_prices,
    read_import,
    report_to_xlsx,
)


def test_csv_report_uses_numeric_prices_excel_filters_and_literal_text() -> None:
    data = (
        "Nome do produto;Preço;Vendedor\n"
        "Cafeteira;R$ 1.299,90;Loja A\n"
        "=1+1;99,90;Loja B\n"
        "Produto sem preço;;Loja C\n"
    ).encode("cp1252")
    table = read_import(data, is_excel=False)
    report = import_prices(table, product=0, price=1, seller=2)
    workbook = load_workbook(BytesIO(report_to_xlsx(report)))
    sheet = workbook["Preços"]

    assert [cell.value for cell in sheet[1]] == ["Preço", "Nome do produto", "Vendedor"]
    assert [cell[0].value for cell in sheet.iter_rows(min_row=2)] == [99.90, 1299.90]
    assert sheet["A2"].data_type == "n"
    assert sheet["B2"].value == "=1+1" and sheet["B2"].data_type == "s"
    assert sheet.tables["TabelaPrecos"].autoFilter.ref == "A1:C3"
    assert sheet.freeze_panes == "A2"
    assert workbook["Pendências"]["A2"].value == 4


def test_excel_import_preserves_numeric_zero_and_rejects_excess_precision() -> None:
    workbook = Workbook()
    workbook.active.append(["Produto", "Preço", "Vendedor"])
    workbook.active.append(["Amostra", 0, "Loja"])
    workbook.active.append(["Valor fora do padrão", 1.234, "Loja"])
    buffer = BytesIO()
    workbook.save(buffer)
    table = read_import(buffer.getvalue(), is_excel=True)
    report = import_prices(table, product=0, price=1, seller=2)
    assert [row.price for row in report.rows] == [0]
    assert len(report.issues) == 1


def test_bulk_lookup_preserves_queries_and_reports_missing_offers() -> None:
    table = read_import(b"SKU\n00123\n00123\n00456\n", is_excel=False)
    searched = []

    def lookup(query: str) -> CatalogResults:
        searched.append(query)
        if query == "00456":
            return CatalogResults([], ["Outra loja"])
        return CatalogResults(
            [
                CatalogOffer(
                    "Loja",
                    "Produto",
                    "Produto 220V",
                    "42",
                    "7898742842100",
                    "Vendedor",
                    Decimal("19.99"),
                    "https://example.com/produto/p",
                    True,
                )
            ],
            [],
        )

    report = lookup_prices(table, 0, lookup)
    assert searched == ["00123", "00456"]
    assert report.rows[0].query == "00123"
    assert report.rows[0].product == "Produto 220V"
    assert len(report.issues) == 2
