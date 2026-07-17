import asyncio
import io
import wave

import pytest

import app.main as main
from app.gemini_bridge import GeminiCallBridge
from app.secondary_asr import (
    SecondaryAsrTranscriber,
    build_batch_transcription_prompt,
    build_transcription_prompt,
    clean_transcript_response,
    pcm16_to_wav,
)


def test_pcm16_is_wrapped_as_valid_mono_wav() -> None:
    pcm = b"\x01\x00" * 320

    wav_bytes = pcm16_to_wav(pcm, 16000)

    with wave.open(io.BytesIO(wav_bytes), "rb") as audio:
        assert audio.getnchannels() == 1
        assert audio.getsampwidth() == 2
        assert audio.getframerate() == 16000
        assert audio.readframes(audio.getnframes()) == pcm


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Transcript: ကွန်ဘိုတစ်ခု ဝယ်ချင်တယ်။", "ကွန်ဘိုတစ်ခု ဝယ်ချင်တယ်။"),
        ("```text\n지금 몇 시예요?\n```", "지금 몇 시예요?"),
        ("[unclear]", ""),
    ],
)
def test_secondary_asr_response_is_cleaned_without_translation(raw: str, expected: str) -> None:
    assert clean_transcript_response(raw) == expected


class _FakeModels:
    def __init__(self) -> None:
        self.kwargs = None

    async def generate_content(self, **kwargs):
        self.kwargs = kwargs
        return type("Response", (), {"text": "ကွန်ဘိုတစ်ခု ဝယ်ချင်တယ်။"})()


class _FakeClient:
    def __init__(self) -> None:
        self.aio = type("Aio", (), {"models": _FakeModels()})()


def test_secondary_asr_sends_audio_to_configured_model() -> None:
    client = _FakeClient()
    transcriber = SecondaryAsrTranscriber(client=client, model="test-asr-model")

    result = asyncio.run(
        transcriber.transcribe(
            b"\x01\x00" * 3200,
            16000,
            live_candidate="지금 몇 시예요?",
        )
    )

    assert result == "ကွန်ဘိုတစ်ခု ဝယ်ချင်တယ်။"
    assert client.aio.models.kwargs["model"] == "test-asr-model"
    request_config = client.aio.models.kwargs["config"]
    assert request_config.thinking_config.thinking_budget == 0
    assert request_config.max_output_tokens >= 500


def test_secondary_asr_prompt_prioritizes_expected_customer_languages() -> None:
    prompt = build_transcription_prompt(
        live_candidate="wrong-script candidate",
        language_priority="Burmese, Myanmar English",
    )

    assert "Expected customer languages, in priority order: Burmese, Myanmar English" in prompt
    assert "audio remains the source of truth" in prompt
    assert "independent of any Live ASR candidate" in prompt


def test_secondary_asr_prompts_recognize_burmese_phone_digit_words() -> None:
    single_prompt = build_transcription_prompt()
    batch_prompt = build_batch_transcription_prompt()

    for prompt in (single_prompt, batch_prompt):
        assert "Burmese phone digits" in prompt
        assert "0 = သုည or ဝ" in prompt
        assert "1 = တစ်" in prompt
        assert "2 = နှစ်" in prompt
        assert "3 = သုံး" in prompt
        assert "4 = လေး" in prompt
        assert "5 = ငါး" in prompt
        assert "6 = ခြောက်" in prompt
        assert "7 = ခုနစ် or ခုနှစ်" in prompt
        assert "8 = ရှစ်" in prompt
        assert "9 = ကိုး" in prompt
        assert "one digit at a time" in prompt
        assert "Pauses between digits do not mean the phone number has ended" in prompt


class _FakeLiveSession:
    def __init__(self) -> None:
        self.client_content = []

    async def send_realtime_input(self, **kwargs) -> None:
        pass

    async def send_client_content(self, **kwargs) -> None:
        self.client_content.append(kwargs)


class _FakeGenaiClient:
    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs


def test_bridge_records_and_replays_secondary_asr_transcript(monkeypatch) -> None:
    cleared = []
    recorded = []
    live_candidates = []

    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr("app.gemini_bridge.genai.Client", _FakeGenaiClient)

    async def on_audio_turn(
        audio: bytes,
        sample_rate: int,
        turn_number: int,
        live_candidate: str,
    ) -> str:
        live_candidates.append(live_candidate)
        return "ကွန်ဘိုတစ်ခု ဝယ်ချင်တယ်။"

    async def on_transcript(speaker: str, text: str) -> None:
        recorded.append((speaker, text))

    async def send_audio(_: bytes) -> None:
        pass

    async def clear_audio() -> None:
        cleared.append(True)

    async def run() -> _FakeLiveSession:
        bridge = GeminiCallBridge(
            call_id="fallback-turn",
            call_sample_rate=16000,
            send_audio=send_audio,
            clear_audio=clear_audio,
            explicit_vad=True,
            realtime_input=True,
            send_initial_greeting=False,
            on_transcript=on_transcript,
            on_audio_turn=on_audio_turn,
        )
        session = _FakeLiveSession()
        bridge.session = session
        await bridge.start_input_activity()
        await bridge.send_input_audio(b"\x01\x00" * 320)
        bridge.realtime_live_transcript_parts.append("지금 몇 시예요?")
        await bridge.end_input_activity()
        await bridge.wait_for_audio_turns()
        return session

    session = asyncio.run(run())

    assert cleared == [True]
    assert live_candidates == ["지금 몇 시예요?"]
    assert recorded == []
    assert len(session.client_content) == 1
    content = session.client_content[0]["turns"]
    assert content.role == "user"
    assert content.parts[0].text == "ကွန်ဘိုတစ်ခု ဝယ်ချင်တယ်။"


def test_bridge_does_not_replay_when_secondary_asr_matches_live_transcript(monkeypatch) -> None:
    recorded = []

    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr("app.gemini_bridge.genai.Client", _FakeGenaiClient)

    async def on_audio_turn(
        audio: bytes,
        sample_rate: int,
        turn_number: int,
        live_candidate: str,
    ) -> str:
        return "ကွန်ဘိုတစ်ခု ဝယ်ချင်တယ်။"

    async def on_transcript(speaker: str, text: str) -> None:
        recorded.append((speaker, text))

    async def send_audio(_: bytes) -> None:
        pass

    async def run() -> _FakeLiveSession:
        bridge = GeminiCallBridge(
            call_id="same-turn",
            call_sample_rate=16000,
            send_audio=send_audio,
            explicit_vad=True,
            realtime_input=True,
            send_initial_greeting=False,
            on_transcript=on_transcript,
            on_audio_turn=on_audio_turn,
        )
        session = _FakeLiveSession()
        bridge.session = session
        await bridge.start_input_activity()
        await bridge.send_input_audio(b"\x01\x00" * 320)
        bridge.realtime_live_transcript_parts.append("ကွန်ဘိုတစ်ခု ဝယ်ချင်တယ်။")
        await bridge.end_input_activity()
        await bridge.wait_for_audio_turns()
        return session

    session = asyncio.run(run())

    assert recorded == []
    assert session.client_content == []


def test_telnyx_audio_turn_handler_uses_secondary_asr(monkeypatch) -> None:
    calls = []
    original_enabled = main.config.gemini.secondary_asr_enabled
    original_in_call_enabled = main.config.gemini.in_call_secondary_asr_enabled

    object.__setattr__(main.config.gemini, "secondary_asr_enabled", True)
    object.__setattr__(main.config.gemini, "in_call_secondary_asr_enabled", True)

    class FakeTranscriber:
        async def transcribe(self, audio: bytes, sample_rate: int, live_candidate: str) -> str:
            calls.append((audio, sample_rate, live_candidate))
            return "တောင်မိုးမိုး 1 combo"

    monkeypatch.setattr("app.secondary_asr.SecondaryAsrTranscriber", FakeTranscriber)

    try:
        handler = main._telnyx_audio_turn_handler("call-secondary")

        assert handler is not None
        result = asyncio.run(handler(b"\x01\x00" * 320, 16000, 0, "Hello."))

        assert result == "တောင်မိုးမိုး 1 combo"
        assert calls == [(b"\x01\x00" * 320, 16000, "Hello.")]
    finally:
        object.__setattr__(main.config.gemini, "secondary_asr_enabled", original_enabled)
        object.__setattr__(
            main.config.gemini,
            "in_call_secondary_asr_enabled",
            original_in_call_enabled,
        )


