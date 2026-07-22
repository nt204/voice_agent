import re


VIETNAM_LOCAL_PREFIXES = ("03", "05", "07", "08")


def normalize_phone_number(number: str) -> str:
    """Normalize dialing numbers for Telnyx.

    Myanmar remains the default market for ambiguous local 09... numbers. Vietnam
    is accepted when the country code is explicit (+84, 84, 0084), when the local
    prefix is clearly Vietnamese (03/05/07/08), or when the input is prefixed with
    a Vietnam hint such as "VN 09..." or "vietnam: 09...".
    """
    raw = str(number or "").strip()
    country_hint = _country_hint(raw)
    cleaned = "".join(char for char in raw if char.isdigit() or char == "+")
    if not cleaned:
        return ""

    if cleaned.startswith("+"):
        return f"+{''.join(char for char in cleaned[1:] if char.isdigit())}"

    digits = "".join(char for char in cleaned if char.isdigit())
    if digits.startswith("00") and len(digits) > 2:
        return f"+{digits[2:]}"
    if digits.startswith(("84", "95")):
        return f"+{digits}"
    if digits.startswith("0") and len(digits) >= 9:
        if country_hint == "VN" or digits.startswith(VIETNAM_LOCAL_PREFIXES):
            return f"+84{digits[1:]}"
        return f"+95{digits[1:]}"
    # Myanmar Sheets commonly drop the domestic trunk prefix 0, leaving a
    # 9- or 10-digit mobile subscriber number beginning with 9. Myanmar is the
    # default market; callers can still force Vietnam with a VN country hint.
    if digits.startswith("9") and len(digits) in {9, 10}:
        country_code = "84" if country_hint == "VN" else "95"
        return f"+{country_code}{digits}"
    return digits


def _country_hint(value: str) -> str:
    normalized = re.sub(r"[\s:_-]+", " ", value.strip().casefold())
    if re.match(r"^(vn|viet\s*nam|vietnam)\b", normalized):
        return "VN"
    if re.match(r"^(mm|myanmar|burma|burmese)\b", normalized):
        return "MM"
    return ""
