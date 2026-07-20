from datetime import datetime, timedelta
from types import SimpleNamespace

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app import database
from app.database import Base, CallRecordingRow, CallTranscriptRow
from app.recording_manager import (
    RecordingInUseError,
    _recording_item,
    cleanup_recordings,
    delete_recording,
    list_recordings,
    storage_summary,
)


def test_recording_item_links_files_by_recording_id_and_file_kind(tmp_path) -> None:
    call_dir = tmp_path / "95961695448_20260714-094436"
    call_dir.mkdir()
    inbound_path = call_dir / "inbound.wav"
    outbound_path = call_dir / "outbound.wav"
    mixed_path = call_dir / "mixed.wav"
    log_path = call_dir / "call.log"
    for path in (inbound_path, outbound_path, mixed_path, log_path):
        path.write_bytes(b"data")

    row = SimpleNamespace(
        id="95961695448_20260714-094436",
        call_id="call-1",
        stream_id="stream-1",
        from_number="95961695448",
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

    assert item["files"]["inbound"]["url"] == "/admin/file/95961695448_20260714-094436/inbound"
    assert item["files"]["outbound"]["url"] == "/admin/file/95961695448_20260714-094436/outbound"
    assert item["files"]["mixed"]["url"] == "/admin/file/95961695448_20260714-094436/mixed"
    assert item["files"]["log"]["url"] == "/admin/file/95961695448_20260714-094436/log"


def _use_test_recording_database(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'recordings-test.db'}")
    Base.metadata.create_all(engine)
    monkeypatch.setattr(database, "SessionLocal", sessionmaker(bind=engine, expire_on_commit=False))
    (tmp_path / "recordings").mkdir()
    monkeypatch.setattr(
        "app.recording_manager.recordings_root", lambda: tmp_path / "recordings"
    )
    return sessionmaker(bind=engine, expire_on_commit=False)


def _add_recording(session_factory, root, recording_id, *, status="completed", days_old=40):
    call_dir = root / recording_id
    call_dir.mkdir()
    files = {
        "inbound": call_dir / "inbound.wav",
        "outbound": call_dir / "outbound.wav",
        "mixed": call_dir / "mixed.wav",
        "log": call_dir / "call.log",
    }
    for path in files.values():
        path.write_bytes(b"audio-data")
    started_at = datetime.utcnow() - timedelta(days=days_old)
    with session_factory() as session:
        session.add(
            CallRecordingRow(
                id=recording_id,
                call_id=f"call-{recording_id}",
                direction="outbound",
                started_at=started_at,
                ended_at=started_at + timedelta(minutes=2),
                status=status,
                inbound_path=str(files["inbound"]),
                outbound_path=str(files["outbound"]),
                mixed_path=str(files["mixed"]),
                log_path=str(files["log"]),
                inbound_bytes=10,
                outbound_bytes=10,
                mixed_bytes=10,
                log_bytes=10,
            )
        )
        session.commit()
    return files


def test_delete_recording_removes_files_but_preserves_call_transcript(tmp_path, monkeypatch):
    session_factory = _use_test_recording_database(tmp_path, monkeypatch)
    root = tmp_path / "recordings"
    files = _add_recording(session_factory, root, "old-call")
    with session_factory() as session:
        session.add(
            CallTranscriptRow(
                recording_id="old-call",
                call_id="call-old-call",
                speaker="customer",
                text="Keep this transcript",
            )
        )
        session.commit()

    result = delete_recording("old-call")

    assert result == {"deleted_recordings": 1, "deleted_files": 4, "freed_bytes": 40}
    assert all(not path.exists() for path in files.values())
    with session_factory() as session:
        row = session.get(CallRecordingRow, "old-call")
        transcript = session.scalar(select(CallTranscriptRow))
        assert row is not None
        assert row.status == "deleted"
        assert transcript.text == "Keep this transcript"
    assert list_recordings() == []
    assert storage_summary() == {"count": 0, "total_bytes": 0, "total_mb": 0.0}


def test_delete_recording_rejects_an_active_call(tmp_path, monkeypatch):
    session_factory = _use_test_recording_database(tmp_path, monkeypatch)
    files = _add_recording(
        session_factory, tmp_path / "recordings", "active-call", status="active"
    )

    try:
        delete_recording("active-call")
    except RecordingInUseError:
        pass
    else:
        raise AssertionError("Active recordings must not be deleted")

    assert all(path.exists() for path in files.values())


def test_delete_recording_never_deletes_a_path_outside_recording_root(tmp_path, monkeypatch):
    session_factory = _use_test_recording_database(tmp_path, monkeypatch)
    files = _add_recording(session_factory, tmp_path / "recordings", "unsafe-path")
    external_file = tmp_path / "must-stay.log"
    external_file.write_bytes(b"do-not-delete")
    with session_factory() as session:
        row = session.get(CallRecordingRow, "unsafe-path")
        row.log_path = str(external_file)
        row.log_bytes = external_file.stat().st_size
        session.commit()

    result = delete_recording("unsafe-path")

    assert result["deleted_files"] == 3
    assert external_file.exists()
    assert not files["inbound"].exists()


def test_cleanup_only_deletes_completed_recordings_older_than_retention(tmp_path, monkeypatch):
    session_factory = _use_test_recording_database(tmp_path, monkeypatch)
    root = tmp_path / "recordings"
    old_files = _add_recording(session_factory, root, "old-completed", days_old=40)
    recent_files = _add_recording(session_factory, root, "recent-completed", days_old=5)
    active_files = _add_recording(
        session_factory, root, "old-active", status="active", days_old=40
    )

    result = cleanup_recordings(30)

    assert result == {"deleted_recordings": 1, "deleted_files": 4, "freed_bytes": 40}
    assert all(not path.exists() for path in old_files.values())
    assert all(path.exists() for path in recent_files.values())
    assert all(path.exists() for path in active_files.values())
