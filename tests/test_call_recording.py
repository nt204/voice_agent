import struct

from app.config import config
from app.call_recording import CallRecorder, _mix_pcm_chunks


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


def test_call_recorder_groups_all_files_in_a_call_directory(tmp_path, monkeypatch) -> None:
    original_recordings_dir = config.call_recordings_dir
    object.__setattr__(config, "call_recordings_dir", str(tmp_path))
    monkeypatch.setattr("app.call_recording._timestamp", lambda: "20260714-094436")
    monkeypatch.setattr(CallRecorder, "_insert_db_row", lambda self: None)
    monkeypatch.setattr(CallRecorder, "_finish_db_row", lambda self: None)

    try:
        recorder = CallRecorder(
            call_id="call-1",
            sample_rate=8000,
            phone_number="+95 961 695 448",
        )
        recorder.write_inbound(_pcm16(100))
        recorder.write_outbound(_pcm16(200))
        recorder.close()

        call_dir = tmp_path / "95_961_695_448_20260714-094436"
        assert recorder.inbound_path == call_dir / "inbound.wav"
        assert recorder.outbound_path == call_dir / "outbound.wav"
        assert recorder.mixed_path == call_dir / "mixed.wav"
        assert recorder.log_path == call_dir / "call.log"
        assert recorder.inbound_path.exists()
        assert recorder.outbound_path.exists()
        assert recorder.mixed_path.exists()
    finally:
        object.__setattr__(config, "call_recordings_dir", original_recordings_dir)
