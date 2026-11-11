from __future__ import annotations

import csv
import re
import unicodedata
from collections.abc import Callable, Iterable
from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from decimal import Decimal
from io import BytesIO, StringIO
from zipfile import BadZipFile, ZipFile

from defusedxml.common import DefusedXmlException
from openpyxl import Workbook, load_workbook
from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.utils.exceptions import InvalidFileException
from openpyxl.worksheet.table import Table, TableStyleInfo
from openpyxl.worksheet.worksheet import Worksheet

from price_monitor.services.catalog_search import CatalogResults, normalize_query

MAX_FILE_BYTES = 5_000_000
MAX_ROWS = 10_000
MAX_COLUMNS = 100
MAX_SEARCHES = 20
IMPORT_EXTENSIONS = ("csv", "tsv", "xlsx", "xlsm")
EXCEL_EXTENSIONS = ("xlsx", "xlsm")
type ImportValue = str | int | float


@dataclass(frozen=True)
class ImportedTable:
    headers: tuple[str, ...]
    rows: list[tuple[int, tuple[ImportValue, ...]]]


@dataclass(frozen=True)
class PriceRow:
    price: Decimal
    product: str
    seller: str
    store: str = ""
    query: str = ""
    barcode: str = ""
    url: str = ""
    origin: str = ""


@dataclass(frozen=True)
class OfferReview:
    line: int
    product: str
    store: str
    url: str
    reason: str
    price_row_index: int | None = None


@dataclass
class PriceReport:
    rows: list[PriceRow] = field(default_factory=list)
    issues: list[tuple[int, str, str]] = field(default_factory=list)
    from_catalogs: bool = False
    from_links: bool = False
    reviews: list[OfferReview] = field(default_factory=list)


def with_confirmed_offers(
    report: PriceReport, confirmations: Iterable[tuple[ImportValue, str]]
) -> PriceReport:
    rows = list(report.rows)
    reviews = []
    for review, (value, seller) in zip(report.reviews, confirmations, strict=True):
        price = _parse_brl(value)
        seller = seller.strip()
        if price is None or price <= 0 or not seller:
            reviews.append(review)
            continue
        row = PriceRow(
            price,
            review.product,
            seller,
            store=review.store,
            url=review.url,
            origin="Conferência manual",
        )
        if review.price_row_index is None:
            rows.append(row)
        else:
            rows[review.price_row_index] = row
    return replace(report, rows=rows, reviews=reviews)


def read_import(data: bytes, *, is_excel: bool, sheet_name: str | None = None) -> ImportedTable:
    if not data or len(data) > MAX_FILE_BYTES:
        raise ValueError("Envie um arquivo de até 5 MB.")
    try:
        if not is_excel:
            return _read_rows(_csv_rows(data))
        with _open_excel(data) as workbook:
            sheet = workbook[sheet_name] if sheet_name else workbook.worksheets[0]
            sheet.reset_dimensions()
            return _read_rows(sheet.values)
    except (
        BadZipFile,
        InvalidFileException,
        DefusedXmlException,
        csv.Error,
        UnicodeError,
        KeyError,
        SyntaxError,
        OSError,
        IndexError,
    ) as exc:
        raise ValueError(
            "Não foi possível ler o arquivo. Confira o formato e os cabeçalhos."
        ) from exc


def import_sheet_names(data: bytes) -> list[str]:
    with _open_excel(data) as workbook:
        return [sheet.title for sheet in workbook.worksheets if sheet.sheet_state == "visible"]


@contextmanager
def _open_excel(data: bytes) -> Iterable[Workbook]:
    if not data or len(data) > MAX_FILE_BYTES:
        raise ValueError("Envie um arquivo de até 5 MB.")
    try:
        with ZipFile(BytesIO(data)) as archive:
            if sum(item.file_size for item in archive.infolist()) > 30_000_000:
                raise ValueError("O conteúdo descompactado da planilha excede 30 MB.")
        workbook = load_workbook(
            BytesIO(data), read_only=True, data_only=True, keep_vba=False, keep_links=False
        )
    except (BadZipFile, InvalidFileException, DefusedXmlException, KeyError, SyntaxError) as exc:
        raise ValueError("Não foi possível abrir a planilha do Excel.") from exc
    try:
        if not workbook.worksheets:
            raise ValueError("A planilha não contém abas de dados.")
        yield workbook
    finally:
        workbook.close()


