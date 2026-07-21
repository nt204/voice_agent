from app.config import config
from app.order_extraction import _merge_payload, analyze_call_with_gemini


def test_combo_payload_uses_catalog_prices_when_gemini_mixes_unit_price() -> None:
    payload = {
        "intent_status": "ready_to_order",
        "customer_phone": "0961695448",
        "shipping_address": "Mandalay Chan Aye Tharzan",
        "product_name": "Venus BigOne နို့မှုန့် Combo 2",
        "quantity": 2,
        "unit_price": 120000,
        "total_price": 210000,
        "combo": None,
        "confidence": 0.9,
    }
    fallback = {
        "customer": {"phone": "", "address": "", "need": ""},
        "analysis": {"intent_status": "ready_to_order", "confidence": 0.7},
        "order": {},
    }

    result = _merge_payload(
        payload,
        [{"speaker": "customer", "text": "ကွန်ဘို ၂ မှာယူမယ်။"}],
        fallback_phone="",
        fallback=fallback,
    )

    order = result["order"]
    assert order["product_name"] == "Venus BigOne Combo 2"
    assert order["quantity"] == 2
    assert order["unit_price"] == 105000
    assert order["total_price"] == 210000
    assert order["status"] == "ready_to_confirm"


def test_garbled_phone_attempt_does_not_fall_back_to_metadata_phone() -> None:
    payload = {
        "intent_status": "ready_to_order",
        "customer_name": "null",
        "customer_phone": "+85961695448",
        "shipping_address": "Yangon, Hleden, Insin Road, No. 28",
        "product_name": "Venus BigOne",
        "quantity": 2,
        "unit_price": 120000,
        "total_price": 210000,
        "combo": "Combo 2",
        "confidence": 0.9,
    }
    fallback = {
        "customer": {"phone": "+85961695448", "address": "", "need": ""},
        "analysis": {"intent_status": "ready_to_order", "confidence": 0.7},
        "order": {},
    }
    transcript = [
        {"speaker": "customer", "text": "စိတ်ဝင်စားတဲ့ Benes Baker နှစ်ဘူးမှာမယ်"},
        {"speaker": "customer", "text": "ဖုန်း သုည ကိုးခြောက် တစ်"},
        {"speaker": "customer", "text": "မေးစမ်း Yangon Hleden Insin Road ပါ အသက် ၂၈ အမျိုးသမီး ပါ"},
    ]

    result = _merge_payload(
        payload,
        transcript,
        fallback_phone="+85961695448",
        fallback=fallback,
    )

    assert result["customer"]["name"] == ""
    assert result["customer"]["phone"] == ""
    assert result["customer"]["address"] == "Yangon, Hleden, Insin Road"

    order = result["order"]
    assert order["customer_phone"] == ""
    assert order["shipping_address"] == "Yangon, Hleden, Insin Road"
    assert order["status"] == "missing_info"
    assert order["missing_fields"] == ["customer_phone"]
    assert order["blocking_reasons"] == ["customer_phone"]


def test_transcript_phone_overrides_payload_that_merged_combo_number() -> None:
    payload = {
        "intent_status": "ready_to_order",
        "customer_name": None,
        "customer_phone": "20961984204",
        "shipping_address": "Yangon Hlaing",
        "product_name": "Venus BigOne Combo 2",
        "quantity": 2,
        "unit_price": 105000,
        "total_price": 210000,
        "combo": "Combo 2",
        "confidence": 0.9,
    }
    transcript = [
        {"speaker": "customer", "text": "ကွန်ဘို ၂ မှာယူမယ် ဖုန်း 0961984204"},
        {"speaker": "customer", "text": "လိပ်စာက Yangon Hlaing"},
    ]

    result = _merge_payload(
        payload,
        transcript,
        fallback_phone="",
        fallback={},
    )

    assert result["customer"]["phone"] == "0961984204"
    assert result["order"]["customer_phone"] == "0961984204"
    assert result["order"]["product_name"] == "Venus BigOne Combo 2"


