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


def test_partial_phone_after_rejection_stays_in_keypad_flow() -> None:
    state = LiveDeliveryState()
    state.apply(field="phone", action="set", value="09797714333")
    state.apply(field="phone", action="reject")

    result = state.apply(field="phone", action="set", value="095003")

    assert result["ok"] is False
    assert state.phone == ""
    assert result["next_action"] == "collect_phone_by_keypad"


def test_phone_moves_to_keypad_only_after_repeated_listening_failures() -> None:
    state = LiveDeliveryState()
    for _ in range(2):
        result = state.apply(field="phone", action="set", value="095003")
        assert result["next_action"] == "ask_phone"

    result = state.apply(field="phone", action="set", value="095003")

    assert result["next_action"] == "collect_phone_by_keypad"


def test_phone_moves_to_keypad_after_first_rejection() -> None:
    state = LiveDeliveryState()
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
        "customer_name": "",
        "phone": "09789119333",
        "shipping_address": "အမှတ် ၉၈၊ ဟံသာဝတီလမ်း၊ အရှေ့ဒဂုံမြို့နယ်",
    }


class _FakeSession:
    def __init__(self) -> None:
        self.tool_responses = []
        self.client_content = []
        self.realtime_inputs = []

    async def send_tool_response(self, **kwargs) -> None:
        self.tool_responses.append(kwargs)

    async def send_client_content(self, **kwargs) -> None:
        self.client_content.append(kwargs)

    async def send_realtime_input(self, **kwargs) -> None:
        self.realtime_inputs.append(kwargs)


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
    assert bridge.confirmed_fact_values["phone"] == "09789119333"
    assert transcripts == []


def test_campaign_accepts_complete_dtmf_phone_even_when_customer_enters_early(monkeypatch) -> None:
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
            initial_phone="09793905153",
            campaign_confirmation_mode=True,
        )
        session = _FakeSession()
        bridge.session = session
        for digit in "0965198457#":
            await bridge.handle_dtmf(digit)
        return bridge, session

    bridge, session = asyncio.run(run())

    assert bridge.delivery_state.phone == "0965198457"
    assert bridge.delivery_state.phone_confirmed is False
    assert bridge.authoritative_phone_source == "keypad"
    assert "phone" not in bridge.confirmed_fact_values
    assert transcripts == []
    assert sent_audio == []
    assert len(session.client_content) == 1
    instruction = session.client_content[0]["turns"].parts[0].text
    assert "0965198457" in instruction
    assert "SYSTEM DTMF EVENT" in instruction
    assert "read every digit exactly once" in instruction
    assert "authoritative, unconfirmed phone" in instruction
    assert "Do not ask for name, address" in instruction


