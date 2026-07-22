from app.call_history import (
    CallHistoryStore,
    SQLiteCallHistoryStore,
    apply_confirmed_delivery_facts,
    apply_confirmed_order_facts,
    extract_customer_info,
)
import sqlite3


def test_outbound_status_creates_call_when_stream_never_started(tmp_path):
    store = CallHistoryStore(tmp_path / "call_history.db")
    request = store.create_outbound_request(
        to_number="+95961695448",
        from_number="+19482194502",
    )
    store.mark_outbound_request_started(request["id"], "call-sid-1")

    store.update_outbound_request_by_call_sid(
        "call-sid-1",
        "completed",
        dialed_phone="+95961695448",
        started_at="2026-07-13T04:57:20.389461Z",
        ended_at="2026-07-13T04:57:21.029432Z",
    )

    calls = store.list_calls(direction="outbound")
    assert len(calls) == 1
    assert calls[0]["id"] == "call-sid-1"
    assert calls[0]["status"] == "completed"
    assert calls[0]["dialed_phone"] == "+95961695448"
    assert calls[0]["customer"]["phone"] == ""
    assert calls[0]["started_at"] == "2026-07-13T04:57:20.389461Z"
    assert calls[0]["ended_at"] == "2026-07-13T04:57:21.029432Z"


def test_outbound_terminal_outcomes_are_preserved_and_filterable(tmp_path):
    store = CallHistoryStore(tmp_path / "call_outcomes.db")
    terminal_statuses = (
        "completed",
        "no_answer",
        "busy",
        "canceled",
        "timed_out",
        "failed",
    )

    for index, status in enumerate(terminal_statuses):
        request = store.create_outbound_request(to_number=f"+9597000000{index}")
        call_sid = f"outcome-{status}"
        store.mark_outbound_request_started(request["id"], call_sid)
        store.update_outbound_request_by_call_sid(call_sid, status)
        assert store.get_call(call_sid)["status"] == status

    assert {call["status"] for call in store.list_calls(call_status="no_answer")} == {
        "no_answer"
    }
    assert {call["status"] for call in store.list_calls(call_status="busy")} == {"busy"}
    assert {call["status"] for call in store.list_calls(call_status="failed")} == {
        "failed",
        "timed_out",
        "canceled",
    }


def test_outbound_status_does_not_overwrite_stream_call_phone_with_empty_value(tmp_path):
    store = CallHistoryStore(tmp_path / "call_history.db")
    request = store.create_outbound_request(
        to_number="+95961695448",
        from_number="+19482194502",
    )
    store.mark_outbound_request_started(request["id"], "call-sid-1")
    store.start_call(
        "call-sid-1",
        "outbound",
        "telnyx",
        dialed_phone="+95961695448",
    )

    store.update_outbound_request_by_call_sid("call-sid-1", "completed")

    call = store.get_call("call-sid-1")
    assert call is not None
    assert call["status"] == "completed"
    assert call["dialed_phone"] == "+95961695448"
    assert call["customer"]["phone"] == ""


def test_started_outbound_request_is_visible_before_callbacks_arrive(tmp_path):
    store = CallHistoryStore(tmp_path / "call_history.db")
    request = store.create_outbound_request(
        to_number="+95961695448",
        from_number="+19482194502",
    )

    store.mark_outbound_request_started(request["id"], "call-sid-visible")

    call = store.get_call("call-sid-visible")
    assert call is not None
    assert call["direction"] == "outbound"
    assert call["status"] == "active"
    assert call["dialed_phone"] == "+95961695448"
    assert call["customer"]["phone"] == ""


def test_startup_backfills_existing_outbound_requests_without_call_rows(tmp_path):
    db_path = tmp_path / "call_history.db"
    store = CallHistoryStore(db_path)
    request = store.create_outbound_request(
        to_number="+95961695448",
        from_number="+19482194502",
    )
    store.mark_outbound_request_started(request["id"], "call-sid-1")
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """
            UPDATE outbound_call_requests
            SET status = 'completed', updated_at = '2026-07-13T04:57:21+00:00'
            WHERE id = ?
            """,
            (request["id"],),
        )

    restarted_store = CallHistoryStore(db_path)

    calls = restarted_store.list_calls(direction="outbound")
    assert len(calls) == 1
    assert calls[0]["id"] == "call-sid-1"
    assert calls[0]["status"] == "completed"


