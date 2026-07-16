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
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "တစ်": 1,
    "နှစ်": 2,
    "သုံး": 3,
    "လေး": 4,
    "ငါး": 5,
}
PHONE_DIGIT_WORDS = {
    "zero": "0",
    "oh": "0",
    "o": "0",
    "သုည": "0",
    "ဝ": "0",
    "one": "1",
    "တစ်": "1",
    "တစ္": "1",
    "two": "2",
    "နှစ်": "2",
    "နစ်": "2",
    "three": "3",
    "သုံး": "3",
    "four": "4",
    "လေး": "4",
    "five": "5",
    "ငါး": "5",
    "six": "6",
    "ခြောက်": "6",
    "seven": "7",
    "ခုနစ်": "7",
    "ခုနှစ်": "7",
    "eight": "8",
    "ရှစ်": "8",
    "nine": "9",
    "ကိုး": "9",
}
PHONE_DIGIT_WORD_ITEMS = sorted(
    PHONE_DIGIT_WORDS.items(),
    key=lambda item: len(item[0]),
    reverse=True,
)
NON_MYANMAR_ADDRESS_PATTERNS = (
    r"\b(?:viet\s*nam|vietnam|ha\s*noi|hanoi|ho\s*chi\s*minh|hcmc?|tp\.?\s*hcm|"
    r"saigon|sai\s*gon|da\s*nang|hai\s*phong|can\s*tho|nha\s*trang|hue|"
    r"vung\s*tau|binh\s*duong|dong\s*nai)\b",
    r"\b(?:nguyen|tran|le\s+loi|dien\s+bien\s+phu|duong|quan|phuong)\b",
    r"\b(?:bangkok|thailand|singapore|malaysia|kuala\s*lumpur|philippines|"
    r"indonesia|india|china|beijing|shanghai|laos|cambodia|japan|korea|"
    r"usa|united\s+states|canada|australia|london|uk|united\s+kingdom)\b",
)
NON_MYANMAR_ADDRESS_TOKENS = (
    "ဗီယက်နမ်",
    "ဟနွိုင်း",
    "ဟိုချီမင်း",
    "ထိုင်း",
    "ဘန်ကောက်",
    "စင်ကာပူ",
    "မလေးရှား",
    "တရုတ်",
    "အိန္ဒိယ",
    "ဂျပန်",
    "ကိုရီးယား",
)


def _customer_text(transcript: list[dict[str, Any]]) -> str:
    return " ".join(
        item.get("text", "").strip()
        for item in transcript
        if item.get("speaker") == "customer" and item.get("text", "").strip()
    )


def _customer_turns(transcript: list[dict[str, Any]]) -> list[str]:
    return [
        item.get("text", "").strip()
        for item in transcript
        if item.get("speaker") == "customer" and item.get("text", "").strip()
    ]


def _clean(value: str) -> str:
    cleaned = value.strip(" \t\r\n,.;:-။၊")
    return re.sub(r"\s*(?:ပါရှင်|ပါတယ်|ပါ)$", "", cleaned).rstrip()


def _normalize_digits(value: str) -> str:
    return value.translate(EXTRA_DIGITS)


def _normalize_phone_candidate(value: str) -> str:
    cleaned = _normalize_digits(value).strip()
    prefix = "+" if cleaned.startswith("+") else ""
    digits = re.sub(r"\D", "", cleaned)
    if not _is_myanmar_phone_digits(digits, has_plus=bool(prefix)):
        return ""
    return f"{prefix}{digits}"


def _is_ascii_word_boundary(text: str, start: int, end: int) -> bool:
    before_ok = start == 0 or not text[start - 1].isalnum()
    after_ok = end >= len(text) or not text[end].isalnum()
    return before_ok and after_ok


