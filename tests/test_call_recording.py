import struct

from app.call_recording import _mix_pcm_chunks


def _pcm16(*samples: int) -> bytes:
    return struct.pack("<" + "h" * len(samples), *samples)


def _samples(pcm: bytes) -> tuple[int, ...]:
    return struct.unpack("<" + "h" * (len(pcm) // 2), pcm)


def test_mix_pcm_chunks_overlays_tracks_on_the_same_timeline() -> None:
    mixed = _mix_pcm_chunks(
        [
            (0, _pcm16(1000, 1000, 1000)),
            (1, _pcm16(2000, 2000)),
        ]
    )

    assert _samples(mixed) == (1000, 3000, 3000)


def test_mix_pcm_chunks_preserves_silence_gaps() -> None:
    mixed = _mix_pcm_chunks([(2, _pcm16(1200))])

    assert _samples(mixed) == (0, 0, 1200)
