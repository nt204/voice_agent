from app.order_extraction import _merge_payload


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