def _spoken_phone_digits(value: str) -> str:
    text = _normalize_digits(value).casefold().strip(" \t\r\n,.;:-။၊")
    text = re.sub(r"\s*(?:ပါရှင်|ပါတယ်|ပါ)$", "", text).strip(" \t\r\n,.;:-။၊")
    if not text:
        return ""

    digits: list[str] = []
    index = 0
    while index < len(text):
        separator = re.match(r"[\s,.;:၊။\-_/()+]+", text[index:])
        if separator:
            index += separator.end()
            continue

        char = text[index]
        if char.isdigit():
            digits.append(char)
            index += 1
            continue

        matched = False
        for word, digit in PHONE_DIGIT_WORD_ITEMS:
            end = index + len(word)
            if not text.startswith(word, index):
                continue
            if word.isascii() and not _is_ascii_word_boundary(text, index, end):
                continue
            digits.append(digit)
            index = end
            matched = True
            break
        if matched:
            continue

        return ""

    return "".join(digits) if len(digits) >= 8 else ""


def _spoken_phone_candidate(value: str) -> str:
    digits = _spoken_phone_digits(value)
    return _normalize_phone_candidate(digits) if digits else ""


def _spoken_phone_from_text(text: str) -> str:
    normalized = _normalize_digits(text)
    phone_label = r"(?:phone|mobile|ဖုန်းနံပါတ်|ဖုန်း)"
    for match in re.finditer(
        phone_label
        + r"\s*(?:number|နံပါတ်|is|က|မှာ|သည်|:)?\s*"
        + r"(.+?)(?=[။;.]|\s*(?:လိပ်စာ|address|delivery|ship|ပို့|ဝယ်ချင်|လိုချင်|မှာမယ်|မှာယူမယ်)\b|$)",
        normalized,
        flags=re.IGNORECASE,
    ):
        candidate = _spoken_phone_candidate(match.group(1))
        if candidate:
            return candidate

    stripped = normalized.strip()
    if stripped:
        return _spoken_phone_candidate(stripped)
    return ""


def _is_myanmar_phone_digits(digits: str, *, has_plus: bool = False) -> bool:
    if has_plus:
        return digits.startswith("959") and 10 <= len(digits) <= 12
    return (
        digits.startswith("09")
        and 9 <= len(digits) <= 11
    ) or (
        digits.startswith("959")
        and 10 <= len(digits) <= 12
    )


def _fold_text(value: str) -> str:
    normalized = unicodedata.normalize("NFD", _normalize_digits(value))
    without_marks = "".join(char for char in normalized if unicodedata.category(char) != "Mn")
    return without_marks.replace("đ", "d").replace("Đ", "D").casefold()


def _contains_any(text: str, tokens: tuple[str, ...]) -> bool:
    return any(token in text for token in tokens)


def _is_clearly_non_myanmar_address(value: str) -> bool:
    cleaned = _clean(value)
    if not cleaned:
        return False
    folded = _fold_text(cleaned)
    if _contains_any(cleaned, NON_MYANMAR_ADDRESS_TOKENS):
        return True
    return any(re.search(pattern, folded, flags=re.IGNORECASE) for pattern in NON_MYANMAR_ADDRESS_PATTERNS)


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
        r"(?:phone|mobile|ဖုန်းနံပါတ်|ဖုန်း)?\s*"
        r"(?:is|က|မှာ|သည်|:)?\s*"
        r"(\+?[\d۰-۹٠-٩၀-၉][\d۰-۹٠-٩۰-۹ .-]{7,}[\d۰-۹٠-٩۰-۹])",
        text,
        flags=re.IGNORECASE,
    )
    if not match:
        return ""
    return _normalize_digits(re.sub(r"[\s.-]+", "", match.group(1)))


