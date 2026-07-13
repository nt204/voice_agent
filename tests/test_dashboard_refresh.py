from pathlib import Path


def test_dashboard_refreshes_automatically_without_losing_selected_detail():
    source = Path("app/static/dashboard.js").read_text(encoding="utf-8")

    assert "setInterval" in source
    assert "document.hidden" in source
    assert 'addEventListener("visibilitychange"' in source
    assert 'addEventListener("focus"' in source
    assert "state.selectedId" in source
    assert "silent: true" in source
