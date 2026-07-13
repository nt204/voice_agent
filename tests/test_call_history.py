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