def _extract_phone_precise(text: str) -> str:
    normalized = _normalize_digits(text)
    phone_label = (
        r"(?:phone|mobile|ဖုန်းနံပါတ်|ဖုန်း)"
    )
    label_match = re.search(
        phone_label
        + r"\s*(?:is|က|မှာ|သည်|:)?\s*"
        + r"(\+?\d[\d .-]{7,}\d)",
        normalized,
        flags=re.IGNORECASE,
    )
    if label_match:
        candidate = _normalize_phone_candidate(label_match.group(1))
        if candidate:
            return candidate

    spoken_candidate = _spoken_phone_from_text(normalized)
    if spoken_candidate:
        return spoken_candidate

    stripped = normalized.strip()
    if re.fullmatch(r"\+?[\d .-]+", stripped):
        candidate = _normalize_phone_candidate(stripped)
        if candidate:
            return candidate

    for match in re.finditer(r"\+?\d{8,15}", normalized):
        candidate = _normalize_phone_candidate(match.group(0))
        if candidate:
            return candidate

    return ""


def _extract_phone_from_turns(turns: list[str]) -> str:
    for turn in reversed(turns):
        phone = _extract_phone_precise(turn)
        if phone:
            return phone
    return _extract_phone_precise(" ".join(turns))


def _extract_name_from_turn(turn: str) -> str:
    patterns = (
        r"(?:recipient name|customer name|my name|name)\s*(?:is|:)?\s*(.+)",
        r"(?:လက်ခံမယ့်နာမည်|လက်ခံမည့်နာမည်|ပစ္စည်းလက်ခံမယ့်နာမည်|နာမည်|အမည်)\s*(?:ကို|က|မှာ|သည်|:)?\s*(.+)",
    )
    for pattern in patterns:
        match = re.search(pattern, turn, flags=re.IGNORECASE)
        if not match:
            continue
        name = _clean(match.group(1))
        name = re.split(
            r"\b(?:phone|mobile|address|ship|delivery)\b|(?:ဖုန်းနံပါတ်|ဖုန်း|လိပ်စာ|ပို့ရန်|ပို့ရမယ့်)",
            name,
            maxsplit=1,
            flags=re.IGNORECASE,
        )[0].strip(" \t\r\n,.;:-")
        name = re.split(r"(?:လို့|ဟု)", name, maxsplit=1)[0].strip(" \t\r\n,.;:-။၊")
        folded_name = _fold_text(name)
        if (
            2 <= len(name) <= 80
            and re.search(r"[A-Za-zÀ-ỹ\u1000-\u109F]", name)
            and not re.search(r"\d", _normalize_digits(name))
            and folded_name not in {"name", "my name", "phone", "address"}
            and not re.search(
                r"\b(?:combo|box|boxes|kyat|buy|order|purchase|phone|address|delivery)\b|"
                r"(?:ကွန်ဘို|ဘူး|ဗူး|ကျပ်|ဝယ်|မှာ|ယူ|ဖုန်း|လိပ်စာ)",
                folded_name,
            )
            and not re.search(
                r"(?:ကွန်ဘို|ဘူး|ဗူး|ကျပ်|ဝယ်|မှာ|ယူ|ဖုန်း|လိပ်စာ|ဟုတ်|မှန်|မလို|အော်ဒါ)",
                name,
            )
        ):
            return name
    return ""


def _is_valid_customer_name(name: str) -> bool:
    cleaned = _clean(name)
    folded_name = _fold_text(cleaned)
    return bool(
        2 <= len(cleaned) <= 80
        and re.search(r"[A-Za-zÀ-ỹ\u1000-\u109F]", cleaned)
        and not re.search(r"\d", _normalize_digits(cleaned))
        and folded_name not in {"name", "my name", "phone", "address"}
        and not re.search(
            r"\b(?:combo|box|boxes|kyat|buy|order|purchase|phone|address|delivery|"
            r"yes|ok|correct|confirm|no|need|street|road|township)\b|"
            r"(?:ကွန်ဘို|ဘူး|ဗူး|ကျပ်|ဝယ်|မှာ|ယူ|ဖုန်း|လိပ်စာ|လမ်း|မြို့နယ်|ဟုတ်|မှန်|မလို)",
            folded_name,
        )
        and not re.search(
            r"(?:ကွန်ဘို|ဘူး|ဗူး|ကျပ်|ဝယ်|မှာ|ယူ|ဖုန်း|လိပ်စာ|လမ်း|မြို့နယ်|ဟုတ်|မှန်|မလို|အော်ဒါ)",
            cleaned,
        )
    )


