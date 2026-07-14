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
