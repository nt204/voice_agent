import csv
import io
import re
from typing import Any
import httpx

from app.phone_numbers import normalize_phone_number


def parse_google_sheet_url(url: str) -> tuple[str, str]:
    """
    Extracts (spreadsheet_id, gid) from a Google Sheets URL.
    Returns (spreadsheet_id, gid). Raises ValueError if URL is invalid.
    """
    url = url.strip()
    match = re.search(r"/d/([a-zA-Z0-9-_]+)", url)
    if not match:
        raise ValueError("Invalid Google Sheet URL: Spreadsheet ID not found.")
    
    spreadsheet_id = match.group(1)
    
    # Extract gid (default to "0" if not specified)
    gid_match = re.search(r"[?&]gid=([0-9]+)", url) or re.search(r"#gid=([0-9]+)", url)
    gid = gid_match.group(1) if gid_match else "0"
    
    return spreadsheet_id, gid


def build_csv_export_url(spreadsheet_id: str, gid: str = "0") -> str:
    """Builds the direct CSV download URL for a public/link-shared Google Sheet."""
    return f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/gviz/tq?tqx=out:csv&gid={gid}"


def normalize_column_name(header: str) -> str:
    """Normalizes column header for flexible fuzzy matching."""
    return re.sub(r"\s+", "_", header.strip().lower())


def _first_value(row: dict[str, str], *aliases: str) -> str:
    for alias in aliases:
        value = row.get(alias, "")
        if value:
            return value
    return ""


def _sheet_flag(value: object) -> bool:
    return str(value or "").strip().casefold() in {
        "true",
        "yes",
        "1",
        "x",
        "y",
        "checked",
        "đã gọi",
        "đã chốt",
    }


def _combined_notes(*values: str) -> str:
    notes: list[str] = []
    for value in values:
        clean = str(value or "").strip()
        if clean and clean not in notes:
            notes.append(clean)
    return " | ".join(notes)


def map_sheet_row(row: dict[str, str]) -> dict[str, Any]:
    """
    Maps a CSV row dict (header -> val) to normalized lead fields:
    phone, name, product, offer, quantity, address, notes, called, status_raw.
    """
    normalized_dict = {
        normalize_column_name(k): str(v or "").strip()
        for k, v in row.items()
        if k
    }

    # Match known headers explicitly. In particular, `customer_note` must not
    # be treated as a customer name merely because it contains `customer`.
    phone = _first_value(
        normalized_dict,
        "phone",
        "phone_number",
        "số_điện_thoại",
        "điện_thoại",
        "sdt",
        "mobile",
        "contact",
        "tel",
    )
    name = _first_value(
        normalized_dict,
        "full_name",
        "customer_name",
        "name",
        "họ_tên",
        "tên_khách_hàng",
        "khách_hàng",
        "tên",
        "customer",
    )
    product = _first_value(
        normalized_dict,
        "product",
        "product_name",
        "sản_phẩm",
        "sp",
        "item",
    )
    offer = _first_value(
        normalized_dict,
        "combo",
        "offer",
        "offer_name",
        "package",
        "gói",
    )
    # Missing quantity must stay unknown. Never silently turn an empty cell
    # into one package.
    quantity = _first_value(
        normalized_dict,
        "qty",
        "quantity",
        "số_lượng",
        "sl",
        "amount",
    )
    address = _first_value(
        normalized_dict,
        "address",
        "shipping_address",
        "địa_chỉ",
        "nơi_ở",
        "location",
    )

    customer_note = _first_value(
        normalized_dict,
        "customer_note",
        "customer_notes",
        "ghi_chú_khách_hàng",
    )
    joint_note = _first_value(normalized_dict, "joint_note", "joint_notes")
    sales_note = _first_value(normalized_dict, "sales_note", "sales_notes")
    generic_note = _first_value(
        normalized_dict,
        "note",
        "notes",
        "ghi_chú",
        "yêu_cầu",
        "remark",
    )
    notes = _combined_notes(customer_note, joint_note, generic_note, sales_note)

    status_raw = _first_value(normalized_dict, "status", "trạng_thái")
    confirmed = _sheet_flag(
        _first_value(normalized_dict, "confirmed", "đã_xác_nhận")
    )
    delivered = _sheet_flag(
        _first_value(normalized_dict, "delivered", "đã_giao")
    )
    canceled = _sheet_flag(
        _first_value(
            normalized_dict,
            "canceled",
            "cancelled",
            "đã_hủy",
        )
    )
    called = _sheet_flag(
        _first_value(normalized_dict, "called", "đã_gọi")
    )
    if status_raw.casefold() in {
        "called",
        "confirmed",
        "canceled",
        "cancelled",
        "completed",
        "delivered",
        "đã gọi",
        "đã chốt",
        "đã giao",
        "đã hủy",
    }:
        called = True
    # A fulfilled, confirmed, or canceled order must never be queued as a new
    # outbound sales call merely because its Called cell was left blank.
    called = called or confirmed or delivered or canceled

    return {
        "phone": phone,
        "name": name,
        "product": product,
        "offer": offer,
        "quantity": quantity,
        "address": address,
        "notes": notes,
        "customer_note": customer_note,
        "joint_note": joint_note,
        "sales_note": sales_note,
        "source": _first_value(normalized_dict, "source", "nguồn"),
        "called": called,
        "confirmed": confirmed,
        "delivered": delivered,
        "canceled": canceled,
        "status_raw": status_raw,
        "time_raw": _first_value(normalized_dict, "time", "timestamp", "created_at"),
        "row_number": _first_value(normalized_dict, "no.", "no", "number", "stt"),
        "system_code": _first_value(normalized_dict, "system_code", "mã_hệ_thống"),
        "raw_row": row,
    }


