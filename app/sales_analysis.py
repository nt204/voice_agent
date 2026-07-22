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
    "နှိပ်ဖူး": 2,
    "နိပ်ဖူး": 2,
    "နှစ်ဖူး": 2,
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
    "ကို": "9",
    "ကိုယ်": "9",
}
PHONE_DIGIT_WORD_ITEMS = sorted(
    PHONE_DIGIT_WORDS.items(),
    key=lambda item: len(item[0]),
    reverse=True,
)
MYANMAR_PHONE_DIGIT_SIGNAL_RE = re.compile(
    "|".join(
        re.escape(word)
        for word, _ in PHONE_DIGIT_WORD_ITEMS
        if any("\u1000" <= char <= "\u109f" for char in word)
    )
)
PHONE_CORRECTION_RE = re.compile(
    r"(?:မဟုတ်|မှား|မမှန်|ပြန်ပြော|ပြန်မှတ်|ပြန်မှား|မလုပ်တတ်|ဘာလို့|ခဏခဏ|ပြောပြီးပြီ|"
    r"wrong|incorrect|not\s+correct|sai|không\s+đúng|khong\s+dung|không\s+phải|khong\s+phai)",
    flags=re.IGNORECASE,
)
BROAD_PHONE_REJECTION_RE = re.compile(
    r"(?:အကုန်လုံး|အားလုံး|တစ်ခုလုံး|အကုန်|all\s+wrong|everything\s+wrong|"
    r"wrong\s+again|still\s+wrong|tất\s+cả\s+sai|tat\s+ca\s+sai|sai\s+hết|sai\s+het)",
    flags=re.IGNORECASE,
)
PHONE_CONFIRMATION_RE = re.compile(
    r"(?:မှန်|ဟုတ်|အိုကေ|ok|okay|correct|right|yes|đúng|dung|\bs[ií]\b)",
    flags=re.IGNORECASE,
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

# Gemini/telephony ASR often inserts spaces between Burmese syllables and may
# render the English loanword "Combo" with a nearby Burmese spelling.  These
# aliases are only used together with a catalog combo number; they are not
# treated as buying intent on their own.
COMBO_ASR_ALIASES = (
    "ကွန်ဘို",
    "ကွန်ဂို",
    "ကွန်ပူ",
    "ကွန်ဘူး",
    "ကုန်ပူ",
    "ကုန်ဘို",
    "ကုန်ဂို",
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


def _phone_digit_fragment(value: str) -> str:
    text = _normalize_digits(value).casefold().strip(" \t\r\n,.;:-။၊")
    text = re.sub(
        r"^(?:(?:အာ|အင်း|ဟုတ်ကဲ့|အိုကေ|ok)\s+)+",
        "",
        text,
        flags=re.IGNORECASE,
    )
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

    return "".join(digits)


def _spoken_phone_digits(value: str) -> str:
    digits = _phone_digit_fragment(value)
    return digits if len(digits) >= 8 else ""


def _spoken_phone_candidates(value: str) -> list[str]:
    text = _normalize_digits(value).casefold()
    candidates: list[str] = []
    digits: list[str] = []
    index = 0

    def flush() -> None:
        if not digits:
            return
        candidate = _normalize_phone_candidate("".join(digits))
        if candidate:
            candidates.append(candidate)
        digits.clear()

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

        flush()
        index += 1

    flush()
    return candidates


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
        candidate = _spoken_phone_candidate(stripped)
        if candidate:
            return candidate
        candidates = _spoken_phone_candidates(stripped)
        if candidates:
            return candidates[-1]
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


def _compact_asr_text(value: str) -> str:
    """Normalize digits/case and ignore ASR-added whitespace for matching only."""
    return re.sub(r"\s+", "", _normalize_digits(value).casefold())


def _contains_asr_phrase(text: str, tokens: tuple[str, ...]) -> bool:
    """Match known phrases without changing the transcript stored for evidence."""
    normalized = _normalize_digits(text).casefold()
    compact = _compact_asr_text(text)
    for token in tokens:
        normalized_token = _normalize_digits(token).casefold()
        if normalized_token in normalized:
            return True
        if any(ord(char) > 127 for char in normalized_token):
            if re.sub(r"\s+", "", normalized_token) in compact:
                return True
    return False


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
    normalized = _normalize_digits(value).strip()
    if normalized.isdigit():
        parsed = int(normalized)
        return parsed if parsed > 0 else None
    if normalized in NUMBER_WORDS:
        return NUMBER_WORDS[normalized]
    return NUMBER_WORDS.get(_fold_text(normalized).strip())


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
    correction_matches = list(PHONE_CORRECTION_RE.finditer(normalized))
    if correction_matches:
        normalized = normalized[correction_matches[-1].end():]

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

    fragments: list[str] = []
    for turn in turns:
        fragment = _phone_digit_fragment(turn)
        if fragment:
            fragments.append(fragment)
            continue
        if fragments:
            candidate = _normalize_phone_candidate("".join(fragments))
            if candidate:
                return candidate
            fragments.clear()

    if fragments:
        candidate = _normalize_phone_candidate("".join(fragments))
        if candidate:
            return candidate

    return _extract_phone_precise(" ".join(turns))


def _phone_comparison_digits(phone: str) -> str:
    digits = re.sub(r"\D", "", _normalize_digits(phone))
    if digits.startswith("959"):
        return f"0{digits[2:]}"
    return digits


def _turn_rejects_latest_phone(turn: str) -> bool:
    if not PHONE_CORRECTION_RE.search(turn):
        return False
    if _looks_like_address(turn):
        return False
    folded = _fold_text(turn)
    return bool(
        BROAD_PHONE_REJECTION_RE.search(turn)
        or BROAD_PHONE_REJECTION_RE.search(folded)
        or _customer_attempted_phone(turn)
        or len(_phone_digit_fragment(turn)) >= 2
    )


def _turn_confirms_phone(turn: str) -> bool:
    if PHONE_CORRECTION_RE.search(turn):
        return False
    folded = _fold_text(turn)
    return bool(PHONE_CONFIRMATION_RE.search(turn) or PHONE_CONFIRMATION_RE.search(folded))


def _agent_turn_reads_phone(turn: str, phone: str) -> bool:
    target_digits = _phone_comparison_digits(phone)
    if not target_digits:
        return False
    turn_phone = _extract_phone_precise(turn)
    if turn_phone and _phone_comparison_digits(turn_phone) == target_digits:
        return True
    turn_digits = re.sub(r"\D", "", _normalize_digits(turn))
    return bool(
        target_digits in turn_digits
        and re.search(
            r"(?:ဖုန်းနံပါတ်|ဖုန်း|phone|mobile|မှန်|correct|right)",
            turn,
            flags=re.IGNORECASE,
        )
    )


def _phone_readback_indices(transcript: list[dict[str, Any]], phone: str) -> list[int]:
    return [
        index
        for index, item in enumerate(transcript)
        if item.get("speaker") == "agent"
        and _agent_turn_reads_phone(item.get("text", ""), phone)
    ]


def _phone_confirmed_after_readback(transcript: list[dict[str, Any]], phone: str) -> bool:
    readback_indices = _phone_readback_indices(transcript, phone)
    if not readback_indices:
        return True
    target_digits = _phone_comparison_digits(phone)
    invalidated = False
    for item in transcript[readback_indices[-1] + 1:]:
        if item.get("speaker") != "customer":
            continue
        turn = item.get("text", "")
        later_phone = _extract_phone_precise(turn)
        if later_phone and _phone_comparison_digits(later_phone) != target_digits:
            invalidated = True
        if _turn_rejects_latest_phone(turn):
            invalidated = True
        if _turn_confirms_phone(turn):
            if later_phone and _phone_comparison_digits(later_phone) == target_digits:
                return True
            if not invalidated:
                return True
        if _customer_attempted_phone(turn) or len(_phone_digit_fragment(turn)) >= 2:
            invalidated = True
    return False


def _phone_candidate_uncertain(transcript: list[dict[str, Any]], phone: str) -> bool:
    if not phone:
        return False
    digits = re.sub(r"\D", "", phone)
    customer_turns = _customer_turns(transcript)
    candidate_index: int | None = None
    for index, turn in enumerate(customer_turns):
        turn_digits = re.sub(r"\D", "", _normalize_digits(turn))
        turn_phone = _extract_phone_precise(turn)
        if turn_phone == phone or (
            re.search(r"(?:ဖုန်းနံပါတ်|phone\s*number)", turn, flags=re.IGNORECASE)
            and digits
            and digits in turn_digits
        ):
            candidate_index = index

    if candidate_index is not None:
        for later in customer_turns[candidate_index + 1:]:
            later_phone = _extract_phone_precise(later)
            if later_phone and later_phone != phone:
                return True
            if _turn_rejects_latest_phone(later):
                return True
            if _turn_confirms_phone(later):
                continue
            if _customer_attempted_phone(later) or len(_phone_digit_fragment(later)) >= 2:
                if PHONE_CORRECTION_RE.search(later) or not later_phone:
                    return True
        if not PHONE_CORRECTION_RE.search(customer_turns[candidate_index]):
            return False
        if _extract_phone_precise(customer_turns[candidate_index]) == phone:
            return False

    phone_turns = [
        turn
        for turn in customer_turns
        if not _looks_like_address(turn)
        and (
            _customer_attempted_phone(turn)
            or len(_phone_digit_fragment(turn)) >= 2
            or bool(re.search(r"\+?\d{8,15}", _normalize_digits(turn)))
            or bool(
                re.search(r"(?:သုည|ကိုး|ကိုယ်|ရှစ်|ခုနစ်|ခုနှစ်|လေး|သုံး|နှစ်|တစ်|\d)", _normalize_digits(turn))
                and re.search(r"(?:မဟုတ်|မှား|ပြန်ပြော)", turn)
            )
        )
    ]
    if len(phone_turns) < 2:
        return False
    joined = " ".join(phone_turns)
    return bool(PHONE_CORRECTION_RE.search(joined))


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
        if _is_valid_customer_name(name):
            return name
    return ""


def _is_valid_customer_name(name: str) -> bool:
    cleaned = _clean(name)
    folded_name = _fold_text(cleaned)
    return bool(
        2 <= len(cleaned) <= 80
        and re.search(r"[A-Za-zÀ-ỹ\u1000-\u109F]", cleaned)
        and not re.fullmatch(r"([A-Za-z\u1000-\u109F])\1{2,}", cleaned)
        and not re.search(r"\d", _normalize_digits(cleaned))
        and not _phone_digit_fragment(cleaned)
        and len(MYANMAR_PHONE_DIGIT_SIGNAL_RE.findall(cleaned)) < 4
        and folded_name not in {"name", "my name", "phone", "address"}
        and not re.search(
            r"\b(?:combo|box|boxes|kyat|buy|order|purchase|phone|address|delivery|"
            r"yes|ok|correct|confirm|no|need|street|road|township|why|ask|asked|"
            r"wrong|price|how\s+much|which|what)\b|"
            r"(?:ကွန်ဘို|ကွန်ဂို|ဘူး|ဗူး|ကျပ်|ဝယ်|မှာ|ယူ|ဖုန်း|လိပ်စာ|လမ်း|မြို့နယ်|ဟုတ်|မှန်|မလို|ဘာလို့|မေး|ပြောပြီး|ပြောပေး|ပြန်ပြော|မှား|ဘယ်လောက်|ဘယ်|ဘာ|ဈေး|စျေး|လား|လဲ)",
            folded_name,
        )
        and not re.search(
            r"(?:ကွန်ဘို|ကွန်ဂို|ဘူး|ဗူး|ကျပ်|ဝယ်|မှာ|ယူ|ဖုန်း|လိပ်စာ|လမ်း|မြို့နယ်|ဟုတ်|မှန်|မလို|အော်ဒါ|ဘာလို့|မေး|ပြောပြီး|ပြောပေး|ပြန်ပြော|မှား|ဘယ်လောက်|ဘယ်|ဘာ|ဈေး|စျေး|လား|လဲ)",
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
        candidate = re.sub(
            r"^(?:(?:အာ|အင်း|ဟုတ်ကဲ့|အိုကေ|ok)\s+)+",
            "",
            candidate,
            flags=re.IGNORECASE,
        ).strip()
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
            address = re.split(
                r"(?:\b(?:age|years?\s+old|female|male|woman|man)\b|အသက်|အမျိုးသမီး|အမျိုးသား)",
                address,
                maxsplit=1,
                flags=re.IGNORECASE,
            )[0].strip(" \t\r\n,.;:-။၊")
            return address if _looks_like_address(address) else ""
    return ""


def _address_fragment_from_turn(turn: str) -> str:
    candidate = _clean(turn)
    if not candidate or not _looks_like_address(candidate):
        return ""
    house_matches = re.findall(
        r"(?:အမှတ်|no\.?|number)\s*[\d۰-۹٠-٩۰-۹]+",
        candidate,
        flags=re.IGNORECASE,
    )
    if "မဟုတ်" in candidate and house_matches:
        return _clean(house_matches[-1])
    return candidate


def _combine_address_fragments(fragments: list[str]) -> str:
    if not fragments:
        return ""
    last_full = ""
    last_house = ""
    last_location = ""
    for fragment in fragments:
        folded = _fold_text(fragment)
        has_house = bool(re.search(r"(?:အမှတ်|no\.?|number)\s*[\d۰-۹٠-٩۰-۹]+", fragment, flags=re.IGNORECASE))
        has_location = bool(
            _contains_any(
                fragment,
                ("လမ်း", "မြို့", "မြို့နယ်", "ရပ်ကွက်", "ရန်ကုန်", "မန္တလေး"),
            )
            or re.search(r"\b(?:road|street|township|ward|yangon|mandalay)\b", folded)
        )
        if has_house and has_location:
            last_full = fragment
        elif has_house:
            last_house = fragment
        elif has_location:
            last_location = fragment
    if last_full:
        return last_full
    if last_house and last_location and last_house not in last_location:
        return f"{last_house} {last_location}"
    return fragments[-1]


def _address_house_number(value: str) -> str:
    normalized = _normalize_digits(value)
    matches = re.findall(
        r"(?:အမှတ်|no\.?|number)\s*\(?\s*([0-9]+)\s*\)?",
        normalized,
        flags=re.IGNORECASE,
    )
    return matches[-1] if matches else ""


def _address_score(value: str) -> int:
    score = len(_clean(value))
    if re.search(r"(?:လမ်း|road|street)", value, flags=re.IGNORECASE):
        score += 80
    if re.search(r"(?:မြို့နယ်|township)", value, flags=re.IGNORECASE):
        score += 60
    if re.search(r"(?:ရန်ကုန်|yangon)", value, flags=re.IGNORECASE):
        score += 30
    return score


def _agent_segments(transcript: list[dict[str, Any]]) -> list[str]:
    segments: list[str] = []
    current: list[str] = []
    for item in transcript:
        if item.get("speaker") == "agent":
            text = item.get("text", "").strip()
            if text:
                current.append(text)
            continue
        if current:
            segments.append(" ".join(current))
            current = []
    if current:
        segments.append(" ".join(current))
    return segments


def _address_from_agent_segment(segment: str) -> str:
    if not re.search(r"(?:လိပ်စာ|ပို့ရမယ့်|ပို့ရန်|address|delivery)", segment, flags=re.IGNORECASE):
        return ""
    address = _extract_address(segment)
    if not address:
        match = re.search(
            r"((?:အမှတ်|no\.?|number)\s*\(?\s*[\d۰-۹٠-٩۰-۹]+\s*\)?.*)",
            segment,
            flags=re.IGNORECASE,
        )
        if match:
            address = _clean(match.group(1))
    if not address:
        return ""
    address = re.split(
        r"(?:ဟုတ်ပါ|မှန်ပါ|ဖုန်းနံပါတ်|နံပါတ်လေး|စုစုပေါင်း|ဖြစ်ပါတယ်|အချက်အလက်)",
        address,
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0].strip(" \t\r\n,.;:-။၊")
    return address if _looks_like_address(address) else ""


def _agent_address_readback(transcript: list[dict[str, Any]], customer_address: str) -> str:
    customer_house = _address_house_number(customer_address)
    best = ""
    for segment in _agent_segments(transcript):
        candidate = _address_from_agent_segment(segment)
        if not candidate or _is_clearly_non_myanmar_address(candidate):
            continue
        candidate_house = _address_house_number(candidate)
        if customer_house and candidate_house and customer_house != candidate_house:
            continue
        if _address_score(candidate) > _address_score(best):
            best = candidate
    return best


def _extract_address_from_transcript(transcript: list[dict[str, Any]]) -> str:
    turns = _customer_turns(transcript)
    for turn in reversed(turns):
        explicit_address = _extract_address(turn)
        if explicit_address:
            if _is_clearly_non_myanmar_address(explicit_address):
                return ""
            readback = _agent_address_readback(transcript, explicit_address)
            return readback if readback and _address_score(readback) > _address_score(explicit_address) else explicit_address

    fragments: list[str] = []
    for index, item in enumerate(transcript):
        if item.get("speaker") != "customer":
            continue
        candidate = _address_fragment_from_turn(item.get("text", ""))
        if not candidate:
            continue
        raw_context = _agent_context_before(transcript, index)
        context = _fold_text(raw_context)
        if (
            re.search(r"\b(?:address|delivery|ship|deliver)\b", context)
            or re.search(r"(?:လိပ်စာ|ပို့|လမ်းနာမည်|မြို့နယ်)", raw_context)
            or _contains_any(candidate, ("လမ်း", "မြို့နယ်", "ရပ်ကွက်", "အမှတ်"))
            ):
            fragments.append(candidate)
    combined = _combine_address_fragments(fragments)
    if combined:
        if _is_clearly_non_myanmar_address(combined):
            return ""
        readback = _agent_address_readback(transcript, combined)
        return readback if readback and _address_score(readback) > _address_score(combined) else combined

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
    return _agent_address_readback(transcript, "")


def _customer_attempted_phone(text: str) -> bool:
    return bool(
        re.search(
            r"(?:ဖုန်းနံပါတ်|ဖုန်း|phone|mobile)",
            text,
            flags=re.IGNORECASE,
        )
    )


def _extract_quantity(text: str) -> int | None:
    unit_pattern = r"(?:ဘူး|ဗူး|ပုဒ်|box|boxes)"
    mentions: list[tuple[int, int, int]] = []
    for match in re.finditer(
        rf"([\d۰-۹٠-٩۰-۹]+)\s*{unit_pattern}",
        text,
        flags=re.IGNORECASE,
    ):
        mentions.append((match.start(), match.end(), int(_normalize_digits(match.group(1)))))
    for word, value in NUMBER_WORDS.items():
        for match in re.finditer(rf"{re.escape(word)}\s*{unit_pattern}", text, flags=re.IGNORECASE):
            mentions.append((match.start(), match.end(), value))

    if mentions:
        # Corrections are normally spoken as "one box is wrong, take two".
        # Prefer the last non-rejected mention instead of the first number ASR saw.
        mentions.sort(key=lambda item: item[0])
        for _, end, value in reversed(mentions):
            suffix = _compact_asr_text(text[end:end + 32])
            if re.match(r"^(?:မဟုတ်|မှား|မယူ|မဝယ်|မမှာ|not|wrong)", suffix):
                continue
            return value
        return mentions[-1][2]
    if re.search(r"(?:နှစ်|နစ်)\s*ပုဒ်", text, flags=re.IGNORECASE):
        return 2
    if re.search(r"(?:နှိပ်ဖူး|နိပ်ဖူး|နှစ်ဖူး)", text, flags=re.IGNORECASE):
        return 2
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
    if _contains_asr_phrase(text, ("မဝယ်", "မယူ", "မမှာ")):
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
    compact = _compact_asr_text(text)
    if re.search(
        r"(?:ဝယ်(?:ယူ)?|ယူ|မှာ(?:ယူ)?)(?:တော့)?(?:ပါ)?(?:မယ်|မည်|ချင်)",
        compact,
    ):
        return True
    if _contains_asr_phrase(
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
    if "?" in text or _contains_asr_phrase(text, ("ဘယ်လောက်", "သလဲ", "လား", "လဲ")):
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
        or _contains_asr_phrase(text, ("ပို့ပေး", "ပို့ရန်", "ပို့ရမယ့်"))
    )


def _is_retail_selection(text: str) -> bool:
    folded = _fold_text(text)
    return bool(
        re.search(
            r"\b(?:retail|single box|one by one|no combo)\b",
            folded,
        ) or _contains_asr_phrase(text, ("လက်လီ", "တစ်ဘူးချင်း", "တစ်ဘူးစီ", "ကွန်ဘိုမဟုတ်"))
    )


def _is_no_need(text: str) -> bool:
    if _contains_asr_phrase(
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
    if _contains_asr_phrase(text, ("မမှာသေး", "မဝယ်သေး", "စဉ်းစား", "စဥ်းစား", "တိုင်ပင်", "ဆုံးဖြတ်")):
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
    compact = _compact_asr_text(text)
    alias_pattern = "|".join(re.escape(alias) for alias in COMBO_ASR_ALIASES)
    myanmar_match = re.search(
        rf"(?:{alias_pattern})(?:နံပါတ်|အမှတ်|#)?([0-9]+|တစ်|နှစ်|သုံး|လေး|ငါး)",
        compact,
        flags=re.IGNORECASE,
    )
    if myanmar_match and not compact[myanmar_match.end():].startswith("ခု"):
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


def select_customer_asr_transcript(live_candidate: str, secondary_candidate: str) -> str:
    """Keep the transcript candidate with more usable, non-invented sales evidence.

    Secondary ASR remains the tie-breaker, but it may not erase a valid phone,
    combo, order decision, quantity, or address that Live ASR captured clearly.
    """
    live = " ".join(str(live_candidate or "").split())
    secondary = " ".join(str(secondary_candidate or "").split())
    if not live:
        return secondary
    if not secondary:
        return live
    if live == secondary:
        return live

    def signals(text: str) -> dict[str, Any]:
        return {
            "phone": _extract_phone_precise(text),
            "combo": _extract_combo(text),
            "quantity": _extract_quantity(text),
            "decision": _has_buy_intent(text) or _is_no_need(text) or _is_deferred(text),
            "address": _looks_like_address(text),
        }

    live_signals = signals(live)
    secondary_signals = signals(secondary)

    # Do not replace a structured value with a transcript that lost it.
    for key in ("phone", "combo", "address"):
        if live_signals[key] and not secondary_signals[key]:
            return live
    if (
        live_signals["decision"]
        and live_signals["quantity"]
        and not (
            secondary_signals["decision"]
            and secondary_signals["quantity"]
        )
    ):
        return live

    weights = {
        "phone": 12,
        "combo": 8,
        "quantity": 4,
        "decision": 6,
        "address": 5,
    }
    live_score = sum(weight for key, weight in weights.items() if live_signals[key])
    secondary_score = sum(
        weight for key, weight in weights.items() if secondary_signals[key]
    )
    return secondary if secondary_score >= live_score else live


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
    if stated_phone and _phone_candidate_uncertain(transcript, stated_phone):
        phone = ""
    if phone and not _phone_confirmed_after_readback(transcript, phone):
        phone = ""
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
