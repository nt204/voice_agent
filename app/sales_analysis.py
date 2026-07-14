import re
import unicodedata
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

COMBO_CATALOG = {
    1: {
        "name": "Venus BigOne Combo 1",
        "quantity": 1,
        "unit_price": 120000,
        "total_price": 120000,
    },
    2: {
        "name": "Venus BigOne Combo 2",
        "quantity": 2,
        "unit_price": 105000,
        "total_price": 210000,
    },
    3: {
        "name": "Venus BigOne Combo 3",
        "quantity": 3,
        "unit_price": 130000,
        "total_price": 390000,
    },
    5: {
        "name": "Venus BigOne Combo 5",
        "quantity": 5,
        "unit_price": 126000,
        "total_price": 630000,
    },
}

MISSING_ORDER_FIELDS = ("product_name", "quantity", "customer_phone", "shipping_address")
EXTRA_DIGITS = str.maketrans(
    "۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩၀၁၂۳۴۵۶۷۸۹",
    "012345678901234567890123456789",
)
EXTRA_DIGITS = str.maketrans(
    {
        **{ord(char): str(index) for index, char in enumerate("\u06f0\u06f1\u06f2\u06f3\u06f4\u06f5\u06f6\u06f7\u06f8\u06f9")},
        **{ord(char): str(index) for index, char in enumerate("\u0660\u0661\u0662\u0663\u0664\u0665\u0666\u0667\u0668\u0669")},
        **{ord(char): str(index) for index, char in enumerate("\u1040\u1041\u1042\u1043\u1044\u1045\u1046\u1047\u1048\u1049")},
    }
)
NUMBER_WORDS = {
    "mot": 1,
    "one": 1,
    "hai": 2,
    "two": 2,
    "ba": 3,
    "three": 3,
    "bon": 4,
    "tu": 4,
    "four": 4,
    "nam": 5,
    "five": 5,
    "တစ်": 1,
    "နှစ်": 2,
    "သုံး": 3,
    "လေး": 4,
    "ငါး": 5,
}


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


def _fold_text(value: str) -> str:
    normalized = unicodedata.normalize("NFD", _normalize_digits(value))
    without_marks = "".join(char for char in normalized if unicodedata.category(char) != "Mn")
    return without_marks.replace("đ", "d").replace("Đ", "D").casefold()


def _contains_any(text: str, tokens: tuple[str, ...]) -> bool:
    return any(token in text for token in tokens)


def _number_value(value: str | None) -> int | None:
    if not value:
        return None
    normalized = _fold_text(value).strip()
    if normalized.isdigit():
        parsed = int(normalized)
        return parsed if parsed > 0 else None
    return NUMBER_WORDS.get(normalized)


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
        r"(?:လိပ်စာ|ပို့ရမယ့်လိပ်စာ|ပို့ရန်လိပ်စာ|နေရပ်လိပ်စာ|ပို့ပေးရမယ့်နေရာ|နေရာ)\s*(?:က|မှာ|သည်|:)?\s*(.+?)(?=[။;]|\s*(?:ဖုန်း|ဝယ်ချင်|လိုချင်|မှာမယ်|မှာယူမယ်)|$)",
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
    for word, value in NUMBER_WORDS.items():
        if re.search(rf"{word}\s*(?:ဘူး|ဗူး|hop|bo|box)", text, flags=re.IGNORECASE):
            return value
    folded = _fold_text(text)
    number_pattern = r"(\d+|mot|hai|ba|bon|tu|nam|one|two|three|four|five)"
    patterns = (
        rf"\b{number_pattern}\s*(?:hop|bo|box|combo)\b",
        rf"\b(?:toi\s+)?(?:mua|dat|lay|chot|order|buy|purchase)\s+{number_pattern}\b",
    )
    for pattern in patterns:
        match = re.search(pattern, folded, flags=re.IGNORECASE)
        if match:
            value = _number_value(match.group(1))
            if value:
                return value
    combo = _extract_combo(text)
    if combo and _has_buy_intent(text):
        return int(combo["quantity"])
    return None


def _has_buy_intent(text: str) -> bool:
    if _contains_any(
        text,
        (
            "ဝယ်ချင်",
            "ဝယ်မယ်",
            "ဝယ်ယူမယ်",
            "ယူမယ်",
            "ယူချင်",
            "မှာမယ်",
            "မှာယူမယ်",
            "မှာချင်",
            "အော်ဒါ",
        ),
    ):
        return True
    folded = _fold_text(text)
    return bool(re.search(r"\b(?:mua|dat|lay|chot|order|buy|purchase)\b", folded, flags=re.IGNORECASE))


def _extract_combo(text: str) -> dict[str, Any] | None:
    normalized = _normalize_digits(text)
    myanmar_match = re.search(
        r"(?:ကွန်ဘို|combo)\s*(?:နံပါတ်|အမှတ်|#|no\.?)?\s*([0-9]+|တစ်|နှစ်|သုံး|လေး|ငါး)",
        normalized,
        flags=re.IGNORECASE,
    )
    if myanmar_match:
        combo_number = _number_value(myanmar_match.group(1))
        if combo_number:
            return COMBO_CATALOG.get(combo_number)

    folded = _fold_text(text)
    number_pattern = r"(\d+|mot|hai|ba|bon|tu|nam|one|two|three|four|five)"
    match = re.search(rf"\bcombo\s*(?:so|number|#)?\s*{number_pattern}\b", folded)
    if not match:
        match = re.search(r"Combo\s*([0-9]+)", _normalize_digits(text), flags=re.IGNORECASE)
    if not match:
        return None
    combo_number = _number_value(match.group(1))
    if not combo_number:
        return None
    return COMBO_CATALOG.get(combo_number)


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
            "ဈေးကြီး",
            "စျေးကြီး",
            "စျေးမြင့်",
            "ဈေးမြင့်",
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
    if _contains_any(
        text,
        (
            "မလိုချင်",
            "မဝယ်ချင်",
            "မလိုအပ်",
            "မလိုဘူး",
            "မလိုပါ",
            "မယူတော့",
            "မမှာတော့",
            "စိတ်မဝင်စား",
            "စိတ်မပါ",
        ),
    ):
        return "no_need"
    if re.search(
        r"\b(?:khong can|khong muon|khong quan tam|chua co nhu cau|not interested|no need)\b",
        text,
        flags=re.IGNORECASE,
    ):
        return "no_need"
    if _has_buy_intent(text):
        return "ready_to_order"
    if _contains_any(text, ("စဉ်းစား", "စဥ်းစား", "မသေချာ", "တိုင်ပင်", "ဆုံးဖြတ်")):
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


def analyze_call(transcript: list[dict[str, Any]], fallback_phone: str = "") -> dict[str, Any]:
    text = _customer_text(transcript)
    phone = _extract_phone(text) or fallback_phone
    address = _extract_address(text)
    quantity = _extract_quantity(text)
    combo = _extract_combo(text)
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
        product_name = combo["name"] if combo else product["name"] if product else ""
        quantity = int(combo["quantity"]) if combo and not quantity else quantity
        unit_price = int(combo["unit_price"]) if combo else int(product["unit_price"]) if product else 0
        total_price = int(combo["total_price"]) if combo else unit_price * (quantity or 0)
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
            "total_price": total_price,
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