def test_spoken_burmese_phone_from_transcript_overrides_empty_payload() -> None:
    payload = {
        "intent_status": "ready_to_order",
        "customer_name": None,
        "customer_phone": None,
        "shipping_address": "Yangon Hlaing",
        "product_name": "Venus BigOne Combo 2",
        "quantity": 2,
        "unit_price": 105000,
        "total_price": 210000,
        "combo": "Combo 2",
        "confidence": 0.9,
    }
    transcript = [
        {"speaker": "customer", "text": "ကွန်ဘို ၂ မှာယူမယ်"},
        {"speaker": "customer", "text": "ဖုန်း သုည ကိုးခြောက် တစ်ခြောက် ကိုး ငါးလေးလေးရှစ် ပါ"},
        {"speaker": "customer", "text": "လိပ်စာက Yangon Hlaing"},
    ]

    result = _merge_payload(
        payload,
        transcript,
        fallback_phone="",
        fallback={},
    )

    assert result["customer"]["phone"] == "0961695448"
    assert result["order"]["customer_phone"] == "0961695448"
    assert result["order"]["missing_fields"] == []


def test_corrected_phone_after_final_full_statement_is_accepted() -> None:
    payload = {
        "intent_status": "ready_to_order",
        "customer_name": None,
        "customer_phone": "09780771494",
        "shipping_address": "အမှတ် ၄၈ အင်းတော်ကြီးလမ်း အရှေ့ဒဂုံမြို့နယ် ၂ ရပ်ကွက်",
        "product_name": "Venus BigOne Combo 2",
        "quantity": 2,
        "unit_price": 105000,
        "total_price": 210000,
        "combo": "Combo 2",
        "confidence": 0.9,
    }
    transcript = [
        {"speaker": "customer", "text": "ပြန်နှိပ်ဖူးပြီနော် အော်ဒါတင်ပေးပါနော်"},
        {"speaker": "customer", "text": "သုည ကိုး"},
        {"speaker": "customer", "text": "သုည ကိုး ၇၈ သုည ၇၇ ၁ ၄၉၄ ပါ"},
        {"speaker": "customer", "text": "သုည ကိုး ၇၇"},
        {
            "speaker": "customer",
            "text": "သုည ကိုး ၇၈ သုည ပါနော် ၈၈ သုည မဟုတ်ဘူးနော် သုည ကိုး ၇၈ သုည ၇၇ ၁ ၄၉၄ ပါ",
        },
        {
            "speaker": "customer",
            "text": "အင်းတော်ကြီးလမ်း အရှေ့ဒဂုံမြို့နယ် ၂ ရပ်ကွက်ပါ",
        },
    ]

    result = _merge_payload(payload, transcript, fallback_phone="", fallback={})

    assert result["customer"]["phone"] == "09780771494"
    assert result["order"]["customer_phone"] == "09780771494"
    assert result["order"]["status"] == "ready_to_confirm"
    assert result["order"]["blocking_reasons"] == []


def test_payload_phone_is_not_promoted_when_latest_correction_is_partial() -> None:
    payload = {
        "intent_status": "ready_to_order",
        "customer_name": None,
        "customer_phone": "09780771433",
        "shipping_address": "အမှတ် ၄၈ အင်းတော်ကြီးလမ်း အရှေ့ဒဂုံမြို့နယ် ၂ ရပ်ကွက်",
        "product_name": "Venus BigOne Combo 2",
        "quantity": 2,
        "unit_price": 105000,
        "total_price": 210000,
        "combo": "Combo 2",
        "confidence": 0.9,
    }
    transcript = [
        {"speaker": "customer", "text": "နှစ်ဘူးယူမယ် အော်ဒါတင်ပေးပါနော်"},
        {"speaker": "customer", "text": "သုည ကိုး ခုနစ် ရှစ် သုည ခုနစ် ခုနစ် တစ် လေး သုံး သုံး ပါ"},
        {
            "speaker": "customer",
            "text": "မဟုတ်ဘူးနော် ဖုန်းနံပါတ်မှားနေတယ်နော် ပြန်ပြောပေးမယ်နော် သုည ကိုး ခုနစ် ရှစ် သုည ခုနစ် ခုနစ်",
        },
        {
            "speaker": "customer",
            "text": "အင်းတော်ကြီးလမ်း အရှေ့ဒဂုံမြို့နယ် ၂ ရပ်ကွက်ပါ",
        },
    ]

    result = _merge_payload(payload, transcript, fallback_phone="", fallback={})

    assert result["customer"]["phone"] == ""
    assert result["order"]["customer_phone"] == ""
    assert result["order"]["status"] == "missing_info"
    assert "customer_phone" in result["order"]["blocking_reasons"]


