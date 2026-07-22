from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.call_history import CallHistoryStore, calls_table, orders_table
from app.config import gemini_system_instruction
from app.order_extraction import _merge_payload, analyze_call_with_gemini


def _product_payload(**overrides):
    payload = {
        "name": "Moe Collagen",
        "slug": "moe-collagen",
        "phone_number": "+959111222333",
        "texml_app_id": "app-moe",
        "inbound_greeting": "Moe Collagen inbound greeting",
        "outbound_greeting": "Moe Collagen outbound greeting",
        "system_prompt": "You sell only Moe Collagen.",
        "knowledge": "Moe Collagen costs 85000 MMK for one box.",
        "language_code": "my-MM",
        "voice_name": "Aoede",
        "active": True,
        "offers": [
            {
                "name": "Moe Collagen Single",
                "quantity": 1,
                "unit_price": 85000,
                "total_price": 85000,
                "shipping_policy": "Delivery included",
                "active": True,
            },
            {
                "name": "Moe Collagen Duo",
                "quantity": 2,
                "unit_price": 80000,
                "total_price": 160000,
                "shipping_policy": "Free delivery",
                "active": True,
            },
        ],
    }
    payload.update(overrides)
    return payload


def test_store_seeds_existing_venus_product_without_changing_order_contract(
    tmp_path, monkeypatch
):
    store = CallHistoryStore(tmp_path / "products.db")

    products = store.list_products()

    assert len(products) == 1
    assert products[0]["name"] == "Venus BigOne"
    assert products[0]["is_default"] is True
    assert products[0]["active"] is True
    assert [offer["total_price"] for offer in products[0]["offers"]] == [
        120000,
        210000,
        390000,
        630000,
    ]

    def existing_order_result(transcript, fallback_phone="", product=None):
        assert product["name"] == "Venus BigOne"
        return {
            "customer": {
                "name": "",
                "phone": "0999809974",
                "address": "No. 2 Insein Road, Yangon",
                "need": "Venus BigOne Combo 2",
            },
            "analysis": {
                "intent_status": "ready_to_order",
                "sentiment": "neutral",
                "urgency": "high",
                "objection": "unknown",
                "summary": "Customer ordered Combo 2.",
                "next_action": "Confirm order.",
                "confidence": 0.9,
            },
            "order": {
                "customer_phone": "0999809974",
                "customer_name": "",
                "shipping_address": "No. 2 Insein Road, Yangon",
                "product_name": "Venus BigOne Combo 2",
                "quantity": 2,
                "unit_price": 105000,
                "total_price": 210000,
                "status": "ready_to_confirm",
                "missing_fields": [],
                "confidence": 0.9,
            },
        }

    monkeypatch.setattr(
        "app.sql_call_history.analyze_call_with_gemini",
        existing_order_result,
    )

    store.start_call(
        "venus-order-contract",
        "outbound",
        "telnyx",
        dialed_phone="+95961695448",
        product_id=products[0]["id"],
    )
    store.add_transcript(
        "venus-order-contract",
        "customer",
        "I want Venus BigOne Combo 2, phone 0999809974, address No. 2 Insein Road, Yangon",
    )
    store.finish_call("venus-order-contract")

    order = store.get_call("venus-order-contract")["order"]
    assert set(order) >= {
        "id",
        "call_id",
        "customer_phone",
        "customer_name",
        "shipping_address",
        "product_name",
        "quantity",
        "unit_price",
        "total_price",
        "status",
        "missing_fields",
        "confidence",
        "created_at",
        "updated_at",
    }
    assert order["product_id"] == products[0]["id"]


def test_venus_keeps_legacy_runtime_prompt_composition(tmp_path):
    store = CallHistoryStore(tmp_path / "venus-prompt-compatibility.db")
    venus = store.get_default_product()

    prompt = gemini_system_instruction("outbound", product=venus)

    assert prompt.startswith(f'{venus["system_prompt"]}\n\nVoice call rules:')
    assert "Product-specific role and constraints:" not in prompt
    assert "cannot override the shared voice" not in prompt