def _csv_rows(data: bytes) -> Iterable[list[str]]:
    try:
        contents = data.decode(
            "utf-16" if data.startswith((b"\xff\xfe", b"\xfe\xff")) else "utf-8-sig"
        )
    except UnicodeDecodeError:
        contents = data.decode("cp1252")
    try:
        dialect = csv.Sniffer().sniff(contents[:8192], delimiters=",;\t")
    except csv.Error:
        first_line = next((line for line in contents.splitlines() if line.strip()), "")
        delimiter = next((c for c in (";", "\t", ",") if c in first_line), ",")
        return csv.reader(StringIO(contents, newline=""), delimiter=delimiter, strict=True)
    return csv.reader(StringIO(contents, newline=""), dialect=dialect, strict=True)


def _read_rows(source: Iterable[Iterable[object]]) -> ImportedTable:
    rows = enumerate(source, start=1)
    headers: tuple[str, ...] = ()
    records: list[tuple[int, tuple[ImportValue, ...]]] = []
    for number, raw in rows:
        if number > MAX_ROWS + 1:
            raise ValueError(f"O arquivo pode ter até {MAX_ROWS:,} linhas de dados.")
        values = tuple(_import_value(value) for value in raw)
        if all(value == "" for value in values):
            continue
        if len(values) > MAX_COLUMNS:
            raise ValueError(f"O arquivo pode ter até {MAX_COLUMNS} colunas.")
        if not headers:
            headers = tuple(
                str(value) if value != "" else f"Coluna {index}"
                for index, value in enumerate(values, 1)
            )
        else:
            if any(value != "" for value in values[len(headers) :]):
                raise ValueError(f"A linha {number} tem mais campos do que o cabeçalho.")
            records.append((number, (values + ("",) * len(headers))[: len(headers)]))
    if not headers or not records:
        raise ValueError("O arquivo precisa de uma linha de cabeçalhos e pelo menos um registro.")
    return ImportedTable(headers, records)


def _import_value(value: object) -> ImportValue:
    if type(value) in (int, float):
        return value
    return "" if value is None else str(value).strip()


def normalize_header(value: str) -> str:
    return (
        "".join(char for char in unicodedata.normalize("NFKD", value.casefold()) if char.isascii())
        .replace("_", " ")
        .strip()
    )


def import_prices(table: ImportedTable, *, product: int, price: int, seller: int) -> PriceReport:
    report = PriceReport()
    for line, row in table.rows:
        name, vendor = str(row[product]), str(row[seller])
        amount = _parse_brl(row[price])
        if not name or amount is None:
            report.issues.append((line, name, "Nome ausente ou preço inválido."))
            continue
        if not vendor:
            report.issues.append((line, name, "Vendedor ausente."))
        report.rows.append(PriceRow(amount, name, vendor))
    return report


def _parse_brl(value: ImportValue) -> Decimal | None:
    if not isinstance(value, str):
        amount = Decimal(str(value))
        if amount.is_finite() and 0 <= amount < 10**12 and amount == round(amount, 2):
            return amount
        return None
    value = value.removeprefix("R$").strip()
    if re.fullmatch(r"(?:[0-9]+|[0-9]{1,3}(?:\.[0-9]{3})+),[0-9]{1,2}", value):
        value = value.replace(".", "").replace(",", ".")
    elif re.fullmatch(r"[0-9]{1,3}(?:\.[0-9]{3})+", value):
        value = value.replace(".", "")
    if not re.fullmatch(r"[0-9]{1,12}(?:\.[0-9]{1,2})?", value):
        return None
    return Decimal(value)