def test_payload_phone_rejected_after_latest_full_candidate_stays_missing() -> None:
    payload = {
        "intent_status": "ready_to_order",
        "customer_name": None,
        "customer_phone": "09993905153",
        "shipping_address": "အမှတ် ၄၈ အင်းတော်ကြီးလမ်း အရှေ့ဒဂုံမြို့နယ်",
        "product_name": "Venus BigOne Combo 2",
        "quantity": 2,
        "unit_price": 105000,
        "total_price": 210000,
        "combo": "Combo 2",
        "confidence": 0.9,
    }
    transcript = [
        {"speaker": "customer", "text": "Venus BigOne နှစ်ဘူး ယူမယ်"},
        {
            "speaker": "customer",
            "text": "သုည ကိုး ကိုး ကိုး သုံး ကိုး သုည ငါး တစ် ငါး သုံး ပါ",
        },
        {
            "speaker": "agent",
            "text": "ဖုန်းနံပါတ် ၀ ၉ ၉ ۹ ၃ ۹ ၀ ۵ ۱ ۵ ۳ မှန်ပါသလားရှင်။",
        },
        {"speaker": "customer", "text": "အော် ရီရတယ်နော် အကုန်လုံး မှားနေတယ်"},
        {
            "speaker": "customer",
            "text": "လိပ်စာက အမှတ် ۴۸ အင်းတော်ကြီးလမ်း အရှေ့ဒဂုံမြို့နယ်",
        },
    ]

    result = _merge_payload(payload, transcript, fallback_phone="", fallback={})

    assert result["customer"]["phone"] == ""
    assert result["order"]["customer_phone"] == ""
    assert result["order"]["status"] == "missing_info"
    assert "customer_phone" in result["order"]["missing_fields"]
    assert "customer_phone" in result["order"]["blocking_reasons"]


def test_payload_phone_readback_without_clear_confirmation_stays_missing() -> None:
    payload = {
        "intent_status": "ready_to_order",
        "customer_name": None,
        "customer_phone": "0961695448",
        "shipping_address": "အမှတ် ၄၈ အင်းတော်ကြီးလမ်း အရှေ့ဒဂုံမြို့နယ်",
        "product_name": "Venus BigOne Combo 2",
        "quantity": 2,
        "unit_price": 105000,
        "total_price": 210000,
        "combo": "Combo 2",
        "confidence": 0.9,
    }
    transcript = [
        {"speaker": "customer", "text": "Venus BigOne နှစ်ဘူး ယူမယ်"},
        {"speaker": "customer", "text": "ဖုန်း 0961695448 ပါ"},
        {
            "speaker": "agent",
            "text": "ဖုန်းနံပါတ် ၀ ۹ ۶ ۱ ۶ ۹ ۵ ۴ ۴ ۸ မှန်ပါသလားရှင်။",
        },
        {
            "speaker": "customer",
            "text": "လိပ်စာက အမှတ် ۴۸ အင်းတော်ကြီးလမ်း အရှေ့ဒဂုံမြို့နယ်",
        },
    ]

    result = _merge_payload(payload, transcript, fallback_phone="", fallback={})

    assert result["customer"]["phone"] == ""
    assert result["order"]["customer_phone"] == ""
    assert result["order"]["status"] == "missing_info"
    assert "customer_phone" in result["order"]["missing_fields"]
    assert "customer_phone" in result["order"]["blocking_reasons"]


