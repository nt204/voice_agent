import re
from typing import Any


PRODUCT_CATALOG = {
    "venus bigone": {
        "name": "Venus BigOne",
        "unit_price": 120000,
        "aliases": (
            "venus bigone",
            "venus",
            "bigone",
            "နို့မှုန့်",
            "နို့်မှုန့်",
        ),
    }
}

MISSING_ORDER_FIELDS = ("product_name", "quantity", "customer_phone", "shipping_address")
EXTRA_DIGITS = str.maketrans(
    "۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩၀၁၂۳۴۵۶۷۸۹",
    "012345678901234567890123456789",
)


def _customer_text(transcript: list[dict[str, Any]]) -> str:
    return " ".join(
        item.get("text", "").strip()
        for item in transcript
        if item.get("speaker") == "customer" and item.get("text", "").strip()
    )


def _clean(value: str) -> str:
    cleaned = value.strip(" \t\r\n,.;:-။၊")
    return re.sub(r"\s*(?:ပါရှင်|ပါတယ်|ပါ)$", "", cleaned).rstrip()


def _normalize_digits(value: str) -> str:
    return value.translate(EXTRA_DIGITS)


def _contains_any(text: str, tokens: tuple[str, ...]) -> bool:
    return any(token in text for token in tokens)


def _extract_phone(text: str) -> str:
    match = re.search(
        r"(?:phone|ဖုန်းနံပါတ်|ဖုန်း|dien thoai|so dien thoai)?\s*"
        r"(?:la|is|က|မှာ|သည်|:)?\s*"
        r"(\+?[\d۰-۹٠-٩၀-၉][\d۰-۹٠-٩۰-۹ .-]{7,}[\d۰-۹٠-٩۰-۹])",
        text,
        flags=re.IGNORECASE,
    )
    if not match:
        return ""
    return _normalize_digits(re.sub(r"[\s.-]+", "", match.group(1)))


def _extract_address(text: str) -> str:
    patterns = (
        r"လိပ်စာ\s*(?:က|မှာ|သည်|:)?\s*(.+?)(?=[။;]|\s*(?:ဖုန်း|ဝယ်ချင်|လိုချင်|မှာမယ်)|$)",
        r"(?:address|dia chi)\s*(?:la|is|:)?\s*(.+?)(?=[.;]|\s+(?:phone|so dien thoai|toi muon|toi can)\b|$)",
    )
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return _clean(match.group(1))
    return ""


def _extract_quantity(text: str) -> int | None:
    match = re.search(r"([\d۰-۹٠-٩۰-۹]+)\s*(?:ဘူး|ဗူး|hop|bo|box)", text, flags=re.IGNORECASE)
    if match:
        return int(_normalize_digits(match.group(1)))
    for word, value in {
        "mot": 1,
        "hai": 2,
        "ba": 3,
        "bon": 4,
        "nam": 5,
        "တစ်": 1,
        "နှစ်": 2,
        "သုံး": 3,
        "လေး": 4,
        "ငါး": 5,
    }.items():
        if re.search(rf"{word}\s*(?:ဘူး|ဗူး|hop|bo|box)", text, flags=re.IGNORECASE):
            return value
    return None


def _has_buy_intent(text: str) -> bool:
    if _contains_any(text, ("ဝယ်ချင်", "ဝယ်မယ်", "ယူမယ်", "မှာမယ်", "အော်ဒါ")):
        return True
    return bool(re.search(r"\b(?:mua|dat|lay|chot|order|buy|purchase)\b", text, flags=re.IGNORECASE))


def _extract_product(text: str) -> dict[str, Any] | None:
    folded = text.casefold()
    for product in PRODUCT_CATALOG.values():
        if any(alias.casefold() in folded for alias in product["aliases"]):
            return product
    if _has_buy_intent(text):
        return PRODUCT_CATALOG["venus bigone"]
    return None


def _extract_age_range(text: str) -> tuple[str, float]:
    match = re.search(
        r"(?:အသက်|age|tuoi)\s*(?:က|မှာ|သည်|la|is|:)?\s*([\d۰-۹٠-٩۰-۹]{1,2})|"
        r"([\d۰-۹٠-٩۰-۹]{1,2})\s*(?:tuoi|years? old|နှစ်)",
        text,
        flags=re.IGNORECASE,
    )
    if not match:
        return "unknown", 0.0
    age = int(_normalize_digits(next(group for group in match.groups() if group)))
    if age < 18:
        return "under_18", 0.95
    if age <= 24:
        return "18-24", 0.95
    if age <= 34:
        return "25-34", 0.95
    if age <= 44:
        return "35-44", 0.95
    if age <= 54:
        return "45-54", 0.95
    return "55+", 0.95


def _extract_gender(text: str) -> tuple[str, float]:
    if _contains_any(text, ("အမျိုးသမီး", "female", "woman")):
        return "female", 0.95
    if _contains_any(text, ("အမျိုးသား", "male", "man")):
        return "male", 0.95
    return "unknown", 0.0


