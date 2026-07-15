from datetime import datetime
from types import SimpleNamespace

from app.recording_manager import _recording_item


def test_recording_item_links_files_by_recording_id_and_file_kind(tmp_path) -> None:
    call_dir = tmp_path / "84961695448_20260714-094436"
    call_dir.mkdir()
    inbound_path = call_dir / "inbound.wav"
    outbound_path = call_dir / "outbound.wav"
    mixed_path = call_dir / "mixed.wav"
    log_path = call_dir / "call.log"
    for path in (inbound_path, outbound_path, mixed_path, log_path):
        path.write_bytes(b"data")

    row = SimpleNamespace(
        id="84961695448_20260714-094436",
        call_id="call-1",
        stream_id="stream-1",
        from_number="84961695448",
        to_number=None,
        direction="inbound",
        started_at=datetime(2026, 7, 14, 9, 44, 36),
        ended_at=None,
        status="completed",
        sales_status="open",
        codec="PCMU",
        sample_rate=8000,
        inbound_path=str(inbound_path),
        outbound_path=str(outbound_path),
        mixed_path=str(mixed_path),
        log_path=str(log_path),
        inbound_bytes=4,
        outbound_bytes=4,
        mixed_bytes=4,
        log_bytes=4,
    )

    item = _recording_item(row)

    assert item["files"]["inbound"]["url"] == "/admin/file/84961695448_20260714-094436/inbound"
    assert item["files"]["outbound"]["url"] == "/admin/file/84961695448_20260714-094436/outbound"
    assert item["files"]["mixed"]["url"] == "/admin/file/84961695448_20260714-094436/mixed"
    assert item["files"]["log"]["url"] == "/admin/file/84961695448_20260714-094436/log"
