from pathlib import Path


def test_admin_pages_have_shared_navigation_and_correct_active_state():
    dashboard = Path("app/static/index.html").read_text(encoding="utf-8")
    products = Path("app/static/products.html").read_text(encoding="utf-8")
    recordings = Path("app/static/recordings.html").read_text(encoding="utf-8")
    orders = Path("app/static/orders.html").read_text(encoding="utf-8")

    for html_content in (dashboard, products, recordings, orders):
        assert 'class="app-nav"' in html_content
        assert 'href="/admin"' in html_content
        assert 'href="/admin/products"' in html_content
        assert 'href="/admin/recordings"' in html_content
        assert 'href="/admin/orders"' in html_content

    assert 'href="/admin" aria-current="page"' in dashboard
    assert 'href="/admin/products" aria-current="page"' in products
    assert 'href="/admin/recordings" aria-current="page"' in recordings
    assert 'href="/admin/orders" aria-current="page"' in orders


def test_product_management_is_a_separate_page_not_a_dashboard_modal():
    main = Path("app/main.py").read_text(encoding="utf-8")
    dashboard = Path("app/static/index.html").read_text(encoding="utf-8")
    products = Path("app/static/products.html").read_text(encoding="utf-8")
    product_script = Path("app/static/products.js").read_text(encoding="utf-8")

    assert '@app.get("/admin/products")' in main
    assert '"products.html"' in main
    assert 'id="productManager"' not in dashboard
    assert 'id="productForm"' in products
    assert 'id="productList"' in products
    assert 'fetchJson("/api/products")' in product_script
    assert 'writeJson("/api/products", "POST"' in product_script


def test_admin_interface_uses_plain_functional_names_without_ai_branding():
    visible_sources = "\n".join(
        Path(path).read_text(encoding="utf-8")
        for path in (
            "app/static/index.html",
            "app/static/products.html",
            "app/static/dashboard.js",
            "app/static/products.js",
        )
    )

    for unwanted in (
        "Trung tâm",
        "DANH MỤC KINH DOANH",
        "Trung tâm bán hàng AI",
        "Kịch bản hội thoại AI",
        "Tư vấn viên AI",
        "Đơn hàng AI",
    ):
        assert unwanted not in visible_sources