def _extract_objection(text: str) -> str:
    if _contains_any(
        text,
        (
            "ဈေးနည်းနည်းများ",
            "စျေးနည်းနည်းများ",
            "ဈေးများ",
            "စျေးများ",
        ),
    ):
        return "price"
    if re.search(
        r"\b(?:gia cao|dat qua|hoi dat|too expensive|price is high|expensive)\b",
        text,
        flags=re.IGNORECASE,
    ):
        return "price"
    return "unknown"


def _intent_status(text: str, *, quantity: int | None, phone: str, address: str) -> str:
    if _contains_any(text, ("မလိုချင်", "မဝယ်ချင်", "မလိုအပ်", "စိတ်မဝင်စား")):
        return "no_need"
    if re.search(
        r"\b(?:khong can|khong muon|khong quan tam|chua co nhu cau|not interested|no need)\b",
        text,
        flags=re.IGNORECASE,
    ):
        return "no_need"
    if _has_buy_intent(text) and (quantity or phone or address):
        return "ready_to_order"
    if _contains_any(text, ("စဉ်းစား", "မသေချာ", "တိုင်ပင်", "ဆုံးဖြတ်")):
        return "considering"
    if re.search(
        r"\b(?:phan van|suy nghi|can nhac|hoi nguoi nha|chua chac|thinking|considering|not sure)\b",
        text,
        flags=re.IGNORECASE,
    ):
        return "considering"
    if _contains_any(text, ("သောက်နည်း", "ဘေးထွက်", "သိချင်", "မေးချင်", "အကြံ", "စိတ်ဝင်စား")):
        return "needs_consultation"
    if re.search(
        r"\b(?:tu van|cach dung|an toan|hieu qua|quan tam|advise|consult|interested)\b",
        text,
        flags=re.IGNORECASE,
    ):
        return "needs_consultation"
    if _contains_any(text, ("ဈေး", "စျေး", "ဘယ်လောက်", "combo", "Combo")):
        return "price_checking"
    if re.search(r"\b(?:gia|bao nhieu|phi ship|price|how much|combo)\b", text, flags=re.IGNORECASE):
        return "price_checking"
    return "unknown"


def analyze_call(transcript: list[dict[str, Any]]) -> dict[str, Any]:
    text = _customer_text(transcript)
    phone = _extract_phone(text)
    address = _extract_address(text)
    quantity = _extract_quantity(text)
    product = _extract_product(text)
    age_range, age_confidence = _extract_age_range(text)
    gender, gender_confidence = _extract_gender(text)
    objection = _extract_objection(text)
    intent_status = _intent_status(text, quantity=quantity, phone=phone, address=address)

    customer = {
        "name": "",
        "phone": phone,
        "address": address,
        "need": text[:240],
        "gender": gender,
        "gender_confidence": gender_confidence,
        "age_range": age_range,
        "age_confidence": age_confidence,
    }

    order = None
    if intent_status == "ready_to_order":
        product_name = product["name"] if product else ""
        unit_price = int(product["unit_price"]) if product else 0
        missing_fields = []
        if not product_name:
            missing_fields.append("product_name")
        if not quantity:
            missing_fields.append("quantity")
        if not phone:
            missing_fields.append("customer_phone")
        if not address:
            missing_fields.append("shipping_address")
        status = "ready_to_confirm" if not missing_fields else "missing_info"
        order = {
            "customer_phone": phone,
            "customer_name": "",
            "shipping_address": address,
            "product_name": product_name,
            "quantity": quantity or 0,
            "unit_price": unit_price,
            "total_price": unit_price * (quantity or 0),
            "status": status,
            "missing_fields": missing_fields,
            "confidence": 0.9 if status == "ready_to_confirm" else 0.65,
        }

    urgency = (
        "high"
        if intent_status == "ready_to_order"
        else "medium"
        if intent_status in {"considering", "needs_consultation"}
        else "low"
    )
    confidence = 0.88 if intent_status in {"ready_to_order", "no_need"} else 0.72 if intent_status != "unknown" else 0.3
    next_action = {
        "ready_to_order": "Kiem tra don nhap va xac nhan lai voi khach.",
        "needs_consultation": "Tu van them ve cach dung, an toan va loi ich chinh.",
        "considering": "Goi lai nhe nhang va xu ly ly do khach con phan van.",
        "price_checking": "Gui gia, combo va uu dai phu hop.",
        "no_need": "Dua vao nhom cham soc lai, khong goi don.",
    }.get(intent_status, "Ra lai transcript de xac dinh buoc tiep theo.")

    return {
        "customer": customer,
        "analysis": {
            "intent_status": intent_status,
            "sentiment": "neutral",
            "urgency": urgency,
            "objection": objection,
            "summary": text[:300] if text else "Chua co du noi dung khach hang.",
            "next_action": next_action,
            "confidence": confidence,
        },
        "order": order,
    }
