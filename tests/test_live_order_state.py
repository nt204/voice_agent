import asyncio

from google.genai import types

from app.gemini_bridge import GeminiCallBridge
from app.live_order_state import DELIVERY_STATE_FUNCTION, LiveDeliveryState


def test_new_phone_attempt_replaces_old_digits_instead_of_appending() -> None:
    state = LiveDeliveryState()

    first = state.apply(field="phone", action="set", value="၀၉၇၉၇၇၁၄၃၃၃")
    second = state.apply(field="phone", action="set", value="09789119333")

    assert first["ok"] is True
    assert second["ok"] is True
    assert state.phone == "09789119333"
    assert second["next_action"] == "confirm_phone"
    assert "0 9 7 8 9 1 1 9 3 3 3" in second["instruction"]


def test_partial_phone_clears_stale_candidate_and_moves_to_keypad_fallback() -> None:
    state = LiveDeliveryState()
    state.apply(field="phone", action="set", value="09797714333")
    state.apply(field="phone", action="reject")

    result = state.apply(field="phone", action="set", value="095003")

    assert result["ok"] is False
    assert state.phone == ""
    assert result["next_action"] == "collect_phone_by_keypad"


def test_confirmed_address_is_retained_and_workflow_advances() -> None:
    state = LiveDeliveryState()
    state.apply(field="phone", action="set", value="09789119333")
    state.apply(field="phone", action="confirm")
    state.apply(
        field="shipping_address",
        action="set",
        value="အမှတ် ၉၈၊ ဟံသာဝတီလမ်း၊ အရှေ့ဒဂုံမြို့နယ်",
    )

    result = state.apply(field="shipping_address", action="confirm")

    assert result["next_action"] == "read_back_order"
    assert state.confirmed_facts() == {
        "phone": "09789119333",
        "address": "အမှတ် ၉၈၊ ဟံသာဝတီလမ်း၊ အရှေ့ဒဂုံမြို့နယ်",
    }


class _FakeSession:
    def __init__(self) -> None:
        self.tool_responses = []
        self.client_content = []

    async def send_tool_response(self, **kwargs) -> None:
        self.tool_responses.append(kwargs)

    async def send_client_content(self, **kwargs) -> None:
        self.client_content.append(kwargs)


class _FakeClient:
    def __init__(self, **kwargs) -> None:
        self.aio = object()


def test_bridge_returns_authoritative_delivery_state_to_live_model(monkeypatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr("app.gemini_bridge.genai.Client", _FakeClient)

    async def send_audio(_: bytes) -> None:
        pass

    async def run() -> tuple[GeminiCallBridge, _FakeSession]:
        bridge = GeminiCallBridge(
            call_id="delivery-tool",
            call_sample_rate=16000,
            send_audio=send_audio,
            send_initial_greeting=False,
        )
        session = _FakeSession()
        bridge.session = session
        await bridge._handle_tool_call(
            types.LiveServerToolCall(
                function_calls=[
                    types.FunctionCall(
                        id="tool-1",
                        name=DELIVERY_STATE_FUNCTION,
                        args={
                            "field": "phone",
                            "action": "set",
                            "value": "09789119333",
                        },
                    )
                ]
            )
        )
        return bridge, session

    bridge, session = asyncio.run(run())

    assert bridge.delivery_state.phone == "09789119333"
    response = session.tool_responses[0]["function_responses"][0].response
    assert response["next_action"] == "confirm_phone"


def test_dtmf_phone_is_recorded_and_sent_to_live_conversation(monkeypatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr("app.gemini_bridge.genai.Client", _FakeClient)
    transcripts = []

    async def send_audio(_: bytes) -> None:
        pass

    async def record(speaker: str, text: str) -> None:
        transcripts.append((speaker, text))

    async def run() -> tuple[GeminiCallBridge, _FakeSession]:
        bridge = GeminiCallBridge(
            call_id="dtmf-phone",
            call_sample_rate=16000,
            send_audio=send_audio,
            send_initial_greeting=False,
            on_transcript=record,
        )
        session = _FakeSession()
        bridge.session = session
        for digit in "09789119333#":
            await bridge.handle_dtmf(digit)
        return bridge, session

    bridge, session = asyncio.run(run())

    assert bridge.delivery_state.phone == "09789119333"
    assert transcripts == [("customer", "ဖုန်းနံပါတ် 09789119333")]
    assert len(session.client_content) == 1