def test_invalid_keypad_phone_prompts_for_complete_reentry(monkeypatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr("app.gemini_bridge.genai.Client", _FakeClient)

    async def send_audio(_: bytes) -> None:
        pass

    async def run() -> tuple[GeminiCallBridge, _FakeSession]:
        bridge = GeminiCallBridge(
            call_id="invalid-dtmf-phone",
            call_sample_rate=16000,
            send_audio=send_audio,
            send_initial_greeting=False,
            initial_phone="09793905153",
            campaign_confirmation_mode=True,
        )
        session = _FakeSession()
        bridge.session = session
        await bridge._handle_tool_call(
            types.LiveServerToolCall(
                function_calls=[
                    types.FunctionCall(
                        id="reject-phone-before-invalid-keypad",
                        name=DELIVERY_STATE_FUNCTION,
                        args={"field": "phone", "action": "reject"},
                    )
                ]
            )
        )
        for digit in "019648180#":
            await bridge.handle_dtmf(digit)
        return bridge, session

    bridge, session = asyncio.run(run())

    assert bridge.delivery_state.phone == ""
    assert bridge.authoritative_phone == ""
    assert bridge.awaiting_keypad_phone is True
    assert len(session.client_content) == 1
    instruction = session.client_content[0]["turns"].parts[0].text
    assert "incomplete or not a valid delivery phone number" in instruction
    assert "again from the beginning and press #" in instruction


def test_campaign_turn_opens_only_on_gemini_turn_complete(monkeypatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr("app.gemini_bridge.genai.Client", _FakeClient)

    async def send_audio(_: bytes) -> None:
        pass

    async def run() -> tuple[GeminiCallBridge, bool]:
        bridge = GeminiCallBridge(
            call_id="single-turn-completion",
            call_sample_rate=16000,
            send_audio=send_audio,
            send_initial_greeting=False,
            campaign_confirmation_mode=True,
        )
        bridge.session = _FakeSession()
        bridge.turn_complete.clear()
        bridge._track_phone_readback_transcript("၀ ၉ ၆ only a partial readback")
        still_closed = not bridge.turn_complete.is_set()
        completed = bridge._handle_model_turn_complete()
        return bridge, still_closed and completed

    bridge, completed_only_by_event = asyncio.run(run())

    assert completed_only_by_event is True
    assert bridge.turn_complete.is_set() is True


def test_campaign_timeout_asks_customer_to_repeat_without_confirming_state(monkeypatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr("app.gemini_bridge.genai.Client", _FakeClient)
    monkeypatch.setattr("app.gemini_bridge.CAMPAIGN_RESPONSE_TIMEOUT_SECONDS", 0.01)
    cleared = []

    async def send_audio(_: bytes) -> None:
        pass

    async def clear_audio() -> None:
        cleared.append(True)

    async def interrupt_stalled(bridge: GeminiCallBridge) -> None:
        await bridge._clear_pending_output_audio()
        bridge.turn_complete.clear()

    monkeypatch.setattr(
        GeminiCallBridge,
        "_interrupt_stalled_campaign_turn",
        interrupt_stalled,
    )

    async def run() -> tuple[GeminiCallBridge, _FakeSession]:
        bridge = GeminiCallBridge(
            call_id="campaign-response-timeout",
            call_sample_rate=16000,
            send_audio=send_audio,
            clear_audio=clear_audio,
            send_initial_greeting=False,
            campaign_confirmation_mode=True,
        )
        session = _FakeSession()
        bridge.session = session
        bridge.turn_complete.clear()
        bridge._start_campaign_response_watchdog("test turn")
        await asyncio.sleep(0.03)
        return bridge, session

    bridge, session = asyncio.run(run())

    assert bridge.turn_complete.is_set() is False
    assert bridge.delivery_state.confirmed_facts()["phone"] == ""
    assert "ask the customer to repeat" in session.client_content[0]["turns"].parts[0].text
    assert cleared


def test_campaign_does_not_cut_phone_audio_from_output_transcript(monkeypatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr("app.gemini_bridge.genai.Client", _FakeClient)
    cleared = []

    async def send_audio(_: bytes) -> None:
        pass

    async def clear_audio() -> None:
        cleared.append(True)

    async def run() -> GeminiCallBridge:
        bridge = GeminiCallBridge(
            call_id="dtmf-readback-complete-question",
            call_sample_rate=16000,
            send_audio=send_audio,
            clear_audio=clear_audio,
            send_initial_greeting=False,
            campaign_confirmation_mode=True,
        )
        bridge.turn_complete.clear()
        bridge._track_phone_readback_transcript(
            "ဖုန်းနံပါတ်က ၀ ၉ ၆ ၁ ၉ ၈ ၄ ၂ ၀ ၄ မှန်ပါသလား"
        )
        return bridge

    bridge = asyncio.run(run())

    assert cleared == []
    assert bridge.turn_complete.is_set() is False


def test_keypad_phone_ignores_speech_but_can_be_rejected_for_new_keypad_entry(monkeypatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr("app.gemini_bridge.genai.Client", _FakeClient)

    async def send_audio(_: bytes) -> None:
        pass

    async def run() -> GeminiCallBridge:
        bridge = GeminiCallBridge(
            call_id="keypad-lock",
            call_sample_rate=16000,
            send_audio=send_audio,
            send_initial_greeting=False,
        )
        bridge.session = _FakeSession()
        for digit in "09967954280#":
            await bridge.handle_dtmf(digit)

        bridge._capture_authoritative_phone(
            "ဖုန်းနံပါတ် 0996552800 ပါ",
            source="Gemini Live transcript",
        )
        bridge._capture_authoritative_phone(
            "ဖုန်းနံပါတ် 0996954220 ပါ",
            source="secondary ASR",
        )
        await bridge._handle_tool_call(
            types.LiveServerToolCall(
                function_calls=[
                    types.FunctionCall(
                        id="reject-keypad-phone",
                        name=DELIVERY_STATE_FUNCTION,
                        args={"field": "phone", "action": "reject"},
                    )
                ]
            )
        )
        return bridge

    bridge = asyncio.run(run())

    assert bridge.authoritative_phone == ""
    assert bridge.authoritative_phone_source == ""
    assert bridge.delivery_state.phone == ""
    assert bridge.delivery_state.phone_confirmed is False
    assert "phone" not in bridge.confirmed_fact_values


def test_keypad_phone_is_appended_after_final_asr_for_order_extraction(monkeypatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr("app.gemini_bridge.genai.Client", _FakeClient)

    class Store:
        def __init__(self) -> None:
            self.transcripts = []

        def add_transcript(self, call_id: str, speaker: str, text: str) -> None:
            self.transcripts.append((call_id, speaker, text))

    async def send_audio(_: bytes) -> None:
        pass

    async def run() -> tuple[GeminiCallBridge, Store]:
        bridge = GeminiCallBridge(
            call_id="keypad-final-fact",
            call_sample_rate=16000,
            send_audio=send_audio,
            send_initial_greeting=False,
        )
        for digit in "09967954280#":
            await bridge.handle_dtmf(digit)
        bridge._track_collection_focus("ဖုန်းနံပါတ် မှန်ပါသလားရှင်။")
        assert await bridge._confirm_authoritative_phone_from_text("ဟုတ်ကဲ့ မှန်ပါတယ်")
        store = Store()
        await bridge.finalize_transcript(store)
        return bridge, store

    bridge, store = asyncio.run(run())

    assert bridge.transcript_finalized is True
    assert store.transcripts == [
        ("keypad-final-fact", "customer", "ဖုန်းနံပါတ် 09967954280 မှန်ပါတယ်")
    ]


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
    assert len(session.client_content) == 1
    instruction = session.client_content[0]["turns"].parts[0].text
    assert "09780771433" in instruction
    assert "read exactly these digits one by one" in instruction
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
        return bridge, session, phone

    bridge, session, phone = asyncio.run(run())

    assert phone == "09780771433"
    assert bridge.delivery_state.phone == "09780771433"
    assert bridge.authoritative_phone == "09780771433"
    assert bridge.pending_authoritative_phone_readback == "09780771433"
    assert cleared == []
    assert session.client_content == []


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
    assert bridge.confirmed_fact_values["phone"] == "09780771433"
    assert transcripts == []


def test_spanish_si_asr_artifact_confirms_phone_readback(monkeypatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr("app.gemini_bridge.genai.Client", _FakeClient)

    async def send_audio(_: bytes) -> None:
        pass

    async def run() -> tuple[GeminiCallBridge, bool]:
        bridge = GeminiCallBridge(
            call_id="si-phone-confirmation",
            call_sample_rate=16000,
            send_audio=send_audio,
            send_initial_greeting=False,
        )
        bridge.delivery_state.apply(
            field="phone",
            action="set",
            value="0961984204",
        )
        bridge.authoritative_phone = "0961984204"
        bridge._track_collection_focus("ဖုန်းနံပါတ် မှန်ပါသလားရှင်။")
        confirmed = await bridge._confirm_authoritative_phone_from_text("Sí.")
        return bridge, confirmed

    bridge, confirmed = asyncio.run(run())

    assert confirmed is True
    assert bridge.delivery_state.phone_confirmed is True


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


def test_campaign_never_runs_secondary_asr_during_the_call(monkeypatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr("app.gemini_bridge.genai.Client", _FakeClient)

    async def send_audio(_: bytes) -> None:
        pass

    async def run() -> tuple[bool, bool]:
        bridge = GeminiCallBridge(
            call_id="campaign-asr-scope",
            call_sample_rate=16000,
            send_audio=send_audio,
            send_initial_greeting=False,
            initial_phone="09793905153",
            campaign_confirmation_mode=True,
        )
        bridge._track_collection_focus("Combo 2 အရေအတွက် မှန်ပါသလားရှင်။")
        product_turn = bridge._needs_in_call_phone_asr("ဟုတ်ကဲ့")
        bridge._track_collection_focus("ဖုန်းနံပါတ် မှန်ပါသလားရှင်။")
        phone_turn = bridge._needs_in_call_phone_asr("ဟုတ်ကဲ့")
        return product_turn, phone_turn

    product_turn, phone_turn = asyncio.run(run())

    assert product_turn is False
    assert phone_turn is False


def test_campaign_phone_confirmation_continues_from_tool_response_only(monkeypatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr("app.gemini_bridge.genai.Client", _FakeClient)
    address = "အမှတ် 99 ဟံသာဝတီ လမ်း အရှေ့ဒဂုံ မြို့နယ် ရန်ကုန်"

    async def send_audio(_: bytes) -> None:
        pass

    async def run() -> tuple[GeminiCallBridge, _FakeSession]:
        bridge = GeminiCallBridge(
            call_id="campaign-phone-next-step",
            call_sample_rate=16000,
            send_audio=send_audio,
            send_initial_greeting=False,
            initial_customer_name="Thaw Zin",
            initial_phone="09793905153",
            initial_shipping_address=address,
            require_customer_name=True,
            campaign_confirmation_mode=True,
        )
        session = _FakeSession()
        bridge.session = session
        await bridge._handle_tool_call(
            types.LiveServerToolCall(
                function_calls=[
                    types.FunctionCall(
                        id="confirm-campaign-phone",
                        name=DELIVERY_STATE_FUNCTION,
                        args={"field": "phone", "action": "confirm"},
                    )
                ]
            )
        )
        return bridge, session

    bridge, session = asyncio.run(run())

    assert bridge.delivery_state.phone_confirmed is True
    assert session.client_content == []
    response = session.tool_responses[0]["function_responses"][0].response
    assert response["next_action"] == "confirm_customer_name"
    assert "Thaw Zin" in response["instruction"]


def test_campaign_address_correction_is_stored_by_tool_without_audio_injection(monkeypatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr("app.gemini_bridge.genai.Client", _FakeClient)
    old_address = "အမှတ် 99 ဟံသာဝတီ လမ်း အရှေ့ဒဂုံ မြို့နယ် ရန်ကုန်"
    new_address = "အမှတ် 12 ပြည်လမ်း ကမာရွတ် မြို့နယ် ရန်ကုန်"

    async def send_audio(_: bytes) -> None:
        pass

    async def run() -> tuple[GeminiCallBridge, _FakeSession]:
        bridge = GeminiCallBridge(
            call_id="campaign-address-correction",
            call_sample_rate=16000,
            send_audio=send_audio,
            send_initial_greeting=False,
            initial_shipping_address=old_address,
            campaign_confirmation_mode=True,
        )
        session = _FakeSession()
        bridge.session = session
        await bridge._handle_tool_call(
            types.LiveServerToolCall(
                function_calls=[
                    types.FunctionCall(
                        id="reject-old-address",
                        name=DELIVERY_STATE_FUNCTION,
                        args={"field": "shipping_address", "action": "reject"},
                    ),
                    types.FunctionCall(
                        id="set-new-address",
                        name=DELIVERY_STATE_FUNCTION,
                        args={
                            "field": "shipping_address",
                            "action": "set",
                            "value": new_address,
                        },
                    ),
                    types.FunctionCall(
                        id="confirm-new-address",
                        name=DELIVERY_STATE_FUNCTION,
                        args={"field": "shipping_address", "action": "confirm"},
                    ),
                ]
            )
        )
        return bridge, session

    bridge, session = asyncio.run(run())

    assert old_address not in bridge.delivery_state.confirmed_facts().values()
    assert bridge.delivery_state.confirmed_facts()["shipping_address"] == new_address
    assert session.client_content == []


def test_campaign_requires_real_recipient_name_when_sheet_has_only_honorific() -> None:
    state = LiveDeliveryState(require_customer_name=True)

    result = state.apply(field="customer_name", action="set", value="မမ")

    assert result["ok"] is False
    assert result["next_action"] == "ask_customer_name"
    assert state.customer_name == ""