def test_product_crud_replaces_offers_and_resolves_normalized_phone(tmp_path):
    store = CallHistoryStore(tmp_path / "products.db")

    created = store.create_product(_product_payload())

    assert created["slug"] == "moe-collagen"
    assert created["phone_number"] == "+959111222333"
    assert len(created["offers"]) == 2
    assert store.resolve_product_by_phone("09 111 222 333")["id"] == created["id"]

    updated = store.update_product(
        created["id"],
        _product_payload(
            name="Moe Collagen Plus",
            offers=[
                {
                    "name": "Moe Collagen Plus Single",
                    "quantity": 1,
                    "unit_price": 90000,
                    "total_price": 90000,
                    "shipping_policy": "Delivery included",
                    "active": True,
                }
            ],
        ),
    )

    assert updated["name"] == "Moe Collagen Plus"
    assert [offer["total_price"] for offer in updated["offers"]] == [90000]
    assert len(store.list_products(active_only=True)) == 2


def test_new_product_gets_standard_conversation_defaults_when_optional_prompt_is_blank(
    tmp_path,
):
    store = CallHistoryStore(tmp_path / "product-default-prompt.db")
    created = store.create_product(
        _product_payload(
            inbound_greeting="",
            outbound_greeting="",
            system_prompt="",
        )
    )

    assert "Moe Collagen" in created["inbound_greeting"]
    assert "Moe Collagen" in created["outbound_greeting"]
    assert "phone sales consultant for Moe Collagen" in created["system_prompt"]

    prompt = gemini_system_instruction("outbound", product=created)
    assert "Order confirmation template" in prompt
    assert "Phone number listening guide" in prompt
    assert "cannot override the shared voice" in prompt
    assert "Moe Collagen Duo" in prompt


def test_product_rejects_duplicate_phone_and_cannot_disable_only_default(tmp_path):
    store = CallHistoryStore(tmp_path / "products.db")
    created = store.create_product(_product_payload())

    with pytest.raises(ValueError, match="phone number"):
        store.create_product(
            _product_payload(
                name="Duplicate",
                slug="duplicate",
            )
        )

    default_product = store.get_default_product()
    with pytest.raises(ValueError, match="default product"):
        store.update_product(
            default_product["id"],
            {
                **default_product,
                "active": False,
                "offers": default_product["offers"],
            },
        )

    store.set_default_product(created["id"])
    disabled_venus = store.update_product(
        default_product["id"],
        {
            **default_product,
            "active": False,
            "offers": default_product["offers"],
        },
    )
    assert disabled_venus["active"] is False


def test_product_rejects_phone_that_telnyx_cannot_dial(tmp_path):
    store = CallHistoryStore(tmp_path / "invalid-product-phone.db")

    with pytest.raises(ValueError, match="valid international number"):
        store.create_product(_product_payload(phone_number="12345"))


def test_product_delete_only_allows_unused_non_default_product(tmp_path):
    store = CallHistoryStore(tmp_path / "delete-products.db")
    default_product = store.get_default_product()

    with pytest.raises(ValueError, match="default product"):
        store.delete_product(default_product["id"])

    deletable = store.create_product(_product_payload())
    deleted = store.delete_product(deletable["id"])
    assert deleted["name"] == "Moe Collagen"
    assert store.get_product(deletable["id"]) is None

    used = store.create_product(
        _product_payload(
            name="Used Product",
            slug="used-product",
            phone_number="+959111222334",
        )
    )
    store.start_call(
        "used-product-call",
        "outbound",
        "telnyx",
        product_id=used["id"],
    )
    with pytest.raises(ValueError, match="existing calls"):
        store.delete_product(used["id"])
    assert store.get_product(used["id"])["name"] == "Used Product"


def test_product_requires_unambiguous_active_offer_configuration(tmp_path):
    store = CallHistoryStore(tmp_path / "product-offer-validation.db")

    with pytest.raises(ValueError, match="at least one offer"):
        store.create_product(_product_payload(offers=[]))

    inactive_offers = [
        {**offer, "active": False}
        for offer in _product_payload()["offers"]
    ]
    with pytest.raises(ValueError, match="at least one active offer"):
        store.create_product(
            _product_payload(slug="all-inactive", offers=inactive_offers)
        )

    duplicate_quantity = [
        _product_payload()["offers"][0],
        {
            **_product_payload()["offers"][1],
            "name": "Moe Collagen Alternate Single",
            "quantity": 1,
        },
    ]
    with pytest.raises(ValueError, match="unique quantities"):
        store.create_product(
            _product_payload(slug="duplicate-quantity", offers=duplicate_quantity)
        )