def _extract_customer_name(turns: list[str]) -> str:
    for turn in reversed(turns):
        name = _extract_name_from_turn(turn)
        if name:
            return name
    return ""


def _agent_context_before(transcript: list[dict[str, Any]], index: int, window: int = 30) -> str:
    parts = []
    for item in transcript[max(0, index - window):index]:
        if item.get("speaker") == "agent" and item.get("text", "").strip():
            parts.append(item["text"].strip())
    return " ".join(parts)


def _extract_customer_name_from_transcript(transcript: list[dict[str, Any]]) -> str:
    turns = _customer_turns(transcript)
    explicit_name = _extract_customer_name(turns)
    if explicit_name:
        return explicit_name

    for index in range(len(transcript) - 1, -1, -1):
        item = transcript[index]
        if item.get("speaker") != "customer":
            continue
        candidate = _clean(item.get("text", ""))
        if not _is_valid_customer_name(candidate):
            continue
        raw_context = _agent_context_before(transcript, index)
        context = _fold_text(raw_context)
        if re.search(r"\b(?:name|recipient|customer name)\b", context) or re.search(r"(?:နာမည်|အမည်)", raw_context):
            return candidate
    return ""


def _looks_like_address(value: str) -> bool:
    cleaned = _clean(value)
    folded = _fold_text(cleaned)
    if len(cleaned) < 8:
        return False
    location_tokens = (
        "yangon",
        "mandalay",
        "naypyidaw",
        "township",
        "road",
        "street",
        "ward",
        "lane",
        "ရန်ကုန်",
        "မန္တလေး",
        "နေပြည်တော်",
        "မြို့",
        "မြို့နယ်",
        "လမ်း",
        "ရပ်ကွက်",
        "အမှတ်",
    )
    if _contains_any(folded, location_tokens) or _contains_any(cleaned, location_tokens):
        return True
    return bool(
        re.search(r"\d", _normalize_digits(cleaned))
        and re.search(
            r"\b(?:no|number|room|building|floor|block)\b",
            folded,
        )
    )


def _extract_address(text: str) -> str:
    patterns = (
        r"(?:လိပ်စာ|ပို့ရမယ့်လိပ်စာ|ပို့ရန်လိပ်စာ|နေရပ်လိပ်စာ|ပို့ပေးရမယ့်နေရာ|နေရာ)\s*(?:က|မှာ|သည်|:)?\s*(.+?)(?=[။;]|\s*(?:ဖုန်း|ဝယ်ချင်|လိုချင်|မှာမယ်|မှာယူမယ်)|$)",
        r"(?:address|delivery address)\s*(?:is|:)?\s*(.+?)(?=[.;]|\s+(?:phone|buy|order|purchase)\b|$)",
        r"(?:ship|deliver|delivery)\s*(?:to)?\s+(.+?)(?=[.;]|$)",
        r"\b((?:no\.?|number)\s+\d+.+)$",
    )
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            address = _clean(match.group(1))
            return re.split(
                r"(?:\b(?:age|years?\s+old|female|male|woman|man)\b|အသက်|အမျိုးသမီး|အမျိုးသား)",
                address,
                maxsplit=1,
                flags=re.IGNORECASE,
            )[0].strip(" \t\r\n,.;:-။၊")
    return ""


def _extract_address_from_transcript(transcript: list[dict[str, Any]]) -> str:
    turns = _customer_turns(transcript)
    for turn in reversed(turns):
        explicit_address = _extract_address(turn)
        if explicit_address:
            return "" if _is_clearly_non_myanmar_address(explicit_address) else explicit_address

    for index in range(len(transcript) - 1, -1, -1):
        item = transcript[index]
        if item.get("speaker") != "customer":
            continue
        candidate = _clean(item.get("text", ""))
        if not _looks_like_address(candidate):
            continue
        raw_context = _agent_context_before(transcript, index)
        context = _fold_text(raw_context)
        if re.search(r"\b(?:address|delivery|ship|deliver)\b", context) or re.search(r"(?:လိပ်စာ|ပို့)", raw_context):
            return "" if _is_clearly_non_myanmar_address(candidate) else candidate
    return ""


