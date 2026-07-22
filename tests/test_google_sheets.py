import pytest
from app.google_sheets import (
    build_csv_export_url,
    map_sheet_row,
    parse_google_sheet_csv,
    parse_google_sheet_url,
)


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


def test_map_sheet_row_keeps_full_name_when_customer_note_is_present():
    lead = map_sheet_row(
        {
            "Time": "22/06/2026 14:03",
            "No.": "17",
            "Full name": "ဒေါ်သန်းသန်းရွှေ",
            "Phone": "9673639587",
            "Address": "ရန်ကုန်",
            "Qty": "1",
            "Combo": "1",
            "Joint note": "အိမ်မှာသာပို့ရန်",
            "Customer note": "မနက် 10 နာရီလောက် အိမ်မှာရှိပါသည်။",
            "Source": "messenger_consultation",
            "Status": "New",
            "Called": "FALSE",
            "Confirmed": "FALSE",
            "Delivered": "FALSE",
            "Canceled": "FALSE",
            "Sales note": "ပြန်စစ်ရန်",
            "System code": "17",
        }
    )

    assert lead["name"] == "ဒေါ်သန်းသန်းရွှေ"
    assert lead["customer_note"] == "မနက် 10 နာရီလောက် အိမ်မှာရှိပါသည်။"
    assert lead["joint_note"] == "အိမ်မှာသာပို့ရန်"
    assert lead["sales_note"] == "ပြန်စစ်ရန်"
    assert lead["notes"] == (
        "မနက် 10 နာရီလောက် အိမ်မှာရှိပါသည်။ | "
        "အိမ်မှာသာပို့ရန် | ပြန်စစ်ရန်"
    )
    assert lead["source"] == "messenger_consultation"
    assert lead["time_raw"] == "22/06/2026 14:03"
    assert lead["row_number"] == "17"
    assert lead["system_code"] == "17"


@pytest.mark.parametrize("terminal_column", ["Confirmed", "Delivered", "Canceled"])
def test_processed_sheet_flags_prevent_accidental_recall(terminal_column):
    row = {
        "Full name": "Myat Thu",
        "Phone": "9777706050",
        "Called": "FALSE",
        terminal_column: "TRUE",
    }

    lead = map_sheet_row(row)

    assert lead[terminal_column.casefold()] is True
    assert lead["called"] is True


def test_csv_parser_deduplicates_equivalent_phone_formats_and_rejects_malformed_number():
    leads = parse_google_sheet_csv(
        "Full name,Phone,Address,Qty,Combo,Status,Called\n"
        'Old row,"09 777 111 222",Yangon,1,1,New,FALSE\n'
        "New row,+959777111222,Mandalay,1,1,New,FALSE\n"
        "Bad row,92001788,Mandalay,1,1,New,FALSE\n"
    )

    assert leads[0]["normalized_phone"] == "+959777111222"
    assert leads[0]["is_duplicate"] is True
    assert leads[1]["normalized_phone"] == "+959777111222"
    assert leads[1]["is_duplicate"] is False
    assert leads[2]["normalized_phone"] == ""
    assert leads[2]["is_valid_phone"] is False


def test_missing_phone_is_not_guessed_from_time_or_system_code():
    lead = map_sheet_row(
        {
            "Time": "22/06/2026 14:03",
            "No.": "17",
            "Full name": "No Phone Customer",
            "System code": "9955104433",
        }
    )

    assert lead["phone"] == ""