def test_calls_requests_and_orders_keep_product_association(tmp_path):
    store = CallHistoryStore(tmp_path / "products.db")
    product = store.create_product(_product_payload())
    request = store.create_outbound_request(
        to_number="+959444555666",
        from_number=product["phone_number"],
        product_id=product["id"],
    )
    store.mark_outbound_request_started(request["id"], "product-call")
    store.start_call(
        "product-call",
        "outbound",
        "telnyx",
        dialed_phone="+959444555666",
        product_id=product["id"],
    )

    call = store.get_call("product-call")
    assert call["product"]["id"] == product["id"]
    assert call["product"]["name"] == "Moe Collagen"
    assert store.list_calls(product_id=product["id"])[0]["id"] == "product-call"
    assert store.list_calls(product_id=store.get_default_product()["id"]) == []
    assert store.get_outbound_request(request["id"])["product_id"] == product["id"]


def test_legacy_order_is_backfilled_from_an_unambiguous_configured_offer(tmp_path):
    db_path = tmp_path / "legacy-order-products.db"
    store = CallHistoryStore(db_path)
    product = store.create_product(_product_payload())
    with store.engine.begin() as connection:
        connection.execute(
            calls_table.insert().values(
                id="legacy-product-call",
                direction="outbound",
                provider="telnyx",
                status="completed",
                started_at="2026-07-20T01:00:00+00:00",
            )
        )
        connection.execute(
            orders_table.insert().values(
                call_id="legacy-product-call",
                product_name="Moe Collagen Duo",
                quantity=2,
                unit_price=80000,
                total_price=160000,
                status="confirmed",
                created_at="2026-07-20T01:05:00+00:00",
                updated_at="2026-07-20T01:05:00+00:00",
            )
        )

    reopened = CallHistoryStore(db_path)
    orders = reopened.list_orders(product_id=product["id"])

    assert len(orders) == 1
    assert orders[0]["product_id"] == product["id"]
    assert orders[0]["product"]["name"] == "Moe Collagen"
    assert reopened.get_call("legacy-product-call")["product"]["id"] == product["id"]


def test_product_prompt_contains_only_selected_product_knowledge(tmp_path):
    store = CallHistoryStore(tmp_path / "products.db")
    product = store.create_product(_product_payload())

    instruction = gemini_system_instruction("outbound", product=product)

    assert "You sell only Moe Collagen." in instruction
    assert "Moe Collagen costs 85000 MMK" in instruction
    assert "Moe Collagen Duo" in instruction
    assert "Venus BigOne" not in instruction
    assert "Combo 3" not in instruction
    assert "Order confirmation template" in instruction
    assert "cannot override the shared voice" in instruction


def test_product_api_crud_and_outbound_rejects_unknown_product(tmp_path, monkeypatch):
    from app import main as main_module

    store = CallHistoryStore(tmp_path / "api-products.db")
    monkeypatch.setattr(main_module, "call_history", store)
    client = TestClient(main_module.app)

    listing = client.get("/api/products")
    assert listing.status_code == 200
    assert listing.json()["products"][0]["name"] == "Venus BigOne"

    created = client.post("/api/products", json=_product_payload())
    assert created.status_code == 201
    product = created.json()["product"]
    assert product["name"] == "Moe Collagen"

    updated = client.put(
        f"/api/products/{product['id']}",
        json=_product_payload(name="Moe Collagen Updated"),
    )
    assert updated.status_code == 200
    assert updated.json()["product"]["name"] == "Moe Collagen Updated"

    selected = client.post(f"/api/products/{product['id']}/default")
    assert selected.status_code == 200
    assert selected.json()["product"]["is_default"] is True

    deletable = client.post(
        "/api/products",
        json=_product_payload(
            name="Delete Me",
            slug="delete-me",
            phone_number="+959111222334",
        ),
    ).json()["product"]
    deleted = client.delete(f"/api/products/{deletable['id']}")
    assert deleted.status_code == 200
    assert deleted.json()["deleted"] is True
    assert client.delete(f"/api/products/{deletable['id']}").status_code == 404
    assert client.delete(f"/api/products/{product['id']}").status_code == 400

    outbound = client.post(
        "/telnyx/outbound/call",
        json={"product_id": 999999, "to_number": "+959123456789"},
    )
    assert outbound.status_code == 400
    assert outbound.json()["detail"] == "Select an active product"


