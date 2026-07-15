from app.call_history import CallHistoryStore
import sqlite3


def test_outbound_status_creates_call_when_stream_never_started(tmp_path):
    store = CallHistoryStore(tmp_path / "call_history.db")
    request = store.create_outbound_request(
        to_number="+84961695448",
        from_number="+19482194502",
    )
    store.mark_outbound_request_started(request["id"], "call-sid-1")

    store.update_outbound_request_by_call_sid(
        "call-sid-1",
        "completed",
        customer_phone="+84961695448",
        started_at="2026-07-13T04:57:20.389461Z",
        ended_at="2026-07-13T04:57:21.029432Z",
    )

    calls = store.list_calls(direction="outbound")
    assert len(calls) == 1
    assert calls[0]["id"] == "call-sid-1"
    assert calls[0]["status"] == "completed"
    assert calls[0]["customer"]["phone"] == "+84961695448"
    assert calls[0]["started_at"] == "2026-07-13T04:57:20.389461Z"
    assert calls[0]["ended_at"] == "2026-07-13T04:57:21.029432Z"


def test_outbound_status_does_not_overwrite_stream_call_phone_with_empty_value(tmp_path):
    store = CallHistoryStore(tmp_path / "call_history.db")
    request = store.create_outbound_request(
        to_number="+84961695448",
        from_number="+19482194502",
    )
    store.mark_outbound_request_started(request["id"], "call-sid-1")
    store.start_call("call-sid-1", "outbound", "telnyx", "+84961695448")

    store.update_outbound_request_by_call_sid("call-sid-1", "completed")

    call = store.get_call("call-sid-1")
    assert call is not None
    assert call["status"] == "completed"
    assert call["customer"]["phone"] == "+84961695448"


def test_started_outbound_request_is_visible_before_callbacks_arrive(tmp_path):
    store = CallHistoryStore(tmp_path / "call_history.db")
    request = store.create_outbound_request(
        to_number="+84961695448",
        from_number="+19482194502",
    )

    store.mark_outbound_request_started(request["id"], "call-sid-visible")

    call = store.get_call("call-sid-visible")
    assert call is not None
    assert call["direction"] == "outbound"
    assert call["status"] == "active"
    assert call["customer"]["phone"] == "+84961695448"


def test_startup_backfills_existing_outbound_requests_without_call_rows(tmp_path):
    db_path = tmp_path / "call_history.db"
    store = CallHistoryStore(db_path)
    request = store.create_outbound_request(
        to_number="+84961695448",
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


def test_vietnamese_combo_buy_intent_creates_missing_info_order(tmp_path):
    store = CallHistoryStore(tmp_path / "call_history.db")
    store.start_call("combo-call", "outbound", "telnyx", "+84961695448")
    store.add_transcript("combo-call", "customer", "အင်း 응. Tôi mua một combo số một. là bao nhiêu tiền?")

    store.finish_call("combo-call")

    call = store.get_call("combo-call")
    assert call is not None
    assert call["analysis"]["intent_status"] == "ready_to_order"
    assert call["order"] is not None
    assert call["order"]["status"] == "missing_info"
    assert call["order"]["customer_phone"] == "+84961695448"
    assert call["order"]["product_name"] == "Venus BigOne Combo 1"
    assert call["order"]["quantity"] == 1
    assert call["order"]["total_price"] == 120000
    assert call["order"]["missing_fields"] == ["shipping_address"]


def test_finish_call_defaults_missing_demographic_fields(tmp_path, monkeypatch):
    store = CallHistoryStore(tmp_path / "call_history.db")
    store.start_call("missing-demographics", "outbound", "telnyx", "+84961695448")
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
    store.add_transcript("unclear-turn", "customer", "Tôi muốn mua Combo 5")

    store.update_customer_transcript_by_index("unclear-turn", 0, "")

    call = store.get_call("unclear-turn")
    assert call is not None
    assert call["transcript"][0]["text"] == ""