def test_store_accepts_database_url_and_migrates_sqlite_history(tmp_path):
    source_path = tmp_path / "legacy.db"
    source = CallHistoryStore(source_path)
    source.start_call("legacy-call", "inbound", "telnyx", "+959123456789")
    source.add_transcript("legacy-call", "customer", "မင်္ဂလာပါ")
    source.finish_call("legacy-call")

    target_path = tmp_path / "target.db"
    target = CallHistoryStore(f"sqlite:///{target_path.as_posix()}")
    migrated = target.migrate_from_sqlite(source_path)

    call = target.get_call("legacy-call")
    assert migrated["calls"] == 1
    assert call is not None
    assert call["customer"]["phone"] == "+959123456789"
    assert call["transcript"][0]["text"] == "မင်္ဂလာပါ"

    assert target.migrate_from_sqlite(source_path) == {}


def test_myanmar_combo_buy_intent_creates_missing_info_order(tmp_path):
    store = CallHistoryStore(tmp_path / "call_history.db")
    store.start_call("combo-call", "outbound", "telnyx", "+95961695448")
    store.add_transcript("combo-call", "customer", "အင်း၊ ကွန်ဘို ၁ မှာယူမယ်။ စျေးဘယ်လောက်လဲ။")

    store.finish_call("combo-call")

    call = store.get_call("combo-call")
    assert call is not None
    assert call["analysis"]["intent_status"] == "ready_to_order"
    assert call["order"] is not None
    assert call["order"]["status"] == "missing_info"
    assert call["order"]["customer_phone"] == "+95961695448"
    assert call["order"]["product_name"] == "Venus BigOne Combo 1"
    assert call["order"]["quantity"] == 1
    assert call["order"]["total_price"] == 120000
    assert call["order"]["missing_fields"] == ["shipping_address"]


def test_finish_call_does_not_restore_fallback_phone_when_order_blocks_phone(
    tmp_path, monkeypatch
):
    store = CallHistoryStore(tmp_path / "call_history.db")
    store.start_call("rejected-phone", "inbound", "telnyx", customer_phone="09993905153")
    store.add_transcript("rejected-phone", "customer", "Venus BigOne နှစ်ဘူး ယူမယ်")
    store.add_transcript("rejected-phone", "customer", "အကုန်လုံး မှားနေတယ်")

    def fake_analyze_call(transcript, fallback_phone=""):
        assert fallback_phone == "09993905153"
        return {
            "customer": {
                "name": "",
                "phone": "",
                "address": "အမှတ် ၄၈ အင်းတော်ကြီးလမ်း",
                "need": "Combo 2 ဝယ်မည်",
            },
            "analysis": {
                "intent_status": "ready_to_order",
                "sentiment": "negative",
                "urgency": "high",
                "objection": "unknown",
                "summary": "Customer ordered but rejected the phone number.",
                "next_action": "Collect customer phone.",
                "confidence": 0.65,
            },
            "order": {
                "customer_phone": "",
                "customer_name": "",
                "shipping_address": "အမှတ် ၄၈ အင်းတော်ကြီးလမ်း",
                "product_name": "Venus BigOne Combo 2",
                "quantity": 2,
                "unit_price": 105000,
                "total_price": 210000,
                "status": "missing_info",
                "missing_fields": ["customer_phone"],
                "blocking_reasons": ["customer_phone"],
                "confidence": 0.65,
            },
        }

    monkeypatch.setattr(
        "app.sql_call_history.analyze_call_with_gemini",
        fake_analyze_call,
    )

    store.finish_call("rejected-phone")

    call = store.get_call("rejected-phone")
    assert call is not None
    assert call["customer"]["phone"] == ""
    assert call["order"]["customer_phone"] == ""
    assert call["order"]["status"] == "missing_info"


