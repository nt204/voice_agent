from datetime import datetime, timezone
from io import BytesIO

from openpyxl import load_workbook

from app.order_export import build_packing_workbook, packing_workbook_filename


def test_packing_workbook_is_formatted_and_contains_product_summary() -> None:
    generated = datetime(2026, 7, 22, 8, 30, tzinfo=timezone.utc)
    content = build_packing_workbook(
        [
            {
                "id": 18,
                "created_at": "2026-07-22T07:00:00+00:00",
                "customer_name": "=unsafe name",
                "customer_phone": "09789119333",
                "product_name": "Venus BigOne Combo 2",
                "quantity": 2,
                "unit_price": 105000,
                "total_price": 210000,
                "shipping_address": "No. 12 Pyay Road, Yangon",
                "status": "confirmed",
                "missing_fields": [],
            },
            {
                "id": 19,
                "created_at": "2026-07-22T07:10:00+00:00",
                "customer_name": "Daw Mya",
                "customer_phone": "09789119334",
                "product_name": "Venus BigOne Combo 2",
                "quantity": 4,
                "unit_price": 97500,
                "total_price": 390000,
                "shipping_address": "Bago Main Road, Bago",
                "status": "packed",
                "missing_fields": [],
            },
        ],
        filter_label="Chờ đóng gói",
        generated_at=generated,
    )

    assert content.startswith(b"PK")
    workbook = load_workbook(BytesIO(content))
    sheet = workbook["Phiếu đóng gói"]
    summary = workbook["Tổng hợp sản phẩm"]

    assert sheet["A1"].value == "PHIẾU ĐÓNG GÓI ĐƠN HÀNG"
    assert "A1:L1" in {str(cell_range) for cell_range in sheet.merged_cells.ranges}
    assert sheet.freeze_panes == "A6"
    assert sheet.auto_filter.ref == "A5:L7"
    assert sheet["A5"].value == "STT"
    assert sheet["D6"].value == "'=unsafe name"
    assert sheet["I6"].number_format == '#,##0 "MMK"'
    assert sheet["K6"].value == "Chờ đóng gói"
    assert sheet.column_dimensions["J"].width >= 40
    assert summary["A4"].value == "Venus BigOne Combo 2"
    assert summary["B4"].value == 2
    assert summary["C4"].value == 6
    assert summary["D4"].value == 600000


def test_packing_workbook_filename_uses_vietnam_time() -> None:
    generated = datetime(2026, 7, 22, 18, 5, tzinfo=timezone.utc)
    assert packing_workbook_filename(generated) == "phieu-dong-goi-20260723-0105.xlsx"
