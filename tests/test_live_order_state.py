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


def test_partial_phone_clears_stale_candidate_and_keeps_listening_before_keypad() -> None:
    state = LiveDeliveryState()
    state.apply(field="phone", action="set", value="09797714333")
    state.apply(field="phone", action="reject")

    result = state.apply(field="phone", action="set", value="095003")

    assert result["ok"] is False
    assert state.phone == ""
    assert result["next_action"] == "ask_phone"


def test_phone_moves_to_keypad_only_after_repeated_listening_failures() -> None:
    state = LiveDeliveryState()
    for _ in range(2):
        result = state.apply(field="phone", action="set", value="095003")
        assert result["next_action"] == "ask_phone"

    result = state.apply(field="phone", action="set", value="095003")

    assert result["next_action"] == "collect_phone_by_keypad"


def test_phone_moves_to_keypad_after_three_rejections() -> None:
    state = LiveDeliveryState()

    for _ in range(2):
        state.apply(field="phone", action="set", value="09789119333")
        result = state.apply(field="phone", action="reject")
        assert result["next_action"] == "ask_phone"

    state.apply(field="phone", action="set", value="09789119333")
    result = state.apply(field="phone", action="reject")

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


def test_bridge_records_phone_after_customer_confirms_it(monkeypatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr("app.gemini_bridge.genai.Client", _FakeClient)
    transcripts = []

    async def send_audio(_: bytes) -> None:
        pass

    async def record(speaker: str, text: str) -> None:
        transcripts.append((speaker, text))

    async def run() -> GeminiCallBridge:
        bridge = GeminiCallBridge(
            call_id="confirmed-phone",
            call_sample_rate=16000,
            send_audio=send_audio,
            send_initial_greeting=False,
            on_transcript=record,
        )
        bridge.session = _FakeSession()
        for action, value in (("set", "09789119333"), ("confirm", "")):
            await bridge._handle_tool_call(
                types.LiveServerToolCall(
                    function_calls=[
                        types.FunctionCall(
                            id=f"phone-{action}",
                            name=DELIVERY_STATE_FUNCTION,
                            args={"field": "phone", "action": action, "value": value},
                        )
                    ]
                )
            )
        return bridge

    bridge = asyncio.run(run())

    assert bridge.delivery_state.confirmed_facts()["phone"] == "09789119333"
    assert transcripts == [("customer", "ဖုန်းနံပါတ် 09789119333 မှန်ပါတယ်")]


def test_dtmf_phone_is_recorded_and_sent_to_live_conversation(monkeypatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr("app.gemini_bridge.genai.Client", _FakeClient)
    transcripts = []

    sent_audio = []

    async def send_audio(frame: bytes) -> None:
        sent_audio.append(frame)

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
    assert transcripts == [
        ("customer", "ဖုန်းနံပါတ် 09789119333"),
        ("agent", "ဖုန်းနံပါတ် 09789119333 မှန်ပါသလားရှင်။"),
    ]
    assert sent_audio
    assert session.client_content == []


def test_secondary_asr_phone_replaces_wrong_live_phone_and_blocks_overwrite(monkeypatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr("app.gemini_bridge.genai.Client", _FakeClient)
    cleared = []
    customer_phone = "သုည ကိုး ခုနစ် ရှစ် သုည ခုနစ် ခုနစ် တစ် လေး သုံး သုံး ပါ"

    async def send_audio(_: bytes) -> None:
        pass

    async def clear_audio() -> None:
        cleared.append(True)

    async def correct_audio(*_args) -> str:
        return customer_phone

    async def run() -> tuple[GeminiCallBridge, _FakeSession]:
        bridge = GeminiCallBridge(
            call_id="secondary-asr-phone",
            call_sample_rate=16000,
            send_audio=send_audio,
            clear_audio=clear_audio,
            send_initial_greeting=False,
            on_audio_turn=correct_audio,
        )
        session = _FakeSession()
        bridge.session = session
        bridge.delivery_state.apply(
            field="phone",
            action="set",
            value="09980991433",
        )

        # The live transcript can already be correct; server ASR must still own the value.
        await bridge._process_audio_turn_correction(0, b"audio", customer_phone)
        await bridge._handle_tool_call(
            types.LiveServerToolCall(
                function_calls=[
                    types.FunctionCall(
                        id="wrong-model-phone",
                        name=DELIVERY_STATE_FUNCTION,
                        args={
                            "field": "phone",
                            "action": "set",
                            "value": "09980991433",
                        },
                    )
                ]
            )
        )
        return bridge, session

    bridge, session = asyncio.run(run())

    assert bridge.delivery_state.phone == "09780771433"
    assert bridge.authoritative_phone == "09780771433"
    assert cleared == [True]
    assert session.client_content == []
    assert bridge.suppress_model_output_for_phone_readback is True
    response = session.tool_responses[0]["function_responses"][0].response
    assert response["state"]["phone"] == "09780771433"
    assert response["next_action"] == "confirm_phone"


def test_live_transcript_phone_is_authoritative_without_secondary_asr(monkeypatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr("app.gemini_bridge.genai.Client", _FakeClient)
    cleared = []

    async def send_audio(_: bytes) -> None:
        pass

    async def clear_audio() -> None:
        cleared.append(True)

    async def run() -> tuple[GeminiCallBridge, _FakeSession, str]:
        bridge = GeminiCallBridge(
            call_id="live-transcript-phone",
            call_sample_rate=16000,
            send_audio=send_audio,
            clear_audio=clear_audio,
            send_initial_greeting=False,
        )
        session = _FakeSession()
        bridge.session = session
        bridge.delivery_state.apply(
            field="phone",
            action="set",
            value="09980991433",
        )

        phone = bridge._capture_authoritative_phone(
            "သုည ကိုး ခုနစ် ရှစ် သုည ခုနစ် ခုနစ် တစ် လေး သုံး သုံး ပါ",
            source="Gemini Live transcript",
        )
        await bridge._flush_authoritative_phone_readback()
        return bridge, session, phone

    bridge, session, phone = asyncio.run(run())

    assert phone == "09780771433"
    assert bridge.delivery_state.phone == "09780771433"
    assert bridge.authoritative_phone == "09780771433"
    assert cleared == [True]
    assert session.client_content == []
    assert bridge.suppress_model_output_for_phone_readback is True


def test_confirmation_transcript_cannot_replace_authoritative_phone(monkeypatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr("app.gemini_bridge.genai.Client", _FakeClient)

    async def send_audio(_: bytes) -> None:
        pass

    bridge = GeminiCallBridge(
        call_id="misheard-phone-confirmation",
        call_sample_rate=16000,
        send_audio=send_audio,
        send_initial_greeting=False,
    )
    bridge.delivery_state.apply(
        field="phone",
        action="set",
        value="09780771433",
    )
    bridge.authoritative_phone = "09780771433"

    phone = bridge._capture_authoritative_phone(
        "ဟုတ်ကဲ့၊ ဖုန်းနံပါတ် 0970771433 က မှန်ပါတယ်ရှင်။",
        source="Gemini Live transcript",
    )

    assert phone == "09780771433"
    assert bridge.delivery_state.phone == "09780771433"
    assert bridge.authoritative_phone == "09780771433"
    assert bridge.pending_authoritative_phone_readback == ""


def test_late_live_transcript_cannot_overwrite_secondary_asr_phone(monkeypatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr("app.gemini_bridge.genai.Client", _FakeClient)

    async def send_audio(_: bytes) -> None:
        pass

    bridge = GeminiCallBridge(
        call_id="late-live-phone",
        call_sample_rate=16000,
        send_audio=send_audio,
        send_initial_greeting=False,
    )

    bridge._capture_authoritative_phone(
        "ဖုန်းနံပါတ် 09780771433 ပါရှင်။",
        source="secondary ASR",
    )
    phone = bridge._capture_authoritative_phone(
        "ဖုန်းနံပါတ် 0998399433 မဟုတ်ပါဘူးရှင်။ နံပါတ်အမှန်က 0978077133 ပါရှင်။",
        source="Gemini Live transcript",
    )

    assert phone == "09780771433"
    assert bridge.delivery_state.phone == "09780771433"
    assert bridge.authoritative_phone_source == "secondary ASR"
    assert bridge.last_phone_capture_conflicted is True


def test_misheard_repeated_digits_can_still_confirm_secondary_asr_readback(monkeypatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr("app.gemini_bridge.genai.Client", _FakeClient)

    async def send_audio(_: bytes) -> None:
        pass

    async def run() -> tuple[GeminiCallBridge, bool]:
        bridge = GeminiCallBridge(
            call_id="misheard-confirmation-digits",
            call_sample_rate=16000,
            send_audio=send_audio,
            send_initial_greeting=False,
        )
        bridge._capture_authoritative_phone(
            "ဖုန်းနံပါတ် 09780771433 ပါရှင်။",
            source="secondary ASR",
        )
        bridge._track_collection_focus("ဖုန်းနံပါတ် မှန်ပါသလားရှင်။")
        bridge._capture_authoritative_phone(
            "ဖုန်းနံပါတ် 0970771433 က မှန်ပါတယ်ရှင်။",
            source="Gemini Live transcript",
        )
        confirmed = False
        if not bridge.last_phone_capture_conflicted:
            confirmed = await bridge._confirm_authoritative_phone_from_text(
                "ဖုန်းနံပါတ် 0970771433 က မှန်ပါတယ်ရှင်။"
            )
        return bridge, confirmed

    bridge, confirmed = asyncio.run(run())

    assert confirmed is True
    assert bridge.delivery_state.phone == "09780771433"
    assert bridge.delivery_state.phone_confirmed is True


def test_later_secondary_asr_can_replace_previous_secondary_phone(monkeypatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr("app.gemini_bridge.genai.Client", _FakeClient)

    async def send_audio(_: bytes) -> None:
        pass

    bridge = GeminiCallBridge(
        call_id="secondary-new-phone",
        call_sample_rate=16000,
        send_audio=send_audio,
        send_initial_greeting=False,
    )
    bridge._capture_authoritative_phone(
        "ဖုန်းနံပါတ် 09780771433 ပါရှင်။",
        source="secondary ASR",
    )

    phone = bridge._capture_authoritative_phone(
        "ဖုန်းနံပါတ်အသစ်က 09993905153 ပါရှင်။",
        source="secondary ASR",
    )

    assert phone == "09993905153"
    assert bridge.delivery_state.phone == "09993905153"


def test_customer_transcript_confirms_authoritative_phone_without_tool_call(monkeypatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr("app.gemini_bridge.genai.Client", _FakeClient)
    transcripts = []

    async def send_audio(_: bytes) -> None:
        pass

    async def record(speaker: str, text: str) -> None:
        transcripts.append((speaker, text))

    async def run() -> tuple[GeminiCallBridge, bool]:
        bridge = GeminiCallBridge(
            call_id="transcript-phone-confirmation",
            call_sample_rate=16000,
            send_audio=send_audio,
            send_initial_greeting=False,
            on_transcript=record,
        )
        bridge.delivery_state.apply(
            field="phone",
            action="set",
            value="09780771433",
        )
        bridge.authoritative_phone = "09780771433"
        bridge._track_collection_focus("ဖုန်းနံပါတ် မှန်ပါသလားရှင်။")
        confirmed = await bridge._confirm_authoritative_phone_from_text(
            "ဟုတ်ကဲ့၊ ဖုန်းနံပါတ် 0970771433 က မှန်ပါတယ်ရှင်။"
        )
        return bridge, confirmed

    bridge, confirmed = asyncio.run(run())

    assert confirmed is True
    assert bridge.delivery_state.phone == "09780771433"
    assert bridge.delivery_state.phone_confirmed is True
    assert transcripts == [("customer", "ဖုန်းနံပါတ် 09780771433 မှန်ပါတယ်")]


def test_explicit_new_phone_replaces_authoritative_phone(monkeypatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr("app.gemini_bridge.genai.Client", _FakeClient)

    async def send_audio(_: bytes) -> None:
        pass

    bridge = GeminiCallBridge(
        call_id="explicit-new-phone",
        call_sample_rate=16000,
        send_audio=send_audio,
        send_initial_greeting=False,
    )
    bridge.delivery_state.apply(
        field="phone",
        action="set",
        value="09780771433",
    )
    bridge.authoritative_phone = "09780771433"

    phone = bridge._capture_authoritative_phone(
        "ဖုန်းနံပါတ်အသစ်က သုည ကိုး ကိုး ကိုး သုံး ကိုး သုည ငါး တစ် ငါး သုံး ပါရှင်။",
        source="Gemini Live transcript",
    )

    assert phone == "09993905153"
    assert bridge.delivery_state.phone == "09993905153"
    assert bridge.authoritative_phone == "09993905153"


def test_customer_rejection_releases_server_asr_phone_lock(monkeypatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr("app.gemini_bridge.genai.Client", _FakeClient)

    async def send_audio(_: bytes) -> None:
        pass

    async def run() -> GeminiCallBridge:
        bridge = GeminiCallBridge(
            call_id="reject-server-phone",
            call_sample_rate=16000,
            send_audio=send_audio,
            send_initial_greeting=False,
        )
        bridge.session = _FakeSession()
        bridge.delivery_state.apply(
            field="phone",
            action="set",
            value="09780771433",
        )
        bridge.authoritative_phone = "09780771433"
        await bridge._handle_tool_call(
            types.LiveServerToolCall(
                function_calls=[
                    types.FunctionCall(
                        id="reject-phone",
                        name=DELIVERY_STATE_FUNCTION,
                        args={"field": "phone", "action": "reject"},
                    )
                ]
            )
        )
        return bridge

    bridge = asyncio.run(run())

    assert bridge.authoritative_phone == ""
    assert bridge.delivery_state.phone == ""
    assert bridge.delivery_state.phone_failures == 1


def test_equivalent_country_code_phone_does_not_conflict_with_server_asr(monkeypatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr("app.gemini_bridge.genai.Client", _FakeClient)

    async def send_audio(_: bytes) -> None:
        pass

    async def run() -> tuple[GeminiCallBridge, _FakeSession]:
        bridge = GeminiCallBridge(
            call_id="country-code-phone",
            call_sample_rate=16000,
            send_audio=send_audio,
            send_initial_greeting=False,
        )
        session = _FakeSession()
        bridge.session = session
        bridge.delivery_state.apply(
            field="phone",
            action="set",
            value="09780771433",
        )
        bridge.authoritative_phone = "09780771433"
        await bridge._handle_tool_call(
            types.LiveServerToolCall(
                function_calls=[
                    types.FunctionCall(
                        id="country-code-phone",
                        name=DELIVERY_STATE_FUNCTION,
                        args={
                            "field": "phone",
                            "action": "set",
                            "value": "+959780771433",
                        },
                    )
                ]
            )
        )
        return bridge, session

    bridge, session = asyncio.run(run())

    assert bridge.delivery_state.phone == "09780771433"
    response = session.tool_responses[0]["function_responses"][0].response
    assert response["message"] == "Phone candidate replaced."