def test_legacy_customer_parser_rejects_phone_as_name() -> None:
    extracted = extract_customer_info(
        [
            {"speaker": "customer", "text": "Venus BigOne တစ်ဘူး ဝယ်မယ်"},
            {"speaker": "customer", "text": "နာမည်က 0961695448 နှစ်"},
            {"speaker": "customer", "text": "လိပ်စာက No. 2 Insein Road, Yangon"},
        ]
    )

    assert extracted["name"] == ""


def test_finish_call_prefers_sales_parser_name_over_legacy_regex(tmp_path, monkeypatch):
    store = CallHistoryStore(tmp_path / "call_history.db")
    store.start_call("name-call", "outbound", "telnyx", "+95961695448")
    store.add_transcript("name-call", "customer", "Venus BigOne တစ်ဘူး ဝယ်မယ်")
    store.add_transcript("name-call", "customer", "နာမည်က 0961695448 နှစ်")
    store.add_transcript("name-call", "customer", "လိပ်စာက No. 2 Insein Road, Yangon")

    def fake_analyze_call(transcript, fallback_phone=""):
        return {
            "customer": {
                "name": "",
                "phone": "0961695448",
                "address": "No. 2 Insein Road, Yangon",
                "need": "1 ဘူး Venus BigOne ဝယ်မည်",
            },
            "analysis": {
                "intent_status": "ready_to_order",
                "sentiment": "neutral",
                "urgency": "high",
                "objection": "unknown",
                "summary": "Customer ordered one box.",
                "next_action": "Confirm order.",
                "confidence": 0.9,
            },
            "order": {
                "customer_phone": "0961695448",
                "customer_name": "Aung",
                "shipping_address": "No. 2 Insein Road, Yangon",
                "product_name": "Venus BigOne",
                "quantity": 1,
                "unit_price": 120000,
                "total_price": 120000,
                "status": "ready_to_confirm",
                "missing_fields": [],
                "confidence": 0.9,
            },
        }

    monkeypatch.setattr(
        "app.sql_call_history.analyze_call_with_gemini",
        fake_analyze_call,
    )

    store.finish_call("name-call")

    call = store.get_call("name-call")
    assert call is not None
    assert call["customer"]["name"] == "Aung"
    assert call["customer"]["need"] == "1 ဘူး Venus BigOne ဝယ်မည်"
    assert call["order"]["customer_name"] == "Aung"


def test_outbound_dialed_phone_is_kept_separate_from_customer_provided_phone(
    tmp_path, monkeypatch
):
    store = CallHistoryStore(tmp_path / "call_history.db")
    store.start_call(
        "separate-phone-call",
        "outbound",
        "telnyx",
        dialed_phone="+959793905153",
    )
    store.add_transcript(
        "separate-phone-call",
        "customer",
        "ဖုန်းနံပါတ် သုည ကိုး ကိုး ကိုး ရှစ် သုည ကိုး ကိုး ခုနစ် လေး",
    )

    def fake_analyze_call(transcript, fallback_phone=""):
        assert fallback_phone == ""
        return {
            "customer": {
                "name": "မီမီ",
                "phone": "0999809974",
                "address": "အမှတ် ၉၈ ဟံသာဝတီလမ်း",
                "need": "Combo 2 ဝယ်မည်",
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
                "customer_name": "မီမီ",
                "shipping_address": "အမှတ် ၉၈ ဟံသာဝတီလမ်း",
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
        fake_analyze_call,
    )

    store.finish_call("separate-phone-call")

    call = store.get_call("separate-phone-call")
    assert call is not None
    assert call["dialed_phone"] == "+959793905153"
    assert call["customer"]["phone"] == "0999809974"
    assert call["order"]["customer_phone"] == "0999809974"


def test_legacy_sqlite_store_serializes_dialed_phone_separately(tmp_path):
    store = SQLiteCallHistoryStore(tmp_path / "legacy-call-history.db")
    store.start_call(
        "legacy-separate-phone",
        "outbound",
        "telnyx",
        dialed_phone="+959793905153",
    )

    call = store.get_call("legacy-separate-phone")

    assert call is not None
    assert call["dialed_phone"] == "+959793905153"
    assert call["customer"]["phone"] == ""


def test_startup_repairs_legacy_conflated_phone_from_latest_order(tmp_path):
    db_path = tmp_path / "legacy-conflated-phone.db"
    store = CallHistoryStore(db_path)
    store.start_call(
        "legacy-conflated-phone",
        "outbound",
        "telnyx",
        customer_phone="+959793905153",
        dialed_phone="+959793905153",
    )
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """
            INSERT INTO orders (
                call_id, customer_phone, customer_name, shipping_address,
                product_name, quantity, unit_price, total_price, status,
                missing_fields, confidence, created_at, updated_at
            )
            VALUES (?, ?, '', '', 'Venus BigOne Combo 2', 2, 105000, 210000,
                    'ready_to_confirm', '', 0.9, ?, ?)
            """,
            (
                "legacy-conflated-phone",
                "0999809974",
                "2026-07-16T09:23:09+00:00",
                "2026-07-16T09:23:09+00:00",
            ),
        )

    repaired = CallHistoryStore(db_path).get_call("legacy-conflated-phone")

    assert repaired is not None
    assert repaired["dialed_phone"] == "+959793905153"
    assert repaired["customer"]["phone"] == "0999809974"


