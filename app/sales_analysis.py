import re
from typing import Any


PRODUCT_CATALOG = {
    "venus bigone": {
        "name": "Venus BigOne",
        "unit_price": 120000,
        "aliases": ("venus bigone", "venus", "bigone", "နို့မှုန့်"),
    }
}

MISSING_ORDER_FIELDS = ("product_name", "quantity", "customer_phone", "shipping_address")
EXTRA_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
MYANMAR_DIGITS = str.maketrans("၀၁၂၃၄၅၆၇၈၉", "0123456789")


def _customer_text(transcript: list[dict[str, Any]]) -> str:
    return " ".join(
        item.get("text", "").strip()
        for item in transcript
        if item.get("speaker") == "customer" and item.get("text", "").strip()
    )


def _clean(value: str) -> str:
    return value.strip(" \t\r\n,.;:-။၊")


def _normalize_digits(value: str) -> str:
    return value.translate(MYANMAR_DIGITS).translate(EXTRA_DIGITS)


def _extract_phone(text: str) -> str:
    match = re.search(
        r"(?:số điện thoại|điện thoại|phone|ဖုန်းနံပါတ်|ဖုန်း)?\s*(?:là|:|က|မှာ|သည်)?\s*(\+?\d[\d .-]{7,}\d)",
        text,
        flags=re.IGNORECASE,
    )
    if not match:
        return ""
    return _normalize_digits(re.sub(r"[\s.-]+", "", match.group(1)))


def _extract_address(text: str) -> str:
    myanmar_match = re.search(
        r"လိပ်စာ\s*(?:က|မှာ|သည်|:)?\s*(.+?)(?=[။;]|\s*(?:ဖုန်း|ဝယ်ချင်|လိုချင်|မှာမယ်)|$)",
        text,
    )
    if myanmar_match:
        return _clean(myanmar_match.group(1))
    patterns = (
        r"(?:địa chỉ|address)\s*(?:là|:)?\s*(.+?)(?=[.;]|\s+(?:tôi muốn|tôi cần|số điện thoại|điện thoại|phone)\b|$)",
        r"လိပ်စာ\s*(?:က|မှာ|သည်|:)?\s*(.+?)(?=[။;]|\s*(?:ဖုန်း|ဝယ်ချင်|လိုချင်)|$)",
    )
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return _clean(match.group(1))
    return ""


def _extract_quantity(text: str) -> int | None:
    vietnamese_match = re.search(r"(\d+)\s*(?:hộp|bộ)\b", text, flags=re.IGNORECASE)
    if vietnamese_match:
        return int(vietnamese_match.group(1))
    for word, value in {"một": 1, "hai": 2, "ba": 3, "bốn": 4, "năm": 5}.items():
        if re.search(rf"\b{word}\s+(?:hộp|bộ)\b", text, flags=re.IGNORECASE):
            return value
    myanmar_match = re.search(r"(\d+)\s*(?:ဘူး|ဗူး)", text)
    if myanmar_match:
        return int(_normalize_digits(myanmar_match.group(1)))
    vietnamese_number_words = {
        "một": 1,
        "hai": 2,
        "ba": 3,
        "bốn": 4,
        "bon": 4,
        "năm": 5,
        "nam": 5,
    }
    match = re.search(r"(\d+)\s*(?:hộp|hop|bộ|bo|bူး|ဗူး)", text, flags=re.IGNORECASE)
    if match:
        return int(match.group(1))
    for word, value in vietnamese_number_words.items():
        if re.search(rf"\b{word}\s+(?:hộp|hop|bộ|bo)\b", text, flags=re.IGNORECASE):
            return value
    myanmar_digits = {"၁": 1, "၂": 2, "၃": 3, "၄": 4, "၅": 5}
    for digit, value in myanmar_digits.items():
        if re.search(rf"{digit}\s*(?:ဘူး|ဗူး)", text):
            return value
    return None


def _extract_product(text: str) -> dict[str, Any] | None:
    folded = text.casefold()
    for product in PRODUCT_CATALOG.values():
        if any(alias in folded for alias in product["aliases"]):
            return product
    if _has_buy_intent(text):
        return PRODUCT_CATALOG["venus bigone"]
    return None


def _extract_age_range(text: str) -> tuple[str, float]:
    myanmar_match = re.search(r"အသက်\s*(?:က|မှာ|သည်|:)?\s*([၀-၉0-9]{1,2})", text)
    if myanmar_match:
        age = int(_normalize_digits(myanmar_match.group(1)))
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
    ascii_match = re.search(
        r"(?:tuoi|age)\s*(?:la|is|:)?\s*(\d{1,2})|(\d{1,2})\s*(?:tuoi|years? old)",
        text,
        flags=re.IGNORECASE,
    )
    if ascii_match:
        age = int(next(group for group in ascii_match.groups() if group))
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
    match = re.search(r"(?:tuổi|အသက်)\s*(?:là|:)?\s*(\d{1,2})|(\d{1,2})\s*(?:tuổi|နှစ်)", text, flags=re.IGNORECASE)
    if not match:
        return "unknown", 0.0
    age = int(next(group for group in match.groups() if group))
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
    if "အမျိုးသမီး" in text:
        return "female", 0.95
    if "အမျိုးသား" in text:
        return "male", 0.95
    if re.search(r"\b(?:tôi là nữ|chị là nữ|em là nữ|female|woman)\b|အမျိုးသမီး", text, flags=re.IGNORECASE):
        return "female", 0.95
    if re.search(r"\b(?:tôi là nam|anh là nam|male|man)\b|အမျိုးသား", text, flags=re.IGNORECASE):
        return "male", 0.95
    return "unknown", 0.0


