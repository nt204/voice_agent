from pathlib import Path

from fastapi.testclient import TestClient


def test_recordings_page_is_routed_and_linked_from_admin_navigation():
    from app import main as main_module

    client = TestClient(main_module.app)
    response = client.get("/admin/recordings")

    assert response.status_code == 200
    assert "Quản lý bản ghi âm" in response.text
    for page in ("app/static/index.html", "app/static/products.html"):
        html = Path(page).read_text(encoding="utf-8")
        assert 'href="/admin/recordings"' in html
        assert "Bản ghi âm" in html


def test_recordings_page_supports_search_playback_and_confirmed_deletion():
    html = Path("app/static/recordings.html").read_text(encoding="utf-8")
    source = Path("app/static/recordings.js").read_text(encoding="utf-8")

    for element_id in (
        "recordingSearch",
        "retentionDays",
        "cleanupRecordingsButton",
        "selectAllRecordings",
        "deleteSelectedRecordingsButton",
        "selectedRecordingCount",
        "recordingList",
        "recordingStatus",
    ):
        assert f'id="{element_id}"' in html
    assert "<audio controls" in source
    assert "window.confirm" in source
    assert 'requestJson(`/admin/api/recordings/${encodeURIComponent(recordingId)}' in source
    assert 'requestJson(`/admin/api/cleanup' in source
    assert 'requestJson("/admin/api/recordings/delete-batch"' in source
    assert 'timeZone: "Asia/Ho_Chi_Minh"' in source
    assert "recording-select-checkbox" in source


def test_bulk_recording_delete_api_validates_and_deletes_selection(monkeypatch):
    from app import admin as admin_module
    from app import main as main_module

    received = []

    def fake_delete_recordings(recording_ids):
        received.extend(recording_ids)
        return {
            "deleted_recordings": 2,
            "deleted_files": 6,
            "freed_bytes": 1234,
            "requested_recordings": 2,
            "skipped_active": 0,
            "missing_recordings": 0,
        }

    monkeypatch.setattr(admin_module, "delete_recordings", fake_delete_recordings)
    client = TestClient(main_module.app)

    empty_response = client.post(
        "/admin/api/recordings/delete-batch",
        json={"recording_ids": []},
    )
    response = client.post(
        "/admin/api/recordings/delete-batch",
        json={"recording_ids": ["recording-a", "recording-b"]},
    )

    assert empty_response.status_code == 400
    assert response.status_code == 200
    assert response.json()["deleted_recordings"] == 2
    assert received == ["recording-a", "recording-b"]


def test_cleanup_api_rejects_negative_retention_days():
    from app import main as main_module

    response = TestClient(main_module.app).post("/admin/api/cleanup?days=-1")

    assert response.status_code == 422