def test_finish_call_defaults_missing_demographic_fields(tmp_path, monkeypatch):
    store = CallHistoryStore(tmp_path / "call_history.db")
    store.start_call("missing-demographics", "outbound", "telnyx", "+95961695448")
    store.add_transcript("missing-demographics", "customer", "တောင်မိုးမိုး 1 combo")

    def fake_analyze_call(transcript, fallback_phone=""):
        return {
            "customer": {
                "name": "",
                "phone": fallback_phone,
                "address": "",
                "need": "တောင်မိုးမိုး 1 combo",
            },
            "analysis": {
                "intent_status": "ready_to_order",
                "sentiment": "neutral",
                "urgency": "high",
                "objection": "unknown",
                "summary": "တောင်မိုးမိုး 1 combo",
                "next_action": "Ask for missing address.",
                "confidence": 0.7,
            },
            "order": None,
        }

    monkeypatch.setattr(
        "app.sql_call_history.analyze_call_with_gemini",
        fake_analyze_call,
    )

    store.finish_call("missing-demographics")

    call = store.get_call("missing-demographics")
    assert call is not None
    assert call["analysis"]["gender"] == "unknown"
    assert call["analysis"]["gender_confidence"] == 0.0
    assert call["analysis"]["age_range"] == "unknown"
    assert call["analysis"]["age_confidence"] == 0.0


def test_final_asr_can_clear_an_unreliable_live_transcript(tmp_path):
    store = CallHistoryStore(tmp_path / "call_history.db")
    store.start_call("unclear-turn", "inbound", "telnyx")
    store.add_transcript("unclear-turn", "customer", "Combo 5 ဝယ်မယ်")

    store.update_customer_transcript_by_index("unclear-turn", 0, "")

    call = store.get_call("unclear-turn")
    assert call is not None
    assert call["transcript"][0]["text"] == ""


def test_campaign_confirmed_delivery_facts_override_post_call_extraction() -> None:
    result = {
        "customer": {
            "name": "Old Name",
            "phone": "09999999999",
            "address": "Old address",
        },
        "order": {
            "customer_name": "Old Name",
            "customer_phone": "09999999999",
            "shipping_address": "Old address",
            "status": "ready_to_confirm",
            "missing_fields": [],
            "blocking_reasons": [],
            "confidence": 0.9,
        },
    }

    apply_confirmed_delivery_facts(
        result,
        {
            "customer_name": "New Name",
            "phone": "09793905153",
            "shipping_address": "New Yangon address",
        },
    )

    assert result["customer"] == {
        "name": "New Name",
        "phone": "09793905153",
        "address": "New Yangon address",
    }
    assert result["order"]["customer_phone"] == "09793905153"
    assert result["order"]["shipping_address"] == "New Yangon address"
    assert result["order"]["status"] == "ready_to_confirm"
    assert result["order"]["missing_fields"] == []