def lookup_prices(
    table: ImportedTable, column: int, lookup: Callable[[str], CatalogResults]
) -> PriceReport:
    report = PriceReport(from_catalogs=True)
    queries: dict[str, int] = {}
    for line, row in table.rows:
        query = normalize_query(str(row[column]))
        if 2 <= len(query) <= 100:
            queries.setdefault(query, line)
        else:
            report.issues.append((line, query, "Consulta vazia ou inválida."))
    if len(queries) > MAX_SEARCHES:
        raise ValueError(f"Envie até {MAX_SEARCHES} consultas distintas por arquivo.")
    for query, line in queries.items():
        try:
            result = lookup(query)
        except ValueError:
            report.issues.append((line, query, "Consulta inválida."))
            continue
        report.rows.extend(
            PriceRow(
                offer.price,
                offer.variant,
                offer.seller,
                offer.store,
                query,
                offer.barcode,
                offer.url,
            )
            for offer in result.offers
        )
        if not result.offers:
            report.issues.append((line, query, "Nenhuma oferta nos catálogos consultados."))
        if result.unavailable_stores:
            stores = ", ".join(result.unavailable_stores)
            report.issues.append((line, query, f"Lojas indisponíveis: {stores}"))
    return report


def report_to_xlsx(report: PriceReport) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    assert isinstance(sheet, Worksheet)
    sheet.title = "Preços"
    headers = ["Preço", "Nome do produto", "Vendedor"]
    widths = [18, 62, 34]
    if report.from_catalogs:
        headers += ["Loja", "Consulta", "EAN", "URL"]
        widths += [25, 40, 19, 50]
    if report.from_links:
        headers += ["Loja", "URL", "Origem"]
        widths += [30, 60, 24]
    sheet.append(headers)
    for offer in sorted(report.rows, key=lambda row: (row.price, row.product.casefold())):
        values = [offer.price, offer.product, offer.seller]
        if report.from_catalogs:
            values += [offer.store, offer.query, offer.barcode, offer.url]
        if report.from_links:
            values += [offer.store, offer.url, offer.origin]
        _append_values(sheet, values)
        sheet.cell(sheet.max_row, 1).number_format = '"R$" #,##0.00'
    _format_table(sheet, "TabelaPrecos", widths)

    if report.issues or report.reviews:
        issues = workbook.create_sheet("Pendências")
        headers = ["Linha de origem", "Produto ou consulta", "Motivo"]
        widths = [20, 46, 76]
        pending = list(report.issues)
        if report.from_links:
            headers += ["Loja", "URL"]
            widths += [30, 60]
            pending = [(*issue, "", "") for issue in pending]
            pending.extend(
                (review.line, review.product, review.reason, review.store, review.url)
                for review in report.reviews
            )
        issues.append(headers)
        for issue in sorted(pending):
            _append_values(issues, issue)
        _format_table(issues, "TabelaPendencias", widths)
        if not report.rows:
            workbook.active = issues

    output = BytesIO()
    workbook.save(output)
    return output.getvalue()


def _append_values(sheet: Worksheet, values: Iterable[str | Decimal | int]) -> None:
    row = sheet.max_row + 1
    for column, value in enumerate(values, start=1):
        cell = sheet.cell(row, column)
        if isinstance(value, str):
            cell.value = ILLEGAL_CHARACTERS_RE.sub("", value)
            cell.data_type = "s"
        else:
            cell.value = value


def _format_table(sheet: Worksheet, name: str, widths: list[int]) -> None:
    sheet.freeze_panes = "A2"
    sheet.sheet_view.showGridLines = False
    for column, width in enumerate(widths, start=1):
        sheet.column_dimensions[get_column_letter(column)].width = width
    if sheet.max_row > 1:
        table = Table(displayName=name, ref=sheet.dimensions)
        table.tableStyleInfo = TableStyleInfo(name="TableStyleMedium2", showRowStripes=True)
        sheet.add_table(table)
    else:
        for cell in sheet[1]:
            cell.fill = PatternFill("solid", fgColor="17414A")
            cell.font = Font(bold=True, color="FFFFFF")
