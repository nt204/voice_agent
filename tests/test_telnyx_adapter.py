import audioop
import asyncio
import base64
import json
import unittest
from unittest.mock import patch
from types import SimpleNamespace

from fastapi.testclient import TestClient

import app.main as main
import app.config as app_config
from app.logging_utils import _safe_stdout
from app.main import RealtimeInputGate, RealtimePassthroughInput
from app.audio import pcm16_to_telnyx_payload, telnyx_payload_to_pcm16
from app.gemini_bridge import GeminiCallBridge, _automatic_activity_detection, _speech_config


class FakeBridge:
    completed_turn_count = 0

    def __init__(self) -> None:
        self.sent_frames: list[bytes] = []
        self.started = False
        self.start_count = 0
        self.ended = False
        self.committed = False
        self.muted_states: list[bool] = []
        self.turn_complete = asyncio.Event()

    def output_recent(self, seconds: float = 1.0) -> bool:
        return False

    async def start_input_activity(self) -> None:
        self.started = True
        self.start_count += 1
        self.turn_complete.clear()

    async def send_input_audio(self, pcm: bytes) -> None:
        self.sent_frames.append(pcm)

    async def end_input_activity(self) -> None:
        self.ended = True

    async def set_output_muted(self, muted: bool) -> None:
        self.muted_states.append(muted)

    async def commit_input_audio_turn(self) -> None:
        self.committed = True

    async def end_input_audio(self) -> None:
        await self.commit_input_audio_turn()


class FakeGeminiSession:
    def __init__(self) -> None:
        self.realtime_audio = []
        self.realtime_end = False
        self.activity_started = False
        self.activity_ended = False

    async def send_realtime_input(
        self,
        audio=None,
        audio_stream_end=None,
        activity_start=None,
        activity_end=None,
    ):
        if audio is not None:
            self.realtime_audio.append(audio)
        if audio_stream_end is not None:
            self.realtime_end = audio_stream_end
        if activity_start is not None:
            self.activity_started = True
        if activity_end is not None:
            self.activity_ended = True


class TelnyxAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        main.config = SimpleNamespace(
            public_base_url="https://example.ngrok-free.dev",
            telnyx=SimpleNamespace(
                stream_token="secret-token",
                stream_codec="PCMU",
                stream_sample_rate=8000,
                speech_threshold=120,
                greeting="မင်္ဂလာပါရှင်။ ဘယ်ပစ္စည်းအတွက် တိုင်ပင်ချင်ပါသလဲ။",
            ),
        )
        self.client = TestClient(main.app)

    def test_telnyx_answer_returns_bidirectional_stream_texml(self) -> None:
        response = self.client.post("/telnyx/answer")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-type"], "application/xml")
        body = response.text
        self.assertIn('<Response>', body)
        self.assertNotIn('<Say', body)
        self.assertNotIn('<Play', body)
        self.assertIn('<Connect>', body)
        self.assertIn('url="wss://example.ngrok-free.dev/telnyx/ws?token=secret-token"', body)
        self.assertIn('track="inbound_track"', body)
        self.assertIn('codec="PCMU"', body)
        self.assertIn('bidirectionalMode="rtp"', body)
        self.assertIn('bidirectionalCodec="PCMU"', body)
        self.assertIn('bidirectionalSamplingRate="8000"', body)
        self.assertIn('<Pause length="600" />', body)

    def test_telnyx_audio_helpers_convert_pcmu_payloads(self) -> None:
        pcm = b"\x00\x00\x01\x00\xff\xff\x00\x10"
        payload = pcm16_to_telnyx_payload(pcm, "PCMU")

        self.assertEqual(telnyx_payload_to_pcm16(payload, "PCMU"), audioop.ulaw2lin(payload, 2))
        self.assertEqual(telnyx_payload_to_pcm16(payload, "G711U"), audioop.ulaw2lin(payload, 2))

    def test_telnyx_websocket_rejects_bad_token(self) -> None:
        with self.assertRaises(Exception):
            with self.client.websocket_connect("/telnyx/ws?token=wrong"):
                pass

    def test_telnyx_gate_can_listen_before_gemini_initial_turn(self) -> None:
        async def run() -> FakeBridge:
            bridge = FakeBridge()
            gate = RealtimeInputGate(
                bridge,
                "telnyx-test-call",
                speech_threshold=10,
                speech_start_frames=2,
                require_initial_turn=False,
            )

            await gate.push(b"\x01\x00" * 160, rms=20)
            await gate.push(b"\x01\x00" * 160, rms=20)
            return bridge

        bridge = asyncio.run(run())

        self.assertTrue(bridge.started)
        self.assertGreaterEqual(len(bridge.sent_frames), 2)

    def test_telnyx_gate_ignores_low_rms_noise(self) -> None:
        async def run() -> FakeBridge:
            bridge = FakeBridge()
            gate = RealtimeInputGate(
                bridge,
                "telnyx-test-call",
                speech_threshold=450,
                speech_start_frames=6,
                require_initial_turn=False,
            )

            for _ in range(10):
                await gate.push(b"\x01\x00" * 160, rms=176)
            return bridge

        bridge = asyncio.run(run())

        self.assertFalse(bridge.started)
        self.assertEqual(bridge.sent_frames, [])

    def test_telnyx_gate_commits_without_waiting_for_prior_turn(self) -> None:
        async def run() -> FakeBridge:
            bridge = FakeBridge()
            gate = RealtimeInputGate(
                bridge,
                "telnyx-test-call",
                speech_threshold=10,
                speech_start_frames=1,
                speech_end_silence_frames=1,
                require_initial_turn=False,
                wait_for_turn_before_commit=False,
            )

            await gate.push(b"\x01\x00" * 160, rms=20)
            await gate.push(b"\x00\x00" * 160, rms=0)
            return bridge

        bridge = asyncio.run(run())

        self.assertTrue(bridge.ended)
        self.assertTrue(bridge.committed)

    def test_telnyx_gate_ends_quickly_after_short_silence_for_realtime_calls(self) -> None:
        async def run() -> FakeBridge:
            bridge = FakeBridge()
            gate = RealtimeInputGate(
                bridge,
                "telnyx-test-call",
                speech_threshold=450,
                speech_start_frames=3,
                speech_end_silence_frames=5,
                require_initial_turn=False,
                wait_for_turn_before_commit=False,
            )

            for index in range(3):
                await gate.push(b"\x01\x04" * 160, rms=1000, timestamp_ms=index * 20)
            for index in range(5):
                await gate.push(b"\x00\x00" * 160, rms=0, timestamp_ms=60 + index * 20)
            return bridge

        bridge = asyncio.run(run())

        self.assertTrue(bridge.started)
        self.assertTrue(bridge.ended)
        self.assertTrue(bridge.committed)

    def test_telnyx_gate_waits_for_gemini_turn_before_new_activity(self) -> None:
        async def run() -> FakeBridge:
            bridge = FakeBridge()
            bridge.turn_complete.set()
            gate = RealtimeInputGate(
                bridge,
                "telnyx-test-call",
                speech_threshold=300,
                speech_start_frames=1,
                speech_end_silence_frames=1,
                require_initial_turn=False,
                wait_for_turn_before_commit=False,
            )

            await gate.push(b"\x01\x04" * 160, rms=1000, timestamp_ms=20)
            await gate.push(b"\x00\x00" * 160, rms=0, timestamp_ms=40)
            frames_after_first_turn = len(bridge.sent_frames)

            await gate.push(b"\x01\x04" * 160, rms=1000, timestamp_ms=60)
            await gate.push(b"\x01\x04" * 160, rms=1000, timestamp_ms=80)
            self.assertEqual(bridge.start_count, 1)
            self.assertEqual(len(bridge.sent_frames), frames_after_first_turn)

            bridge.turn_complete.set()
            await gate.push(b"\x01\x04" * 160, rms=1000, timestamp_ms=100)
            return bridge

        bridge = asyncio.run(run())

        self.assertEqual(bridge.start_count, 2)
        self.assertEqual(bridge.muted_states, [True, False, True])

    def test_telnyx_passthrough_streams_every_frame_without_gate_commit(self) -> None:
        async def run() -> FakeBridge:
            bridge = FakeBridge()
            passthrough = RealtimePassthroughInput(bridge, "telnyx-test-call")

            await passthrough.push(b"\x01\x00" * 160, rms=20, timestamp_ms=20)
            await passthrough.push(b"\x00\x00" * 160, rms=0, timestamp_ms=40)
            await passthrough.force_end()
            return bridge

        bridge = asyncio.run(run())

        self.assertEqual(len(bridge.sent_frames), 2)
        self.assertFalse(bridge.started)
        self.assertFalse(bridge.ended)
        self.assertTrue(bridge.committed)

    def test_gemini_bridge_realtime_input_sends_chunks_without_buffering(self) -> None:
        async def run() -> tuple[FakeGeminiSession, GeminiCallBridge]:
            session = FakeGeminiSession()
            bridge = GeminiCallBridge.__new__(GeminiCallBridge)
            bridge.session = session
            bridge.call_sample_rate = 8000
            bridge.gemini_input_sample_rate = 16000
            bridge.input_resample_state = None
            bridge.input_turn_buffer = bytearray()
            bridge.realtime_input = True

            await GeminiCallBridge.send_input_audio(bridge, b"\x01\x00" * 160)
            await GeminiCallBridge.commit_input_audio_turn(bridge)
            return session, bridge

        session, bridge = asyncio.run(run())

        self.assertEqual(len(session.realtime_audio), 1)
        self.assertEqual(session.realtime_audio[0].mime_type, "audio/pcm;rate=16000")
        self.assertGreater(len(session.realtime_audio[0].data), 320)
        self.assertEqual(bridge.input_turn_buffer, bytearray())

    def test_gemini_bridge_explicit_vad_ends_activity_without_commit(self) -> None:
        async def run() -> tuple[FakeGeminiSession, GeminiCallBridge]:
            session = FakeGeminiSession()
            bridge = GeminiCallBridge.__new__(GeminiCallBridge)
            bridge.session = session
            bridge.call_id = "telnyx-test-call"
            bridge.realtime_input = True
            bridge.explicit_vad = True
            bridge.input_activity_active = True
            bridge.input_turn_buffer = bytearray(b"stale")

            await GeminiCallBridge.end_input_audio(bridge)
            return session, bridge

        session, bridge = asyncio.run(run())

        self.assertTrue(session.activity_ended)
        self.assertFalse(session.realtime_end)
        self.assertEqual(bridge.input_turn_buffer, bytearray(b"stale"))

    def test_gemini_bridge_clears_turn_complete_when_activity_starts(self) -> None:
        async def run() -> tuple[FakeGeminiSession, GeminiCallBridge]:
            session = FakeGeminiSession()
            bridge = GeminiCallBridge.__new__(GeminiCallBridge)
            bridge.session = session
            bridge.call_id = "telnyx-test-call"
            bridge.explicit_vad = True
            bridge.input_activity_active = False
            bridge.turn_complete = asyncio.Event()
            bridge.turn_complete.set()

            await GeminiCallBridge.start_input_activity(bridge)
            return session, bridge

        session, bridge = asyncio.run(run())

        self.assertTrue(session.activity_started)
        self.assertTrue(bridge.input_activity_active)
        self.assertFalse(bridge.turn_complete.is_set())

    def test_explicit_vad_config_disables_automatic_detection_only(self) -> None:
        vad = _automatic_activity_detection(explicit_vad=True)

        self.assertTrue(vad.disabled)
        self.assertIsNone(vad.start_of_speech_sensitivity)
        self.assertIsNone(vad.end_of_speech_sensitivity)
        self.assertIsNone(vad.silence_duration_ms)

    def test_speech_config_forces_myanmar_live_language(self) -> None:
        speech = _speech_config()

        self.assertEqual(speech.language_code, "my-MM")

    def test_system_instruction_requires_short_realtime_sales_replies(self) -> None:
        instruction = app_config.gemini_system_instruction()

        self.assertIn("မြန်မာဘာသာဖြင့်သာ", instruction)
        self.assertIn("နောက်ဆက်တွဲမေးခွန်းကို ၁ ခုသာ မေးပါ", instruction)
        self.assertIn("နောက်ဆုံးအသံဖြေကြားစည်းကမ်း", instruction)
        self.assertIn("what is that", instruction)
        self.assertIn("never stay silent", instruction)

    def test_safe_stdout_does_not_crash_on_vietnamese_text(self) -> None:
        class FakeStdout:
            encoding = "cp1252"

            def __init__(self) -> None:
                self.value = ""

            def write(self, value: str) -> int:
                value.encode(self.encoding)
                self.value += value
                return len(value)

            def flush(self) -> None:
                pass

        fake_stdout = FakeStdout()
        with patch("sys.stdout", fake_stdout):
            _safe_stdout("Gemini: အသံကြားရပါတယ်ရှင်")

        self.assertIn("Gemini:", fake_stdout.value)


if __name__ == "__main__":
    unittest.main()