def _customer_attempted_phone(text: str) -> bool:
    return bool(
        re.search(
            r"(?:ဖုန်းနံပါတ်|ဖုန်း|phone|mobile)",
            text,
            flags=re.IGNORECASE,
        )
    )


def _extract_quantity(text: str) -> int | None:
    match = re.search(r"([\d۰-۹٠-٩۰-۹]+)\s*(?:ဘူး|ဗူး|box|boxes)", text, flags=re.IGNORECASE)
    if match:
        return int(_normalize_digits(match.group(1)))
    for word, value in NUMBER_WORDS.items():
        if re.search(rf"{word}\s*(?:ဘူး|ဗူး|box|boxes)", text, flags=re.IGNORECASE):
            return value
    folded = _fold_text(text)
    number_pattern = r"(\d+|one|two|three|four|five)"
    patterns = (
        rf"\b{number_pattern}\s*(?:box|boxes)\b",
        rf"\b(?:order|buy|purchase|take)\s+{number_pattern}(?!\s*combo\b)",
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


def _has_negated_buy_intent(text: str) -> bool:
    if any(token in text for token in ("မဝယ်", "မယူ", "မမှာ")):
        return True
    folded = _fold_text(text)
    return bool(
        re.search(
            r"\b(?:do\s+not|don't|not|not\s+yet)\s+(?:buy|order|purchase)\b",
            folded,
        )
    )


def _has_buy_intent(text: str) -> bool:
    if _has_negated_buy_intent(text):
        return False
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
    return bool(re.search(r"\b(?:order|buy|purchase|take)\b", folded, flags=re.IGNORECASE))


def _is_question(text: str) -> bool:
    if "?" in text or _contains_any(text, ("ဘယ်လောက်", "သလဲ", "လား", "လဲ")):
        return True
    folded = _fold_text(text)
    return bool(
        re.search(
            r"\b(?:price|how\s+much|what\s+about|which|available)\b",
            folded,
        )
    )


def _is_delivery_order_request(text: str) -> bool:
    return bool(
        re.search(r"\b(?:ship|deliver|delivery)\b", _fold_text(text))
        or _contains_any(text, ("ပို့ပေး", "ပို့ရန်", "ပို့ရမယ့်"))
    )


def _is_retail_selection(text: str) -> bool:
    folded = _fold_text(text)
    return bool(
        re.search(
            r"\b(?:retail|single box|one by one|no combo)\b",
            folded,
        ) or _contains_any(text, ("လက်လီ", "တစ်ဘူးချင်း", "တစ်ဘူးစီ", "ကွန်ဘိုမဟုတ်"))
    )


def _is_no_need(text: str) -> bool:
    if _contains_any(
        text,
        (
            "မလိုချင်",
            "မဝယ်ချင်",
            "မလိုအပ်",
            "မလိုဘူး",
            "မလိုပါ",
            "မဝယ်တော့",
            "မယူတော့",
            "မမှာတော့",
            "အော်ဒါဖျက်",
            "စိတ်မဝင်စား",
            "စိတ်မပါ",
        ),
    ):
        return True
    folded = _fold_text(text)
    return bool(
        re.search(
            r"\b(?:not\s+interested|no\s+need|do\s+not\s+need|do\s+not\s+want)\b",
            folded,
        )
    )


def _is_deferred(text: str) -> bool:
    if _contains_any(text, ("မမှာသေး", "မဝယ်သေး", "စဉ်းစား", "စဥ်းစား", "တိုင်ပင်", "ဆုံးဖြတ်")):
        return True
    folded = _fold_text(text)
    return bool(
        re.search(
            r"\b(?:not\s+yet|thinking|considering|decide\s+later|ask\s+family)\b",
            folded,
        )
    )


def extract_order_selection(transcript: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Return the latest concrete customer commitment, never a product question."""
    pending_generic_intent = False
    selection: dict[str, Any] | None = None

    for turn in _customer_turns(transcript):
        if _is_no_need(turn) or _is_deferred(turn):
            pending_generic_intent = False
            selection = None
            continue

        combo = _extract_combo(turn)
        quantity = _extract_quantity(turn)
        selected_combo = combo or (
            COMBO_CATALOG.get(quantity)
            if quantity in COMBO_CATALOG and quantity != 1 and not _is_retail_selection(turn)
            else None
        )
        product = _extract_product(turn)
        concrete_item = bool(selected_combo or quantity)
        delivery_selection = (
            concrete_item
            and _is_delivery_order_request(turn)
            and not _is_question(turn)
        )

        if _has_buy_intent(turn) or delivery_selection:
            if concrete_item:
                selection = {
                    "text": turn,
                    "combo": selected_combo,
                    "quantity": int(selected_combo["quantity"]) if selected_combo else quantity,
                    "product": product or PRODUCT_CATALOG["venus bigone"],
                }
                pending_generic_intent = False
            else:
                # A general wish to buy still needs a concrete product/variant and count.
                if selection is None:
                    pending_generic_intent = True
                else:
                    pending_generic_intent = False
            continue

        if pending_generic_intent and concrete_item and not _is_question(turn):
            selection = {
                "text": turn,
                "combo": selected_combo,
                "quantity": int(selected_combo["quantity"]) if selected_combo else quantity,
                "product": product or PRODUCT_CATALOG["venus bigone"],
            }
            pending_generic_intent = False

    return selection


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
    number_pattern = r"(\d+|one|two|three|four|five)"
    match = re.search(rf"\bcombo\s*(?:number|#)?\s*{number_pattern}\b", folded)
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
        r"(?:အသက်|age)\s*(?:က|မှာ|သည်|is|:)?\s*([\d۰-۹٠-٩۰-۹]{1,2})|"
        r"([\d۰-۹٠-٩۰-۹]{1,2})\s*(?:years? old|နှစ်)",
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
        r"\b(?:too expensive|price is high|expensive)\b",
        text,
        flags=re.IGNORECASE,
    ):
        return "price"
    return "unknown"


def _intent_status(
    text: str,
    *,
    customer_turns: list[str],
    order_selection: dict[str, Any] | None,
) -> str:
    if order_selection:
        return "ready_to_order"
    for turn in reversed(customer_turns):
        if _is_no_need(turn):
            return "no_need"
        if _is_deferred(turn):
            return "considering"
        if _has_buy_intent(turn):
            return "needs_consultation"
    if _contains_any(text, ("သောက်နည်း", "ဘေးထွက်", "သိချင်", "မေးချင်", "အကြံ", "စိတ်ဝင်စား")):
        return "needs_consultation"
    if re.search(
        r"\b(?:advise|consult|interested|how to use|safe|effective)\b",
        text,
        flags=re.IGNORECASE,
    ):
        return "needs_consultation"
    if _contains_any(text, ("ဈေး", "စျေး", "ဘယ်လောက်", "combo", "Combo")):
        return "price_checking"
    if re.search(
        r"\b(?:price|how much|delivery fee|shipping fee|combo)\b",
        _fold_text(text),
        flags=re.IGNORECASE,
    ):
        return "price_checking"
    return "unknown"


def _need_summary(
    text: str,
    *,
    intent_status: str,
    order_selection: dict[str, Any] | None,
) -> str:
    if intent_status == "no_need":
        return "လိုအပ်ချက်မရှိ"
    if order_selection:
        combo = order_selection.get("combo")
        quantity = order_selection.get("quantity")
        product = order_selection.get("product") or PRODUCT_CATALOG["venus bigone"]
        if combo:
            return f"Combo {combo['quantity']} ဝယ်မည်"
        if quantity:
            return f"{quantity} ဘူး {product['name']} ဝယ်မည်"
        return f"{product['name']} ဝယ်မည်"
    return text[:240]


def extract_customer_facts(
    transcript: list[dict[str, Any]],
    fallback_phone: str = "",
) -> dict[str, Any]:
    text = _customer_text(transcript)
    turns = _customer_turns(transcript)
    name = _extract_customer_name_from_transcript(transcript)
    stated_phone = _extract_phone_from_turns(turns)
    metadata_phone = _normalize_phone_candidate(fallback_phone)
    phone = stated_phone or ("" if _customer_attempted_phone(text) else metadata_phone)
    address = _extract_address_from_transcript(transcript)
    age_range, age_confidence = _extract_age_range(text)
    gender, gender_confidence = _extract_gender(text)
    return {
        "name": name,
        "phone": phone,
        "address": address,
        "need": text[:240],
        "gender": gender,
        "gender_confidence": gender_confidence,
        "age_range": age_range,
        "age_confidence": age_confidence,
    }


def analyze_call(transcript: list[dict[str, Any]], fallback_phone: str = "") -> dict[str, Any]:
    text = _customer_text(transcript)
    customer_turns = _customer_turns(transcript)
    customer = extract_customer_facts(transcript, fallback_phone=fallback_phone)
    phone = customer["phone"]
    address = customer["address"]
    order_selection = extract_order_selection(transcript)
    objection = _extract_objection(text)
    intent_status = _intent_status(
        text,
        customer_turns=customer_turns,
        order_selection=order_selection,
    )
    customer["need"] = _need_summary(
        text,
        intent_status=intent_status,
        order_selection=order_selection,
    )

    order = None
    if intent_status == "ready_to_order" and order_selection:
        combo = order_selection["combo"]
        product = order_selection["product"] or PRODUCT_CATALOG["venus bigone"]
        quantity = int(combo["quantity"]) if combo else order_selection["quantity"]
        product_name = combo["name"] if combo else product["name"]
        purchase_type = "combo" if combo else "retail"
        combo_name = combo["name"] if combo else ""
        unit_price = int(combo["unit_price"]) if combo else int(product["unit_price"])
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
            "customer_name": customer["name"],
            "shipping_address": address,
            "product_name": product_name,
            "purchase_type": purchase_type,
            "combo": combo_name,
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
    confidence = 0.86 if intent_status in {"ready_to_order", "no_need"} else 0.72 if intent_status != "unknown" else 0.3
    next_action = {
        "ready_to_order": "အော်ဒါအချက်အလက်ကို စစ်ပြီး customer နဲ့ ပြန်အတည်ပြုပါ။",
        "needs_consultation": "သောက်သုံးနည်း၊ သတိပြုရန်နှင့် အဓိကအကျိုးကျေးဇူးများကို ထပ်ရှင်းပြပါ။",
        "considering": "Customer စဉ်းစားနေသော အကြောင်းရင်းကို ဖြေရှင်းပြီး နူးညံ့စွာ ပြန်ဆက်သွယ်ပါ။",
        "price_checking": "စျေးနှုန်း၊ combo နှင့် ပို့ခအချက်အလက်ကို ပြောပါ။",
        "no_need": "နောက်ထပ်အော်ဒါ follow-up မလုပ်ပါနှင့်။",
    }.get(intent_status, "Transcript ကို ပြန်စစ်ပြီး နောက်တစ်ဆင့်ကို သတ်မှတ်ပါ။")

    return {
        "customer": customer,
        "analysis": {
            "intent_status": intent_status,
            "sentiment": "neutral",
            "urgency": urgency,
            "objection": objection,
            "summary": text[:300] if text else "Customer ပြောဆိုချက် မရှိသေးပါ။",
            "next_action": next_action,
            "confidence": confidence,
        },
        "order": order,
    }
