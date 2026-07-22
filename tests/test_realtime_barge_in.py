import asyncio

from google.genai import types

import app.gemini_bridge as gemini_bridge
from app.main import RealtimeInputGate, _telnyx_input_gate_options


class _FakeBridge:
    def __init__(self) -> None:
        self.turn_complete = asyncio.Event()
        self.completed_turn_count = 1
        self.muted = []
        self.started = 0
        self.frames = []

    def output_recent(self, seconds: float) -> bool:
        return True

    async def set_output_muted(self, muted: bool) -> None:
        self.muted.append(muted)

    async def start_input_activity(self) -> None:
        self.started += 1

    async def send_input_audio(self, pcm: bytes) -> None:
        self.frames.append(pcm)


def test_barge_in_accepts_strong_speech_while_waiting_for_response() -> None:
    async def run() -> _FakeBridge:
        bridge = _FakeBridge()
        gate = RealtimeInputGate(
            bridge,
            "barge-in",
            speech_threshold=300,
            speech_start_frames=2,
            speech_end_silence_frames=2,
            barge_in_threshold=900,
            allow_barge_in=True,
        )
        gate.waiting_for_response = True

        await gate.push(b"\x01\x00" * 160, 1200)
        await gate.push(b"\x01\x00" * 160, 1200)
        return bridge

    bridge = asyncio.run(run())

    assert bridge.muted == [True]
    assert bridge.started == 1
    assert len(bridge.frames) == 2


def test_activity_handling_interrupts_when_barge_in_is_enabled() -> None:
    assert (
        gemini_bridge._activity_handling(True)
        == types.ActivityHandling.START_OF_ACTIVITY_INTERRUPTS
    )
    assert (
        gemini_bridge._activity_handling(False)
        == types.ActivityHandling.NO_INTERRUPTION
    )


def test_barge_in_rejects_echo_below_the_barge_in_threshold() -> None:
    async def run() -> _FakeBridge:
        bridge = _FakeBridge()
        gate = RealtimeInputGate(
            bridge,
            "barge-in-echo",
            speech_threshold=300,
            speech_start_frames=2,
            barge_in_threshold=900,
            allow_barge_in=True,
        )
        gate.waiting_for_response = True

        for _ in range(5):
            await gate.push(b"\x01\x00" * 160, 700)
        return bridge

    bridge = asyncio.run(run())

    assert bridge.muted == []
    assert bridge.started == 0
    assert bridge.frames == []


def test_barge_in_can_be_disabled() -> None:
    async def run() -> _FakeBridge:
        bridge = _FakeBridge()
        gate = RealtimeInputGate(
            bridge,
            "barge-in-disabled",
            speech_threshold=300,
            speech_start_frames=2,
            barge_in_threshold=900,
            allow_barge_in=False,
        )
        gate.waiting_for_response = True

        await gate.push(b"\x01\x00" * 160, 1200)
        await gate.push(b"\x01\x00" * 160, 1200)
        return bridge

    bridge = asyncio.run(run())

    assert bridge.muted == []
    assert bridge.started == 0
    assert bridge.frames == []


def test_campaign_confirmation_ignores_recent_output_echo() -> None:
    async def run() -> _FakeBridge:
        bridge = _FakeBridge()
        gate = RealtimeInputGate(
            bridge,
            "campaign-readback-echo",
            speech_threshold=300,
            speech_start_frames=2,
            barge_in_threshold=900,
            allow_barge_in=True,
            campaign_confirmation_mode=True,
        )

        for _ in range(5):
            await gate.push(b"\x01\x00" * 160, 1400)
        return bridge

    bridge = asyncio.run(run())

    assert bridge.muted == []
    assert bridge.started == 0
    assert bridge.frames == []


def test_dtmf_entry_blocks_key_tones_from_starting_a_speech_turn() -> None:
    async def run() -> _FakeBridge:
        bridge = _FakeBridge()
        bridge.dtmf_digits = ""
        bridge.awaiting_keypad_phone = True
        gate = RealtimeInputGate(
            bridge,
            "dtmf-audio-block",
            speech_threshold=300,
            speech_start_frames=2,
            campaign_confirmation_mode=True,
        )

        for _ in range(8):
            await gate.push(b"\x01\x00" * 160, 1800)
        return bridge

    bridge = asyncio.run(run())

    assert bridge.muted == []
    assert bridge.started == 0
    assert bridge.frames == []


def test_campaign_uses_one_sensitive_vad_profile_for_soft_answers() -> None:
    class SoftConfirmationBridge(_FakeBridge):
        def output_recent(self, seconds: float) -> bool:
            return False

    async def run() -> SoftConfirmationBridge:
        bridge = SoftConfirmationBridge()
        options = _telnyx_input_gate_options(
            "outbound",
            campaign_confirmation_mode=True,
        )
        gate = RealtimeInputGate(
            bridge,
            "soft-phone-confirmation",
            speech_threshold=options["speech_threshold"],
            speech_start_frames=options["speech_start_frames"],
            adaptive_threshold=options["adaptive_threshold"],
            campaign_confirmation_mode=True,
        )

        await gate.push(b"\x01\x00" * 160, 180)
        await gate.push(b"\x01\x00" * 160, 180)
        return bridge

    bridge = asyncio.run(run())

    assert bridge.muted == [True]
    assert bridge.started == 1
    assert len(bridge.frames) == 2
