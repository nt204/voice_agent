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
    assert "Bỏ qua dòng Sheet đã đánh dấu gọi" in html
    assert "Sẵn sàng · Đã từng gọi" in source
    assert "campaign_run_id: state.sheetCampaignRunId" in source
    assert "lead.offer || lead.product || data.product?.name" in source
    assert 'id="cancelSheetCampaignButton"' in html
    assert "Hủy chiến dịch đang chạy" in html
    assert "/api/sheets/campaigns/${encodeURIComponent(runId)}/cancel" in source
    assert "Telnyx đã khóa tài khoản gọi đi (D17)" in source
    assert "Đã gọi trong chiến dịch" in source
    assert 'id="allowRetryAllButton"' in html
    assert "Cho phép gọi lại tất cả" in html
    assert "/api/sheets/campaigns/allow-retry" in source
    assert 'data-retry-phone="${escapeHtml(lead.phone || "")}"' in source
    assert 'id="sheetCallTimeoutSelect"' in html
    assert "Nghỉ sau mỗi cuộc" in html
    assert "Tối đa mỗi cuộc" in html
    assert '<option value="600">10 phút</option>' in html
    assert "call_timeout_seconds: callTimeoutSeconds" in source

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