def test_split_burmese_phone_turns_are_joined_without_using_digit_as_name() -> None:
    payload = {
        "intent_status": "ready_to_order",
        "customer_name": "လေး",
        "customer_phone": None,
        "shipping_address": "အမှတ် ၉၆ ဟံသာဝတီလမ်း၊ အရှေ့ဒဂုံမြို့နယ်",
        "product_name": "Venus BigOne Combo 2",
        "quantity": 2,
        "unit_price": 105000,
        "total_price": 210000,
        "combo": "Combo 2",
        "confidence": 0.86,
    }
    transcript = [
        {"speaker": "customer", "text": "Combo 2 နှစ်ဘူး ယူချင်ပါတယ်ရှင်"},
        {"speaker": "agent", "text": "လက်ခံမယ့်သူရဲ့ နာမည်လေး ပြောပေးပါဦးရှင်"},
        {"speaker": "customer", "text": "အာ မီမီ ပါ"},
        {"speaker": "agent", "text": "ဖုန်းနံပါတ်ကို တစ်လုံးချင်း ဖြည်းဖြည်း ပြောပေးပါရှင်"},
        {"speaker": "customer", "text": "သုည ကိုး"},
        {"speaker": "agent", "text": "သုည ကိုး"},
        {"speaker": "customer", "text": "ကိုး"},
        {"speaker": "agent", "text": "ကိုး"},
        {"speaker": "customer", "text": "ကိုး ရှစ် သုည"},
        {"speaker": "agent", "text": "ကိုး ရှစ် သုည"},
        {"speaker": "customer", "text": "ကိုး ကိုး ခုနစ်"},
        {"speaker": "agent", "text": "ကိုး ကိုး ခုနစ်"},
        {"speaker": "customer", "text": "လေး"},
        {"speaker": "customer", "text": "အင်း ဟုတ်ပြီ"},
        {
            "speaker": "customer",
            "text": "လိပ်စာက အမှတ် ၉၆ ဟံသာဝတီလမ်း၊ အရှေ့ဒဂုံမြို့နယ် ပါ",
        },
    ]

    result = _merge_payload(
        payload,
        transcript,
        fallback_phone="+959793905153",
        fallback={},
    )

    assert result["customer"]["name"] == "မီမီ"
    assert result["customer"]["phone"] == "0999809974"
    assert result["order"]["customer_name"] == "မီမီ"
    assert result["order"]["customer_phone"] == "0999809974"
    assert result["order"]["status"] == "ready_to_confirm"
    assert result["order"]["missing_fields"] == []


def test_non_myanmar_payload_address_is_sanitized_to_missing() -> None:
    payload = {
        "intent_status": "ready_to_order",
        "customer_name": None,
        "customer_phone": "0961695448",
        "shipping_address": "No. 12 Nguyen Trai Street, Hanoi, Vietnam",
        "product_name": "Venus BigOne Combo 2",
        "quantity": 2,
        "unit_price": 105000,
        "total_price": 210000,
        "combo": "Combo 2",
        "confidence": 0.9,
    }
    transcript = [
        {"speaker": "customer", "text": "ကွန်ဘို ၂ မှာယူမယ်"},
        {"speaker": "customer", "text": "ဖုန်း 0961695448"},
        {"speaker": "customer", "text": "လိပ်စာက No. 12 Nguyen Trai Street, Hanoi, Vietnam"},
    ]

    result = _merge_payload(
        payload,
        transcript,
        fallback_phone="",
        fallback={},
    )

    assert result["customer"]["address"] == ""
    assert result["order"]["shipping_address"] == ""
    assert result["order"]["status"] == "missing_info"
    assert result["order"]["missing_fields"] == ["shipping_address"]


def test_merge_payload_uses_name_from_transcript_when_payload_omits_it() -> None:
    payload = {
        "intent_status": "ready_to_order",
        "customer_name": None,
        "customer_phone": "0961984204",
        "shipping_address": "Yangon Hlaing",
        "product_name": "Venus BigOne Combo 2",
        "quantity": 2,
        "unit_price": 105000,
        "total_price": 210000,
        "combo": "Combo 2",
        "confidence": 0.9,
    }
    transcript = [
        {"speaker": "customer", "text": "ကွန်ဘို ၂ မှာယူမယ်"},
        {"speaker": "customer", "text": "နာမည်က Aung Min"},
        {"speaker": "customer", "text": "ဖုန်း 0961984204"},
        {"speaker": "customer", "text": "လိပ်စာက Yangon Hlaing"},
    ]

    result = _merge_payload(
        payload,
        transcript,
        fallback_phone="",
        fallback={},
    )

    assert result["customer"]["name"] == "Aung Min"
    assert result["customer"]["need"] == "Combo 2 ဝယ်မည်"
    assert result["order"]["customer_name"] == "Aung Min"


