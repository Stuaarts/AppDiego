from io import BytesIO

import pytest
from openpyxl import load_workbook

from price_monitor.scraping.client import HttpFetchResult
from price_monitor.security import UrlValidationResult
from price_monitor.services.link_report import report_link_prices
from price_monitor.services.price_report import (
    PriceReport,
    read_import,
    report_to_xlsx,
    with_confirmed_offers,
)


@pytest.mark.asyncio
async def test_report_uses_product_links_and_lists_blocked_stores(monkeypatch, test_settings):
    table = read_import(
        b"Produto;Link Amazon;Link Loja\n"
        b"Produto original;https://www.amazon.com.br/dp/example;https://loja.test/p\n",
        is_excel=False,
    )

    def validate(url):
        return UrlValidationResult(ok=True, normalized_url=url)

    class Fetcher:
        async def fetch(self, url):
            if "loja.test" in url:
                return HttpFetchResult(False, url, error_code="http_403")
            return HttpFetchResult(
                True,
                url,
                html="""
                <title>Produto</title><script>const captchaConfig = {};</script>
                <div id="corePrice_feature_div">
                  <span class="a-price a-text-price"><span class="a-offscreen">R$ 150</span></span>
                  <span class="a-price"><span class="a-offscreen">R$ 100,50</span></span>
                </div>
                <a id="sellerProfileTriggerId">Vendedor teste</a>
                """,
            )

    monkeypatch.setattr("price_monitor.services.product_import.normalize_public_url", validate)
    result = await report_link_prices(table, 0, (1, 2), test_settings, fetcher=Fetcher())
    assert len(result.rows) == 1
    assert result.rows[0].product == "Produto original"
    assert result.rows[0].seller == "Vendedor teste"
    assert len(result.reviews) == 1
    assert result.reviews[0].reason == "A loja bloqueou a consulta (403)."
    assert result.reviews[0].url == "https://loja.test/p"

    workbook = load_workbook(BytesIO(report_to_xlsx(result)))
    assert [cell.value for cell in workbook["Preços"][1]] == [
        "Preço",
        "Nome do produto",
        "Vendedor",
        "Loja",
        "URL",
        "Origem",
    ]
    assert workbook["Preços"]["A2"].value == 100.5
    assert workbook["Preços"].tables["TabelaPrecos"].autoFilter.ref == "A1:F2"
    assert workbook["Pendências"]["E2"].value == "https://loja.test/p"
    assert with_confirmed_offers(result, [("119,99", "")]).reviews == result.reviews
    updated = with_confirmed_offers(result, [("119,99", "Loja confirmada")])
    assert not updated.reviews and len(updated.rows) == 2
    completed = load_workbook(BytesIO(report_to_xlsx(updated)))
    assert completed["Preços"]["A3"].value == 119.99
    assert completed["Preços"]["C3"].value == "Loja confirmada"
    assert completed["Preços"]["F3"].value == "Conferência manual"


def test_empty_report_opens_on_issues():
    report = PriceReport(issues=[(2, "Produto", "Nenhum preço verificado.")])
    assert load_workbook(BytesIO(report_to_xlsx(report))).active.title == "Pendências"