def test_telnyx_audio_turn_handler_disabled_when_secondary_asr_disabled() -> None:
    original_enabled = main.config.gemini.secondary_asr_enabled
    original_in_call_enabled = main.config.gemini.in_call_secondary_asr_enabled
    object.__setattr__(main.config.gemini, "secondary_asr_enabled", False)
    object.__setattr__(main.config.gemini, "in_call_secondary_asr_enabled", True)

    try:
        assert main._telnyx_audio_turn_handler("call-secondary") is None
    finally:
        object.__setattr__(main.config.gemini, "secondary_asr_enabled", original_enabled)
        object.__setattr__(
            main.config.gemini,
            "in_call_secondary_asr_enabled",
            original_in_call_enabled,
        )


def test_telnyx_audio_turn_handler_disabled_for_immediate_replies() -> None:
    original_enabled = main.config.gemini.secondary_asr_enabled
    original_in_call_enabled = main.config.gemini.in_call_secondary_asr_enabled
    object.__setattr__(main.config.gemini, "secondary_asr_enabled", True)
    object.__setattr__(main.config.gemini, "in_call_secondary_asr_enabled", False)

    try:
        assert main._telnyx_audio_turn_handler("call-secondary") is None
    finally:
        object.__setattr__(main.config.gemini, "secondary_asr_enabled", original_enabled)
        object.__setattr__(
            main.config.gemini,
            "in_call_secondary_asr_enabled",
            original_in_call_enabled,
        )


class _BatchModels:
    def __init__(self) -> None:
        self.calls = []

    async def generate_content(self, **kwargs):
        self.calls.append(kwargs)
        return type(
            "Response",
            (),
            {
                "text": (
                    '{"turns":['
                    '{"index":0,"text":"ကွန်ဘိုတစ်ခု ဝယ်ချင်တယ်"},'
                    '{"index":1,"text":"Combo 2 က ဘယ်လိုလဲ"}'
                    "]}"
                )
            },
        )()


class _BatchClient:
    def __init__(self) -> None:
        self.models = _BatchModels()
        self.aio = type("Aio", (), {"models": self.models})()


def test_secondary_asr_batches_all_completed_turns_in_one_request() -> None:
    client = _BatchClient()
    transcriber = SecondaryAsrTranscriber(client=client, model="batch-asr-model")
    audio = b"\x01\x00" * 3200

    result = asyncio.run(
        transcriber.transcribe_many(
            [
                (0, audio, 16000, "wrong live text"),
                (1, audio, 16000, "wrong live text"),
            ]
        )
    )

    assert result == {
        0: "ကွန်ဘိုတစ်ခု ဝယ်ချင်တယ်",
        1: "Combo 2 က ဘယ်လိုလဲ",
    }
    assert len(client.models.calls) == 1
    assert client.models.calls[0]["model"] == "batch-asr-model"
    request_config = client.models.calls[0]["config"]
    assert request_config.thinking_config.thinking_budget == 0


def test_post_call_asr_reuses_in_call_results(monkeypatch) -> None:
    original_enabled = main.config.gemini.secondary_asr_enabled
    object.__setattr__(main.config.gemini, "secondary_asr_enabled", True)
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr("app.gemini_bridge.genai.Client", _FakeGenaiClient)

    class ShouldNotRun:
        def __init__(self):
            raise AssertionError("cached ASR result should be reused")

    class Store:
        def __init__(self) -> None:
            self.updates = []

        def update_customer_transcript_by_index(self, call_id, index, text) -> None:
            self.updates.append((call_id, index, text))

    monkeypatch.setattr("app.secondary_asr.SecondaryAsrTranscriber", ShouldNotRun)
    try:
        bridge = GeminiCallBridge(
            call_id="cached-asr",
            call_sample_rate=16000,
            send_audio=lambda _: None,
            send_initial_greeting=False,
        )
        bridge.completed_turns_audio = [(0, b"\x01\x00" * 3200, "wrong")]
        bridge.secondary_asr_results = {0: "correct"}
        store = Store()

        asyncio.run(bridge.run_post_call_asr(store))

        assert store.updates == [("cached-asr", 0, "correct")]
    finally:
        object.__setattr__(main.config.gemini, "secondary_asr_enabled", original_enabled)


def test_call_finalization_waits_for_asr_before_sales_extraction() -> None:
    events = []

    class Bridge:
        async def finalize_transcript(self, store) -> None:
            events.append("asr")

        async def close(self) -> None:
            events.append("close")

    class Store:
        def finish_call(self, call_id) -> None:
            events.append(f"extract:{call_id}")

    asyncio.run(main._finalize_call(Bridge(), "ordered-finalization", Store()))

    assert events == ["asr", "close", "extract:ordered-finalization"]
