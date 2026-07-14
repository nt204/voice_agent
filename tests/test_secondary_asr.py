import asyncio
import io
import wave

import pytest

import app.main as main
from app.gemini_bridge import GeminiCallBridge
from app.secondary_asr import (
    SecondaryAsrTranscriber,
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
        ("Transcript: Tôi muốn mua một combo.", "Tôi muốn mua một combo."),
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
        return type("Response", (), {"text": "Tôi muốn mua một combo."})()


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

    assert result == "Tôi muốn mua một combo."
    assert client.aio.models.kwargs["model"] == "test-asr-model"


def test_secondary_asr_prompt_prioritizes_expected_customer_languages() -> None:
    prompt = build_transcription_prompt(
        live_candidate="wrong-script candidate",
        language_priority="Vietnamese, Myanmar",
    )

    assert "Expected customer languages, in priority order: Vietnamese, Myanmar" in prompt
    assert "Vietnamese phone speech is often misheard as Myanmar or Korean" in prompt
    assert "Do not output Myanmar or Korean text unless the audio clearly supports it" in prompt


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
        return "Tôi muốn mua một combo."

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
    assert recorded == [("customer_recovered", "Tôi muốn mua một combo.")]
    assert len(session.client_content) == 1
    content = session.client_content[0]["turns"]
    assert content.role == "user"
    assert content.parts[0].text == "Tôi muốn mua một combo."


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
        return "Tôi muốn mua một combo."

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
        bridge.realtime_live_transcript_parts.append("Tôi muốn mua một combo.")
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
