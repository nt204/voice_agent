import csv
import io
import re
from typing import Any
import httpx


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


def map_sheet_row(row: dict[str, str]) -> dict[str, Any]:
    """
    Maps a CSV row dict (header -> val) to normalized lead fields:
    phone, name, product, offer, quantity, address, notes, called, status_raw.
    """
    normalized_dict = {normalize_column_name(k): v.strip() for k, v in row.items() if k}
    
    phone = ""
    name = ""
    product = ""
    offer = ""
    # Missing quantity must stay unknown. Sheet campaigns confirm an existing
    # order, but must never silently turn an empty quantity into one item.
    quantity = ""
    address = ""
    notes = ""
    called = False
    status_raw = ""
    
    for key, val in normalized_dict.items():
        if not val:
            continue
        # Phone
        if any(term in key for term in ["phone", "sdt", "số_điện_thoại", "điện_thoại", "contact", "mobile", "tel"]):
            phone = val
        # Name
        elif any(term in key for term in ["name", "tên", "khách_hàng", "họ_tên", "customer"]):
            name = val
        # Configured product and selected package/offer are separate concepts.
        # A Sheet commonly stores "Combo" while the campaign selects Product.
        elif any(term in key for term in ["combo", "offer", "package", "gói"]):
            offer = val
        # Product
        elif any(term in key for term in ["product", "sản_phẩm", "sp", "item"]):
            product = val
        # Quantity
        elif any(term in key for term in ["quantity", "số_lượng", "qty", "sl", "amount"]):
            quantity = val
        # Address
        elif any(term in key for term in ["address", "địa_chỉ", "nơi_ở", "location"]):
            address = val
        # Notes
        elif any(term in key for term in ["note", "ghi_chú", "notes", "yêu_cầu", "remark"]):
            notes = val
        # Called status
        elif key == "called" or "đã_gọi" in key:
            if val.lower() in {"true", "yes", "1", "x", "đã gọi", "y"}:
                called = True
        # Status raw
        elif key in {"status", "trạng_thái"}:
            status_raw = val
            if val.lower() in {"called", "confirmed", "canceled", "cancelled", "completed", "đã gọi", "đã chốt"}:
                called = True

    # Backup heuristic: if phone wasn't matched by header, check if any column value looks like a phone number
    if not phone:
        for val in normalized_dict.values():
            digits = re.sub(r"\D", "", val)
            if 8 <= len(digits) <= 15:
                phone = val
                break

    return {
        "phone": phone,
        "name": name,
        "product": product,
        "offer": offer,
        "quantity": quantity,
        "address": address,
        "notes": notes,
        "called": called,
        "status_raw": status_raw,
        "raw_row": row,
    }

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

    reader = list(csv.DictReader(io.StringIO(csv_text)))
    leads: list[dict[str, Any]] = []
    
    for row in reader:
        lead = map_sheet_row(row)
        if lead["phone"] or lead["name"]:  # Skip completely empty rows
            leads.append(lead)

    # Reverse pass: Keep the latest (last) entry for each phone number active,
    # and flag earlier entries of the same phone number as duplicate.
    seen_phones: set[str] = set()
    for lead in reversed(leads):
        clean_phone = re.sub(r"\D", "", lead["phone"]) if lead["phone"] else ""
        lead["is_valid_phone"] = bool(clean_phone and 7 <= len(clean_phone) <= 15)
        if clean_phone and lead["is_valid_phone"]:
            if clean_phone in seen_phones:
                lead["is_duplicate"] = True
            else:
                lead["is_duplicate"] = False
                seen_phones.add(clean_phone)
        else:
            lead["is_duplicate"] = False

    return leads