def parse_google_sheet_csv(csv_text: str) -> list[dict[str, Any]]:
    """Parse exported CSV and mark invalid/duplicate phone rows."""
    reader = csv.DictReader(io.StringIO(csv_text))
    leads: list[dict[str, Any]] = []

    for row in reader:
        lead = map_sheet_row(row)
        if lead["phone"] or lead["name"]:
            leads.append(lead)

    # Keep only the bottom-most row active for each normalized phone number.
    # Formatting variants such as 09... and +959... therefore count as the
    # same customer.
    seen_phones: set[str] = set()
    for lead in reversed(leads):
        normalized_phone = normalize_phone_number(str(lead.get("phone") or ""))
        is_valid = bool(re.fullmatch(r"\+[1-9][0-9]{7,14}", normalized_phone))
        lead["normalized_phone"] = normalized_phone if is_valid else ""
        lead["is_valid_phone"] = is_valid
        if is_valid:
            lead["is_duplicate"] = normalized_phone in seen_phones
            seen_phones.add(normalized_phone)
        else:
            lead["is_duplicate"] = False

    return leads

async def fetch_and_parse_google_sheet(sheet_url: str) -> list[dict[str, Any]]:
    """
    Fetches Google Sheet CSV content from the given URL and parses leads.
    When duplicate phone numbers exist, keeps the LATEST (bottom-most) row as active,
    and flags earlier rows as duplicate.
    """
    spreadsheet_id, gid = parse_google_sheet_url(sheet_url)
    csv_url = build_csv_export_url(spreadsheet_id, gid)
    
    async with httpx.AsyncClient(follow_redirects=True, timeout=15.0) as client:
        response = await client.get(csv_url)
        if response.status_code != 200:
            raise RuntimeError(
                f"Failed to fetch Google Sheet (HTTP {response.status_code}). "
                "Please make sure the Google Sheet link sharing is set to 'Anyone with the link can view'."
            )
        csv_text = response.text

    return parse_google_sheet_csv(csv_text)
