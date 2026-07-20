from pathlib import Path


def test_dashboard_is_fully_localized_for_vietnamese_staff():
    html = Path("app/static/index.html").read_text(encoding="utf-8")
    source = Path("app/static/dashboard.js").read_text(encoding="utf-8")
    products_html = Path("app/static/products.html").read_text(encoding="utf-8")
    products_source = Path("app/static/products.js").read_text(encoding="utf-8")

    assert '<html lang="vi">' in html
    assert "Quản lý bán hàng" in html
    assert "Quản lý sản phẩm" in products_html
    assert "Tổng quan khách hàng" in html
    assert "Gọi nhanh cho khách" in html
    assert "Đơn hàng đã tạo" in html
    assert "Chọn một khách hàng để xem chi tiết" in html
    assert 'const LOCALE = "vi-VN"' in source
    assert "Bản ghi cuộc gọi" in source
    assert "Sản phẩm mặc định" in products_source
    assert "Đã lưu sản phẩm" in products_source

    forbidden_labels = (
        "Voice AI Sales",
        "Product view",
        "Manage products",
        "Sales funnel",
        "Quick customer call",
        "Created orders",
        "Select a lead",
        "Call recording",
    )
    combined = html + source + products_html + products_source
    for label in forbidden_labels:
        assert label not in combined


def test_dashboard_keeps_order_and_product_integration_hooks():
    html = Path("app/static/index.html").read_text(encoding="utf-8")
    source = Path("app/static/dashboard.js").read_text(encoding="utf-8")

    for element_id in (
        "productFilter",
        "outboundProduct",
        "outboundCallForm",
        "orderList",
        "callList",
        "detailPanel",
    ):
        assert f'id="{element_id}"' in html

    assert 'postJson("/telnyx/outbound/call"' in source
    assert 'product_id: Number(productId)' in source
    assert 'fetchJson("/api/products")' in source


def test_quick_call_can_be_ended_after_it_starts():
    html = Path("app/static/index.html").read_text(encoding="utf-8")
    source = Path("app/static/dashboard.js").read_text(encoding="utf-8")

    assert 'id="endCallButton"' in html
    assert "Ngắt cuộc gọi" in html
    assert 'postJson(`/telnyx/outbound/call/${encodeURIComponent(state.activeCallSid)}/hangup`)' in source
    assert "state.activeCallSid = result.call_sid" in source


def test_customer_detail_does_not_render_need_card():
    source = Path("app/static/dashboard.js").read_text(encoding="utf-8")

    assert '<div class="detail-note"><span>Nhu cầu</span>' not in source


def test_customer_detail_uses_comfortable_reading_scale():
    styles = Path("app/static/dashboard.css").read_text(encoding="utf-8")

    assert "--detail-message-size: 16px;" in styles
    assert "--detail-summary-width: 360px;" in styles
    assert "min-width: 220px;" in styles


def test_call_recording_controls_are_large_and_full_width():
    styles = Path("app/static/dashboard.css").read_text(encoding="utf-8")

    assert "--recording-control-height: 52px;" in styles
    assert "height: var(--recording-control-height);" in styles
    assert "min-height: 72px;" in styles


def test_quick_call_fields_do_not_overlap():
    source = Path("app/static/dashboard.js").read_text(encoding="utf-8")
    styles = Path("app/static/dashboard.css").read_text(encoding="utf-8")

    assert '${escapeHtml(product.name)}</option>' in source
    assert 'product.phone_number || "Chưa có số"' not in source
    assert ".call-form label { min-width: 0;" in styles
    assert ".call-form select { width: 100%;" in styles
