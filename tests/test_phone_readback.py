from app.audio import frame_bytes_for_pcm16
from app.phone_readback import phone_readback_frames, phone_readback_pcm


def test_builds_deterministic_readback_for_varied_phone_lengths() -> None:
    for phone in ("0961695448", "09780771433", "09993905153"):
        pcm = phone_readback_pcm(phone, 16000)
        frames = phone_readback_frames(phone, 8000)

        assert pcm
        assert frames
        assert all(len(frame) == frame_bytes_for_pcm16(8000) for frame in frames)


def test_empty_phone_has_no_readback_audio() -> None:
    assert phone_readback_pcm("", 16000) == b""
    assert phone_readback_frames("", 8000) == []
