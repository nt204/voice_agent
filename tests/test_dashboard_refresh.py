from pathlib import Path


def test_dashboard_refreshes_automatically_without_losing_selected_detail():
    source = Path("app/static/dashboard.js").read_text(encoding="utf-8")

    assert "setInterval" in source
    assert "document.hidden" in source
    assert 'addEventListener("visibilitychange"' in source
    assert 'addEventListener("focus"' in source
    assert "state.selectedId" in source
    assert "silent: true" in source
    assert "shouldRefreshSelectedDetail" in source
    assert "isActiveCall(selectedCall)" in source
    assert "state.selectedDetailStatus === \"active\"" in source
    assert "isDetailAudioPlaying()" in source
    assert "isTranscriptScrolledAwayFromBottom()" in source


def test_dashboard_renders_call_recording_player():
    source = Path("app/static/dashboard.js").read_text(encoding="utf-8")
    styles = Path("app/static/dashboard.css").read_text(encoding="utf-8")
    html = Path("app/static/index.html").read_text(encoding="utf-8")
    main = Path("app/main.py").read_text(encoding="utf-8")

    assert "renderRecordingCard(call)" in source
    assert "Bản ghi cuộc gọi" in source
    assert "recording?.files" in source
    assert "/recording/" in main
    assert "<audio controls" in source
    assert ".recording-card" in styles
    assert "layout-fix-v22" in html
    assert "Số đã gọi" in source
    assert "Số khách cung cấp" in source
