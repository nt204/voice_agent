from fastapi.testclient import TestClient
import httpx


def test_hangup_endpoint_completes_the_telnyx_texml_call(monkeypatch):
    from app import main as main_module

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
            return httpx.Response(200, json={"sid": "v3:test-call", "status": "completed"}, request=request)

    original_api_key = main_module.config.telnyx.api_key
    original_account_sid = main_module.config.telnyx.account_sid
    try:
        object.__setattr__(main_module.config.telnyx, "api_key", "test-api-key")
        object.__setattr__(main_module.config.telnyx, "account_sid", "test-account")
        monkeypatch.setattr(main_module.httpx, "AsyncClient", FakeAsyncClient)

        response = TestClient(main_module.app).post(
            "/telnyx/outbound/call/v3:test-call/hangup"
        )
    finally:
        object.__setattr__(main_module.config.telnyx, "api_key", original_api_key)
        object.__setattr__(main_module.config.telnyx, "account_sid", original_account_sid)

    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert captured["url"] == (
        "https://api.telnyx.com/v2/texml/Accounts/test-account/Calls/v3%3Atest-call"
    )
    assert captured["data"] == {"Status": "completed"}
    assert captured["headers"]["Authorization"] == "Bearer test-api-key"


def test_hangup_endpoint_rejects_request_when_telnyx_is_not_configured():
    from app import main as main_module

    original_api_key = main_module.config.telnyx.api_key
    original_account_sid = main_module.config.telnyx.account_sid
    try:
        object.__setattr__(main_module.config.telnyx, "api_key", None)
        object.__setattr__(main_module.config.telnyx, "account_sid", None)

        response = TestClient(main_module.app).post(
            "/telnyx/outbound/call/v3:test-call/hangup"
        )
    finally:
        object.__setattr__(main_module.config.telnyx, "api_key", original_api_key)
        object.__setattr__(main_module.config.telnyx, "account_sid", original_account_sid)

    assert response.status_code == 500
    assert response.json()["detail"] == "Missing config: TELNYX_API_KEY, TELNYX_ACCOUNT_SID"