def test_model_cannot_save_phone_correction_sentence_as_customer_name() -> None:
    payload = {
        "intent_status": "ready_to_order",
        "customer_name": "းနေတယ်နော် ဆရာ ပြောပေးမယ်နော်",
        "customer_phone": "09967954280",
        "shipping_address": "အမှတ် ၆၂ ဂျပ်ဆင်လမ်း မြောက်ဥက္ကလာပမြို့နယ် ရန်ကုန်",
        "product_name": "Venus BigOne Combo 2",
        "quantity": 2,
        "unit_price": 105000,
        "total_price": 210000,
        "combo": "Combo 2",
        "confidence": 0.9,
    }
    transcript = [
        {"speaker": "customer", "text": "နှစ်ဘူး ယူ ပါ မယ်"},
        {"speaker": "customer", "text": "ဖုန်းနံပါတ် 09967954280 မှန်ပါတယ်"},
        {
            "speaker": "customer",
            "text": "လိပ်စာက အမှတ် ၆၂ ဂျပ်ဆင်လမ်း မြောက်ဥက္ကလာပမြို့နယ် ရန်ကုန်",
        },
    ]

    result = _merge_payload(payload, transcript, fallback_phone="", fallback={})

    assert result["customer"]["name"] == ""
    assert result["order"]["customer_name"] == ""


def test_model_ready_intent_is_rejected_without_concrete_customer_selection() -> None:
    payload = {
        "intent_status": "ready_to_order",
        "customer_phone": "+95961984204",
        "shipping_address": "Yangon Hlaing",
        "product_name": "Venus BigOne Combo 2",
        "combo": "Combo 2",
        "quantity": 2,
        "unit_price": 105000,
        "total_price": 210000,
        "confidence": 0.9,
    }
    transcript = [
        {"speaker": "customer", "text": "ကွန်ဘိုတစ်ခု ဝယ်ချင်တယ်"},
        {"speaker": "customer", "text": "Combo 2 က ဘယ်လိုလဲ"},
        {"speaker": "customer", "text": "ship to Yangon Hlaing"},
    ]

    result = _merge_payload(
        payload,
        transcript,
        fallback_phone="+95961984204",
        fallback={},
    )

    assert result["analysis"]["intent_status"] == "needs_consultation"
    assert result["analysis"]["confidence"] == 0.6
    assert result["customer"]["address"] == "Yangon Hlaing"
    assert result["order"] is None


class _FakeGeminiRateLimit(Exception):
    code = 429


def test_order_extraction_retries_gemini_429_without_rule_fallback(monkeypatch) -> None:
    original_enabled = config.gemini.order_extraction_enabled
    original_api_key = config.gemini.api_key
    original_max_delay = config.gemini.rate_limit_retry_max_delay_seconds
    object.__setattr__(config.gemini, "order_extraction_enabled", True)
    object.__setattr__(config.gemini, "api_key", "test-key")
    object.__setattr__(config.gemini, "rate_limit_retry_max_delay_seconds", 1)

    calls = []
    sleeps = []
    payload = {
        "intent_status": "ready_to_order",
        "customer_name": None,
        "customer_phone": "0961695448",
        "shipping_address": "Yangon Hlaing",
        "product_name": "Venus BigOne Combo 2",
        "combo": "Combo 2",
        "quantity": 2,
        "unit_price": 105000,
        "total_price": 210000,
        "objection": "none",
        "summary": "Gemini extracted an order.",
        "missing_fields": [],
        "confidence": 0.9,
    }

    def fake_extract_json_once(prompt: str) -> dict:
        calls.append(prompt)
        if len(calls) == 1:
            raise _FakeGeminiRateLimit(
                "429 RESOURCE_EXHAUSTED {'retryDelay': '0.01s'}"
            )
        return payload

    monkeypatch.setattr(
        "app.order_extraction._extract_json_once",
        fake_extract_json_once,
    )
    monkeypatch.setattr("app.order_extraction.time.sleep", sleeps.append)

    try:
        result = analyze_call_with_gemini(
            [
                {"speaker": "customer", "text": "ကွန်ဘို ၂ မှာယူမယ်"},
                {"speaker": "customer", "text": "ဖုန်း 0961695448"},
                {"speaker": "customer", "text": "လိပ်စာက Yangon Hlaing"},
            ],
            fallback_phone="",
        )
    finally:
        object.__setattr__(config.gemini, "order_extraction_enabled", original_enabled)
        object.__setattr__(config.gemini, "api_key", original_api_key)
        object.__setattr__(
            config.gemini,
            "rate_limit_retry_max_delay_seconds",
            original_max_delay,
        )

    assert len(calls) == 2
    assert sleeps == [1.0]
    assert result["analysis"]["summary"] == "Gemini extracted an order."
    assert result["order"]["status"] == "ready_to_confirm"