def _has_buy_intent(text: str) -> bool:
    if any(token in text for token in ("ဝယ်ချင်", "ယူမယ်", "မှာမယ်", "အော်ဒါ")):
        return True
    if re.search(r"\b(?:dat|lay|chot|buy|purchase)\b", text, flags=re.IGNORECASE):
        return True
    patterns = (
        r"\b(?:mua|đặt|lấy|chốt|order)\b",
        r"ဝယ်ချင်",
        r"ယူမယ်",
        r"မှာမယ်",
        r"အော်ဒါ",
    )
    return any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in patterns)


def _intent_status(text: str, *, quantity: int | None, phone: str, address: str) -> str:
    if any(token in text for token in ("မလိုချင်", "မဝယ်ချင်", "မလိုအပ်", "စိတ်မဝင်စား")):
        return "no_need"
    if re.search(
        r"\b(?:khong can|khong muon|khong quan tam|chua co nhu cau|chua can|no need|not interested)\b",
        text,
        flags=re.IGNORECASE,
    ):
        return "no_need"
    if re.search(r"\b(?:không cần|không muốn|không quan tâm|chưa có nhu cầu)\b|မလိုချင်|မဝယ်ချင်", text, flags=re.IGNORECASE):
        return "no_need"
    if _has_buy_intent(text) and (quantity or phone or address):
        return "ready_to_order"
    if any(token in text for token in ("စဉ်းစား", "မသေချာ", "စိတ်ဝင်စားပေမယ့်")):
        return "considering"
    if re.search(
        r"\b(?:phan van|suy nghi|can nhac|hoi nguoi nha|chua chac|thinking|considering|not sure)\b",
        text,
        flags=re.IGNORECASE,
    ):
        return "considering"
    if re.search(r"\b(?:gia|bao nhieu|phi ship|price|how much)\b", text, flags=re.IGNORECASE):
        return "price_checking"
    if any(token in text for token in ("အကြံ", "သိချင်", "မေးချင်", "စိတ်ဝင်စား")):
        return "needs_consultation"
    if re.search(
        r"\b(?:tu van|cach dung|dung the nao|an toan|hieu qua|quan tam|advise|consult|how to use|interested)\b",
        text,
        flags=re.IGNORECASE,
    ):
        return "needs_consultation"
    if re.search(r"\b(?:phân vân|suy nghĩ|cân nhắc|hỏi người nhà|chưa chắc)\b", text, flags=re.IGNORECASE):
        return "considering"
    if re.search(r"\b(?:giá|bao nhiêu|combo|phí ship)\b|ဈေး|စျေး", text, flags=re.IGNORECASE):
        return "price_checking"
    if re.search(r"\b(?:tư vấn|cách dùng|dùng thế nào|an toàn|hiệu quả|quan tâm)\b|အကြံဉာဏ်", text, flags=re.IGNORECASE):
        return "needs_consultation"
    return "unknown"


def analyze_call(transcript: list[dict[str, Any]]) -> dict[str, Any]:
    text = _customer_text(transcript)
    phone = _extract_phone(text)
    address = _extract_address(text)
    quantity = _extract_quantity(text)
    product = _extract_product(text)
    age_range, age_confidence = _extract_age_range(text)
    gender, gender_confidence = _extract_gender(text)
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
        order_confidence = 0.9 if status == "ready_to_confirm" else 0.65
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
            "confidence": order_confidence,
        }

    urgency = "high" if intent_status == "ready_to_order" else "medium" if intent_status in {"considering", "needs_consultation"} else "low"
    confidence = 0.88 if intent_status in {"ready_to_order", "no_need"} else 0.72 if intent_status != "unknown" else 0.3
    next_action = {
        "ready_to_order": "Kiểm tra đơn nháp và xác nhận lại với khách.",
        "needs_consultation": "Tư vấn thêm về cách dùng, an toàn và lợi ích chính.",
        "considering": "Gọi lại nhẹ nhàng, xử lý lý do khách còn phân vân.",
        "price_checking": "Gửi giá, combo và ưu đãi phù hợp.",
        "no_need": "Đưa vào nhóm chăm sóc lại, không gọi dồn.",
    }.get(intent_status, "Rà lại transcript để xác định bước tiếp theo.")

    analysis = {
        "intent_status": intent_status,
        "sentiment": "neutral",
        "urgency": urgency,
        "objection": "unknown",
        "summary": text[:300] if text else "Chưa có đủ nội dung khách hàng.",
        "next_action": next_action,
        "confidence": confidence,
    }

    return {
        "customer": customer,
        "analysis": analysis,
        "order": order,
    }
