import pytest
from app.google_sheets import parse_google_sheet_url, build_csv_export_url, map_sheet_row


def test_parse_google_sheet_url_valid():
    url = "https://docs.google.com/spreadsheets/d/1gw22t8FruDmqRdK0EkwRnyrTFMl2I2A-dBEuEm_zbb4/edit?gid=0#gid=0"
    sheet_id, gid = parse_google_sheet_url(url)
    assert sheet_id == "1gw22t8FruDmqRdK0EkwRnyrTFMl2I2A-dBEuEm_zbb4"
    assert gid == "0"


def test_parse_google_sheet_url_invalid():
    with pytest.raises(ValueError):
        parse_google_sheet_url("https://invalid-url.com")


def test_build_csv_export_url():
    url = build_csv_export_url("abc123id", "12")
    assert url == "https://docs.google.com/spreadsheets/d/abc123id/gviz/tq?tqx=out:csv&gid=12"


def test_map_sheet_row():
    row = {
        "Họ tên": "Aung Ko",
        "Số điện thoại": "+95912345678",
        "Sản phẩm": "Venus BigOne",
        "Combo": "Venus BigOne Combo 2",
        "Số lượng": "2",
        "Địa chỉ": "Yangon, Myanmar",
        "Ghi chú": "Giao giờ hành chính",
        "Called": "FALSE",
        "Status": "New",
    }
    lead = map_sheet_row(row)
    assert lead["name"] == "Aung Ko"
    assert lead["phone"] == "+95912345678"
    assert lead["product"] == "Venus BigOne"
    assert lead["offer"] == "Venus BigOne Combo 2"
    assert lead["quantity"] == "2"
    assert lead["address"] == "Yangon, Myanmar"
    assert lead["notes"] == "Giao giờ hành chính"
    assert lead["called"] is False


def test_map_sheet_row_called_status():
    row = {
        "Full name": "Myat Thu",
        "Phone": "9777706050",
        "Called": "TRUE",
        "Status": "Called",
    }
    lead = map_sheet_row(row)
    assert lead["name"] == "Myat Thu"
    assert lead["phone"] == "9777706050"
    assert lead["called"] is True


def test_map_sheet_row_does_not_default_missing_quantity_to_one():
    lead = map_sheet_row({"Name": "Myat Thu", "Phone": "9777706050"})

    assert lead["quantity"] == ""