def test_telnyx_answer_routes_product_into_websocket_and_bridge(tmp_path, monkeypatch):
    from app import main as main_module

    store = CallHistoryStore(tmp_path / "route-products.db")
    product = store.create_product(_product_payload())
    monkeypatch.setattr(main_module, "call_history", store)
    client = TestClient(main_module.app)

    inbound = client.post(
        "/telnyx/answer",
        data={"To": product["phone_number"], "From": "+959888777666"},
    )
    outbound = client.post(f"/telnyx/outbound/answer?product_id={product['id']}")
    bridge_options = main_module._telnyx_bridge_options("outbound", product)

    assert inbound.status_code == 200
    assert f"product_id={product['id']}" in inbound.text
    assert outbound.status_code == 200
    assert f"product_id={product['id']}" in outbound.text
    assert bridge_options["initial_greeting"] == product["outbound_greeting"]
    assert "Moe Collagen costs 85000 MMK" in bridge_options["system_instruction"]
    assert bridge_options["language_code"] == "my-MM"
    assert bridge_options["voice_name"] == "Aoede"


def test_custom_product_offer_cannot_be_overwritten_by_venus_combo_catalog():
    product = {"id": 2, **_product_payload()}
    transcript = [
        {
            "speaker": "customer",
            "text": (
                "I will buy Moe Collagen Duo quantity 2. "
                "Phone 0999809974. Address No. 2 Insein Road, Yangon."
            ),
        }
    ]
    payload = {
        "intent_status": "ready_to_order",
        "customer_name": "Moe Moe",
        "customer_phone": "0999809974",
        "shipping_address": "No. 2 Insein Road, Yangon",
        "product_name": "Moe Collagen Duo",
        "combo": "Moe Collagen Duo",
        "quantity": 2,
        "unit_price": 80000,
        "total_price": 160000,
        "objection": "none",
        "summary": "Customer ordered Moe Collagen Duo.",
        "missing_fields": [],
        "confidence": 0.95,
    }

    result = _merge_payload(
        payload,
        transcript,
        fallback_phone="",
        fallback={},
        product=product,
    )

    assert result["order"]["product_name"] == "Moe Collagen Duo"
    assert result["order"]["quantity"] == 2
    assert result["order"]["unit_price"] == 80000
    assert result["order"]["total_price"] == 160000


def test_custom_product_fallback_never_creates_a_venus_order():
    product = {"id": 2, **_product_payload()}
    transcript = [
        {
            "speaker": "customer",
            "text": "I want Combo 2 of Moe Collagen and will place the order.",
        }
    ]

    result = analyze_call_with_gemini(
        transcript,
        fallback_phone="+959123456789",
        product=product,
    )

    assert result["order"] is None
    assert result["analysis"]["intent_status"] == "needs_consultation"
    assert "Venus BigOne" not in result["customer"]["need"]


def test_dashboard_includes_product_management_and_product_call_selection():
    html = Path("app/static/index.html").read_text(encoding="utf-8")
    source = Path("app/static/dashboard.js").read_text(encoding="utf-8")
    products_html = Path("app/static/products.html").read_text(encoding="utf-8")
    products_source = Path("app/static/products.js").read_text(encoding="utf-8")
    styles = Path("app/static/dashboard.css").read_text(encoding="utf-8")

    assert 'id="productFilter"' in html
    assert 'id="outboundProduct"' in html
    assert 'id="productForm"' in products_html
    assert 'id="productList"' in products_html
    assert 'id="applyProductPromptDefaultsButton"' in products_html
    assert 'id="deleteProductButton"' in products_html
    assert "Prompt lõi và xác nhận đơn đã được dùng chung" in products_html
    assert 'fetchJson("/api/products")' in source
    assert 'product_id: Number(productId)' in source
    assert 'fetchJson("/api/products")' in products_source
    assert "renderProductList" in products_source
    assert "standardConversationDefaults" in products_source
    assert 'writeJson(`/api/products/${product.id}`, "DELETE")' in products_source
    assert ".products-workspace" in styles
    assert "@media (max-width: 680px)" in styles
