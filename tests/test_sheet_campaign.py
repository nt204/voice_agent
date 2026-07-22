import asyncio
import json

import httpx
from fastapi.testclient import TestClient

from app.call_history import CallHistoryStore


def _product_payload() -> dict:
    return {
        "name": "Moe Collagen",
        "slug": "moe-collagen-sheet",
        "phone_number": "+959111222333",
        "texml_app_id": "app-moe",
        "inbound_greeting": "Moe Collagen inbound greeting",
        "outbound_greeting": "မင်္ဂလာပါရှင် {customer_name}",
        "system_prompt": "You sell only Moe Collagen.",
        "knowledge": "Moe Collagen usage and safety knowledge.",
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


def test_sheet_campaign_dispatches_created_requests_with_selected_product(
    tmp_path,
    monkeypatch,
) -> None:
    from app import main as main_module

    store = CallHistoryStore(tmp_path / "sheet-campaign.db")
    product = store.create_product(_product_payload())
    monkeypatch.setattr(main_module, "call_history", store)
    dispatched = []

    async def fake_send(outbound_request, selected_product):
        dispatched.append((outbound_request, selected_product))
        call_sid = f"sheet-call-{outbound_request['id']}"
        store.mark_outbound_request_started(
            outbound_request["id"],
            call_sid,
        )
        store.update_outbound_request_by_call_sid(call_sid, "completed")
        return {"ok": True}

    monkeypatch.setattr(main_module, "_send_queued_outbound_request", fake_send)
    client = TestClient(main_module.app)
    leads = [
        {
            "name": "Older Duplicate",
            "phone": "09 777 111 222",
            "status_tag": "duplicate",
            "raw_row": {},
        },
        {
            "name": "Thaw Zin",
            "phone": "09 777 111 222",
            "product": "Untrusted Other Product",
            "quantity": "2",
            "address": "Mandalay",
            "notes": "Call before delivery",
            "status_tag": "ready",
            "raw_row": {"Name": "Thaw Zin", "Phone": "09 777 111 222"},
        },
        {
            "name": "Already Called",
            "phone": "09 888 111 222",
            "called": True,
            "raw_row": {},
        },
    ]

    response = client.post(
        "/api/sheets/launch-campaign",
        json={
            "leads": leads,
            "product_id": product["id"],
            "skip_already_called": True,
            "delay_seconds": 120,
            "call_timeout_seconds": 900,
            "campaign_run_id": "sheetcampaignrun0000000000000001",
        },
    )

    assert response.status_code == 200
    assert response.json()["count"] == 1
    assert response.json()["skipped_count"] == 2
    assert response.json()["delay_seconds"] == 120
    assert response.json()["call_timeout_seconds"] == 900
    assert len(dispatched) == 1
    request = store.list_outbound_requests()[0]
    assert request["status"] == "completed"
    assert request["to_number"] == "+959777111222"
    assert request["from_number"] == product["phone_number"]
    assert request["product_id"] == product["id"]
    assert request["campaign_run_id"] == "sheetcampaignrun0000000000000001"
    run = store.get_campaign_run("sheetcampaignrun0000000000000001")
    assert run["delay_seconds"] == 120
    assert run["call_timeout_seconds"] == 900
    customer_data = json.loads(request["customer_data_json"])
    assert customer_data["Name"] == "Thaw Zin"
    assert customer_data["lead"] == {
        "name": "Thaw Zin",
        "phone": "09 777 111 222",
        "product": "Untrusted Other Product",
        "offer": "",
        "quantity": "2",
        "address": "Mandalay",
        "notes": "Call before delivery",
    }
    assert "Moe Collagen" in request["prompt_override"]
    assert "Untrusted Other Product" in request["prompt_override"]
    assert "reference only, not authoritative" in request["prompt_override"]

    options = main_module._telnyx_bridge_options(
        "outbound",
        product,
        prompt_override=request["prompt_override"],
        customer_name=request["customer_name"],
    )
    assert "Order workflow:" in options["system_instruction"]
    assert "Customer File Context" in options["system_instruction"]
    assert "never overrides product" in options["system_instruction"]
    assert "pre-qualified order" in options["system_instruction"]
    assert "Do not ask whether the customer is interested in buying" in options["system_instruction"]
    assert "Thaw Zin" in options["initial_greeting"]
    assert "Moe Collagen" in options["initial_greeting"]
    assert "အော်ဒါကို အတည်ပြုဖို့ပါ" in options["initial_greeting"]

    seed = main_module._sheet_delivery_seed(request)
    assert seed == {
        "customer_name": "Thaw Zin",
        "phone": "09 777 111 222",
        "shipping_address": "Mandalay",
    }


def test_sheet_preview_marks_queued_phone_as_in_progress(tmp_path, monkeypatch) -> None:
    from app import main as main_module

    store = CallHistoryStore(tmp_path / "sheet-preview.db")
    product = store.create_product(_product_payload())
    store.create_outbound_request(
        to_number="+959777111222",
        from_number=product["phone_number"],
        product_id=product["id"],
    )
    monkeypatch.setattr(main_module, "call_history", store)

    async def fake_fetch(_sheet_url: str):
        return [
            {
                "name": "Thaw Zin",
                "phone": "09 777 111 222",
                "product": "Moe Collagen",
                "quantity": "1",
                "address": "Mandalay",
                "notes": "",
                "called": False,
                "status_raw": "",
                "raw_row": {},
                "is_valid_phone": True,
                "is_duplicate": False,
            }
        ]

    monkeypatch.setattr(main_module, "fetch_and_parse_google_sheet", fake_fetch)
    client = TestClient(main_module.app)

    response = client.post(
        "/api/sheets/preview",
        json={"sheet_url": "https://docs.google.com/spreadsheets/d/test/edit", "product_id": product["id"]},
    )

    assert response.status_code == 200
    assert response.json()["ready_count"] == 0
    assert response.json()["called_count"] == 0
    assert response.json()["in_progress_count"] == 1
    assert response.json()["leads"][0]["status_tag"] == "in_progress"
    assert len(response.json()["campaign_run_id"]) == 32
    assert response.json()["product"] == {"id": product["id"], "name": product["name"]}


def test_sheet_preview_keeps_completed_historical_call_ready(tmp_path, monkeypatch) -> None:
    from app import main as main_module

    store = CallHistoryStore(tmp_path / "sheet-historical.db")
    product = store.create_product(_product_payload())
    request = store.create_outbound_request(
        to_number="+959777111222",
        from_number=product["phone_number"],
        product_id=product["id"],
    )
    store.mark_outbound_request_started(request["id"], "historical-sheet-call")
    store.update_outbound_request_by_call_sid(
        "historical-sheet-call",
        "completed",
        dialed_phone="+959777111222",
    )
    monkeypatch.setattr(main_module, "call_history", store)

    async def fake_fetch(_sheet_url: str):
        return [
            {
                "name": "Thaw Zin",
                "phone": "09 777 111 222",
                "called": False,
                "is_valid_phone": True,
                "is_duplicate": False,
            }
        ]

    monkeypatch.setattr(main_module, "fetch_and_parse_google_sheet", fake_fetch)
    client = TestClient(main_module.app)
    response = client.post(
        "/api/sheets/preview",
        json={
            "sheet_url": "https://docs.google.com/spreadsheets/d/test/edit",
            "product_id": product["id"],
        },
    )

    assert response.status_code == 200
    assert response.json()["ready_count"] == 1
    assert response.json()["historical_count"] == 1
    assert response.json()["called_count"] == 0
    assert response.json()["leads"][0]["status_tag"] == "ready_previously_called"


def test_sheet_called_column_is_the_only_historical_blocker(tmp_path, monkeypatch) -> None:
    from app import main as main_module

    store = CallHistoryStore(tmp_path / "sheet-called-column.db")
    product = store.create_product(_product_payload())
    monkeypatch.setattr(main_module, "call_history", store)

    async def fake_fetch(_sheet_url: str):
        return [
            {
                "name": "Thaw Zin",
                "phone": "09 777 111 222",
                "called": True,
                "is_valid_phone": True,
                "is_duplicate": False,
            }
        ]

    monkeypatch.setattr(main_module, "fetch_and_parse_google_sheet", fake_fetch)
    client = TestClient(main_module.app)
    payload = {
        "sheet_url": "https://docs.google.com/spreadsheets/d/test/edit",
        "product_id": product["id"],
    }

    blocked = client.post("/api/sheets/preview", json=payload)
    allowed = client.post(
        "/api/sheets/preview",
        json={**payload, "skip_already_called": False},
    )

    assert blocked.json()["ready_count"] == 0
    assert blocked.json()["leads"][0]["status_tag"] == "already_called"
    assert allowed.json()["ready_count"] == 1
    assert allowed.json()["leads"][0]["status_tag"] == "ready_previously_called"


def test_sheet_campaign_run_id_is_idempotent(tmp_path, monkeypatch) -> None:
    from app import main as main_module

    store = CallHistoryStore(tmp_path / "sheet-idempotent.db")
    product = store.create_product(_product_payload())
    monkeypatch.setattr(main_module, "call_history", store)
    dispatched = []

    async def fake_send(outbound_request, selected_product):
        dispatched.append(outbound_request["id"])
        call_sid = f"idempotent-call-{outbound_request['id']}"
        store.mark_outbound_request_started(
            outbound_request["id"],
            call_sid,
        )
        store.update_outbound_request_by_call_sid(call_sid, "completed")
        return {"ok": True}

    monkeypatch.setattr(main_module, "_send_queued_outbound_request", fake_send)
    payload = {
        "leads": [{"name": "Thaw Zin", "phone": "09 777 111 222"}],
        "product_id": product["id"],
        "campaign_run_id": "samecampaignrun00000000000000001",
    }
    client = TestClient(main_module.app)

    first = client.post("/api/sheets/launch-campaign", json=payload)
    second = client.post("/api/sheets/launch-campaign", json=payload)

    assert first.status_code == 200
    assert first.json()["reused"] is False
    assert second.status_code == 200
    assert second.json()["reused"] is True
    assert second.json()["count"] == 1
    assert len(dispatched) == 1
    assert len(store.list_campaign_run_requests(payload["campaign_run_id"])) == 1


def test_sheet_dispatch_waits_for_terminal_status_before_next_call(tmp_path, monkeypatch) -> None:
    from app import main as main_module

    store = CallHistoryStore(tmp_path / "sheet-sequential.db")
    product = store.create_product(_product_payload())
    run_id = "sequentialcampaignrun0000000000001"
    store.create_campaign_run(
        run_id,
        sheet_url="https://docs.google.com/spreadsheets/d/test/edit",
        product_id=product["id"],
        delay_seconds=30,
        call_timeout_seconds=600,
    )
    requests = [
        store.create_outbound_request(
            to_number=phone,
            from_number=product["phone_number"],
            product_id=product["id"],
            campaign_run_id=run_id,
        )
        for phone in ("+959777111222", "+959888111222")
    ]
    monkeypatch.setattr(main_module, "call_history", store)
    events = []

    async def fake_send(outbound_request, selected_product):
        events.append(f"start:{outbound_request['id']}")
        store.mark_outbound_request_started(
            outbound_request["id"],
            f"sequential-{outbound_request['id']}",
        )
        return {"ok": True}

    async def fake_wait(request_id, campaign_run_id, timeout_seconds):
        events.append(f"wait:{request_id}:{timeout_seconds}")
        store.update_outbound_request_by_call_sid(
            f"sequential-{request_id}",
            "completed",
        )
        return "completed"

    async def fake_gap(campaign_run_id, delay_seconds):
        events.append(f"gap:{delay_seconds}")
        return True

    monkeypatch.setattr(main_module, "_send_queued_outbound_request", fake_send)
    monkeypatch.setattr(main_module, "_wait_for_campaign_request_terminal", fake_wait)
    monkeypatch.setattr(main_module, "_wait_campaign_gap", fake_gap)

    asyncio.run(
        main_module._dispatch_sheet_campaign(
            [request["id"] for request in requests],
            30,
            run_id,
            600,
        )
    )

    assert events == [
        f"start:{requests[0]['id']}",
        f"wait:{requests[0]['id']}:600",
        "gap:30",
        f"start:{requests[1]['id']}",
        f"wait:{requests[1]['id']}:600",
    ]
    assert store.get_campaign_run(run_id)["status"] == "completed"


def test_campaign_wait_timeout_hangs_up_and_marks_request(tmp_path, monkeypatch) -> None:
    from app import main as main_module

    store = CallHistoryStore(tmp_path / "sheet-timeout.db")
    product = store.create_product(_product_payload())
    run_id = "timeoutcampaignrun0000000000000001"
    store.create_campaign_run(
        run_id,
        sheet_url="https://docs.google.com/spreadsheets/d/test/edit",
        product_id=product["id"],
        delay_seconds=0,
        call_timeout_seconds=60,
    )
    request = store.create_outbound_request(
        to_number="+959777111222",
        from_number=product["phone_number"],
        product_id=product["id"],
        campaign_run_id=run_id,
    )
    store.mark_outbound_request_started(request["id"], "timed-out-call")
    monkeypatch.setattr(main_module, "call_history", store)
    hangups = []

    async def fake_hangup(call_sid: str):
        hangups.append(call_sid)
        return {"ok": True}

    monkeypatch.setattr(main_module, "_hangup_telnyx_call", fake_hangup)
    result = asyncio.run(
        main_module._wait_for_campaign_request_terminal(
            request["id"],
            run_id,
            0,
        )
    )

    assert result == "timed_out"
    assert hangups == ["timed-out-call"]
    assert store.get_outbound_request(request["id"])["status"] == "timed_out"


def test_completed_campaign_call_blocks_future_campaign_preview(tmp_path, monkeypatch) -> None:
    from app import main as main_module

    store = CallHistoryStore(tmp_path / "sheet-campaign-called.db")
    product = store.create_product(_product_payload())
    run_id = "completedcampaignrun00000000000001"
    store.create_campaign_run(
        run_id,
        sheet_url="https://docs.google.com/spreadsheets/d/test/edit",
        product_id=product["id"],
        delay_seconds=0,
    )
    request = store.create_outbound_request(
        to_number="+959777111222",
        from_number=product["phone_number"],
        product_id=product["id"],
        campaign_run_id=run_id,
    )
    store.mark_outbound_request_started(request["id"], "completed-campaign-call")
    store.update_outbound_request_by_call_sid(
        "completed-campaign-call",
        "completed",
        dialed_phone="+959777111222",
    )
    monkeypatch.setattr(main_module, "call_history", store)

    async def fake_fetch(_sheet_url: str):
        return [{"name": "Thaw Zin", "phone": "09 777 111 222", "called": False}]

    monkeypatch.setattr(main_module, "fetch_and_parse_google_sheet", fake_fetch)
    client = TestClient(main_module.app)
    response = client.post(
        "/api/sheets/preview",
        json={
            "sheet_url": "https://docs.google.com/spreadsheets/d/test/edit",
            "product_id": product["id"],
        },
    )

    assert response.status_code == 200
    assert response.json()["ready_count"] == 0
    assert response.json()["campaign_called_count"] == 1
    assert response.json()["leads"][0]["status_tag"] == "campaign_called"

    reset = client.post(
        "/api/sheets/campaigns/allow-retry",
        json={"phone_numbers": ["09 777 111 222"]},
    )
    retry_preview = client.post(
        "/api/sheets/preview",
        json={
            "sheet_url": "https://docs.google.com/spreadsheets/d/test/edit",
            "product_id": product["id"],
        },
    )

    assert reset.status_code == 200
    assert reset.json()["reset_count"] == 1
    assert retry_preview.json()["ready_count"] == 1
    assert retry_preview.json()["campaign_called_count"] == 0
    assert retry_preview.json()["leads"][0]["status_tag"] == "ready_previously_called"

    second_run_id = "secondcampaignrun00000000000000001"
    store.create_campaign_run(
        second_run_id,
        sheet_url="https://docs.google.com/spreadsheets/d/test/edit",
        product_id=product["id"],
        delay_seconds=0,
    )
    second_request = store.create_outbound_request(
        to_number="+959777111222",
        from_number=product["phone_number"],
        product_id=product["id"],
        campaign_run_id=second_run_id,
    )
    store.mark_outbound_request_started(second_request["id"], "second-campaign-call")
    store.update_outbound_request_by_call_sid(
        "second-campaign-call",
        "completed",
        dialed_phone="+959777111222",
    )
    blocked_again = client.post(
        "/api/sheets/preview",
        json={
            "sheet_url": "https://docs.google.com/spreadsheets/d/test/edit",
            "product_id": product["id"],
        },
    )

    assert blocked_again.json()["ready_count"] == 0
    assert blocked_again.json()["campaign_called_count"] == 1


def test_failed_campaign_request_without_call_sid_can_be_retried(tmp_path, monkeypatch) -> None:
    from app import main as main_module

    store = CallHistoryStore(tmp_path / "sheet-campaign-failed.db")
    product = store.create_product(_product_payload())
    run_id = "failedcampaignrun0000000000000001"
    store.create_campaign_run(
        run_id,
        sheet_url="https://docs.google.com/spreadsheets/d/test/edit",
        product_id=product["id"],
        delay_seconds=0,
    )
    request = store.create_outbound_request(
        to_number="+959777111222",
        from_number=product["phone_number"],
        product_id=product["id"],
        campaign_run_id=run_id,
    )
    store.mark_outbound_request_failed(request["id"], "Telnyx account disabled D17")
    monkeypatch.setattr(main_module, "call_history", store)

    async def fake_fetch(_sheet_url: str):
        return [{"name": "Thaw Zin", "phone": "09 777 111 222", "called": False}]

    monkeypatch.setattr(main_module, "fetch_and_parse_google_sheet", fake_fetch)
    response = TestClient(main_module.app).post(
        "/api/sheets/preview",
        json={
            "sheet_url": "https://docs.google.com/spreadsheets/d/test/edit",
            "product_id": product["id"],
        },
    )

    assert response.status_code == 200
    assert response.json()["ready_count"] == 1
    assert response.json()["campaign_called_count"] == 0
    assert response.json()["leads"][0]["status_tag"] == "ready"


def test_cancel_campaign_stops_queue_and_hangs_up_started_calls(tmp_path, monkeypatch) -> None:
    from app import main as main_module

    store = CallHistoryStore(tmp_path / "sheet-campaign-cancel.db")
    product = store.create_product(_product_payload())
    run_id = "cancelcampaignrun0000000000000001"
    store.create_campaign_run(
        run_id,
        sheet_url="https://docs.google.com/spreadsheets/d/test/edit",
        product_id=product["id"],
        delay_seconds=15,
    )
    queued = store.create_outbound_request(
        to_number="+959777111222",
        from_number=product["phone_number"],
        product_id=product["id"],
        campaign_run_id=run_id,
    )
    started = store.create_outbound_request(
        to_number="+959888111222",
        from_number=product["phone_number"],
        product_id=product["id"],
        campaign_run_id=run_id,
    )
    store.mark_outbound_request_started(started["id"], "active-campaign-call")
    monkeypatch.setattr(main_module, "call_history", store)
    hangups = []

    async def fake_hangup(call_sid: str):
        hangups.append(call_sid)
        return {"ok": True, "call_sid": call_sid}

    monkeypatch.setattr(main_module, "_hangup_telnyx_call", fake_hangup)
    client = TestClient(main_module.app)

    active = client.get("/api/sheets/campaigns/active")
    canceled = client.post(f"/api/sheets/campaigns/{run_id}/cancel")
    no_active = client.get("/api/sheets/campaigns/active")

    assert active.status_code == 200
    assert active.json()["campaign"]["id"] == run_id
    assert canceled.status_code == 200
    assert canceled.json()["canceled_count"] == 2
    assert canceled.json()["hangup_requested_count"] == 1
    assert hangups == ["active-campaign-call"]
    assert store.get_outbound_request(queued["id"])["status"] == "canceled"
    assert store.get_outbound_request(started["id"])["status"] == "canceled"
    assert store.get_campaign_run(run_id)["status"] == "canceled"
    assert no_active.json()["campaign"] is None


def test_sheet_campaign_rejects_unknown_product_before_queueing(tmp_path, monkeypatch) -> None:
    from app import main as main_module

    store = CallHistoryStore(tmp_path / "sheet-invalid-product.db")
    monkeypatch.setattr(main_module, "call_history", store)
    client = TestClient(main_module.app)

    response = client.post(
        "/api/sheets/launch-campaign",
        json={
            "leads": [{"phone": "09999999999", "status_tag": "ready"}],
            "product_id": 999999,
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Product not found"
    assert store.list_outbound_requests() == []


def test_sheet_dispatch_sends_existing_request_with_product_and_request_routing(
    tmp_path,
    monkeypatch,
) -> None:
    from app import main as main_module

    store = CallHistoryStore(tmp_path / "sheet-dispatch.db")
    product = store.create_product(_product_payload())
    outbound_request = store.create_outbound_request(
        to_number="+959777111222",
        from_number=product["phone_number"],
        product_id=product["id"],
        prompt_override="Customer context",
    )
    monkeypatch.setattr(main_module, "call_history", store)
    captured = {}

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            captured["timeout"] = kwargs.get("timeout")

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, traceback):
            return False

        async def post(self, url, **kwargs):
            captured["url"] = url
            captured.update(kwargs)
            request = httpx.Request("POST", url)
            return httpx.Response(200, json={"sid": "v3:sheet-dispatch"}, request=request)

    monkeypatch.setattr(main_module.httpx, "AsyncClient", FakeAsyncClient)
    original_api_key = main_module.config.telnyx.api_key
    original_account_sid = main_module.config.telnyx.account_sid
    original_public_url = main_module.config.public_base_url
    try:
        object.__setattr__(main_module.config.telnyx, "api_key", "test-api-key")
        object.__setattr__(main_module.config.telnyx, "account_sid", "test-account")
        object.__setattr__(main_module.config, "public_base_url", "https://voice.example")
        result = asyncio.run(
            main_module._send_queued_outbound_request(outbound_request, product)
        )
    finally:
        object.__setattr__(main_module.config.telnyx, "api_key", original_api_key)
        object.__setattr__(main_module.config.telnyx, "account_sid", original_account_sid)
        object.__setattr__(main_module.config, "public_base_url", original_public_url)

    assert result["call_sid"] == "v3:sheet-dispatch"
    assert store.get_outbound_request(outbound_request["id"])["status"] == "started"
    assert captured["url"].endswith("/Accounts/test-account/Calls")
    assert captured["json"]["ApplicationSid"] == product["texml_app_id"]
    assert captured["json"]["To"] == "+959777111222"
    assert captured["json"]["From"] == product["phone_number"]
    assert f"product_id={product['id']}" in captured["json"]["Url"]
    assert f"request_id={outbound_request['id']}" in captured["json"]["Url"]
    assert f"request_id={outbound_request['id']}" in captured["json"]["StatusCallback"]