def test_campaign_unconfirmed_delivery_values_cannot_reappear_in_order() -> None:
    result = {
        "customer": {
            "name": "Wrong Name",
            "phone": "09999999999",
            "address": "Rejected address",
        },
        "order": {
            "customer_name": "Wrong Name",
            "customer_phone": "09999999999",
            "shipping_address": "Rejected address",
            "status": "ready_to_confirm",
            "missing_fields": [],
            "blocking_reasons": [],
            "confidence": 0.9,
        },
    }

    apply_confirmed_delivery_facts(result, {})

    assert result["customer"]["phone"] == ""
    assert result["customer"]["address"] == ""
    assert result["order"]["customer_phone"] == ""
    assert result["order"]["shipping_address"] == ""
    assert result["order"]["status"] == "missing_info"
    assert result["order"]["missing_fields"] == [
        "customer_phone",
        "shipping_address",
    ]


def test_campaign_sheet_quantity_is_persisted_as_combo_count_not_box_count() -> None:
    result = {
        "customer": {"name": "မမ", "phone": "0961984204", "address": "Yangon"},
        "order": {
            # Simulate a wrong post-call extraction of raw Sheet Qty=1.
            "product_name": "Venus BigOne",
            "purchase_type": "single",
            "combo": "",
            "quantity": 1,
            "unit_price": 120000,
            "total_price": 120000,
            "status": "ready_to_confirm",
            "missing_fields": [],
            "blocking_reasons": [],
            "confidence": 0.9,
        },
    }

    apply_confirmed_order_facts(
        result,
        {
            "offer_name": "Venus BigOne Combo 2",
            "package_count": 1,
            "units_per_package": 2,
            "total_units": 2,
            "unit_price": 105000,
            "package_price": 210000,
            "total_price": 210000,
        },
    )

    assert result["order"]["product_name"] == "Venus BigOne Combo 2"
    assert result["order"]["package_count"] == 1
    assert result["order"]["units_per_package"] == 2
    assert result["order"]["quantity"] == 2
    assert result["order"]["total_price"] == 210000
    assert result["order"]["status"] == "ready_to_confirm"


def test_campaign_final_order_acceptance_sets_confirmed_status() -> None:
    result = {
        "customer": {},
        "order": {
            "product_name": "Wrong",
            "quantity": 1,
            "unit_price": 1,
            "total_price": 1,
            "missing_fields": [],
            "blocking_reasons": [],
        },
    }

    apply_confirmed_order_facts(
        result,
        {
            "offer_name": "Venus BigOne Combo 2",
            "package_count": 1,
            "units_per_package": 2,
            "total_units": 2,
            "unit_price": 105000,
            "package_price": 210000,
            "total_price": 210000,
            "order_confirmed": True,
        },
    )

    assert result["order"]["status"] == "confirmed"


def test_campaign_multiple_combo_packages_multiply_packing_quantity_and_price() -> None:
    result = {
        "customer": {},
        "order": {
            "product_name": "Wrong",
            "quantity": 3,
            "unit_price": 1,
            "total_price": 3,
            "missing_fields": [],
            "blocking_reasons": [],
        },
    }

    apply_confirmed_order_facts(
        result,
        {
            "offer_name": "Moe Collagen Duo",
            "package_count": 3,
            "units_per_package": 2,
            "total_units": 6,
            "unit_price": 80000,
            "package_price": 160000,
            "total_price": 480000,
        },
    )

    assert result["order"]["package_count"] == 3
    assert result["order"]["quantity"] == 6
    assert result["order"]["total_price"] == 480000


def test_campaign_unconfirmed_combo_cannot_be_saved_from_transcript_extraction() -> None:
    result = {
        "customer": {},
        "order": {
            "product_name": "Venus BigOne",
            "purchase_type": "single",
            "combo": "",
            "quantity": 1,
            "unit_price": 120000,
            "total_price": 120000,
            "status": "ready_to_confirm",
            "missing_fields": [],
            "blocking_reasons": [],
        },
    }

    apply_confirmed_order_facts(result, {})

    assert result["order"]["product_name"] == ""
    assert result["order"]["quantity"] == 0
    assert result["order"]["total_price"] == 0
    assert result["order"]["status"] == "missing_info"
    assert result["order"]["missing_fields"] == ["product_name", "quantity"]
