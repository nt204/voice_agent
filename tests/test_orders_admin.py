from pathlib import Path

from fastapi.testclient import TestClient


def test_orders_page_groups_and_exports_orders_by_product() -> None:
    html = Path("app/static/orders.html").read_text(encoding="utf-8")
    source = Path("app/static/orders.js").read_text(encoding="utf-8")

    assert 'id="orderProductTabs"' in html
    assert "Quản lý theo sản phẩm" in html
    assert 'fetchJson("/api/products")' in source
    assert "productCounts" in source
    assert 'params.set("product_id", activeProductFilter)' in source
    assert 'params.set("unassigned", "true")' in source
    assert 'params.set("status", activeStatusFilter)' in source
    assert "order.product?.name" in source
    assert "setInterval" in source
    assert 'id="ordersPager"' in html
    assert 'id="statNeedsReview"' in html
    assert 'id="statUnitsToPack"' not in html
    assert 'id="statCodPending"' not in html
    assert 'id="statOverdue"' not in html
    assert 'id="exportOrdersExcel"' in html
    assert "Xuất Excel đóng gói" in html
    assert "/api/orders/export.xlsx" in source
    assert 'params.set("status", "confirmed")' not in source
    assert 'href="/api/orders/export.xlsx"' in html
    assert 'orders.js?v=excel-filter-v30' in html


def test_orders_api_can_filter_unassigned_orders(monkeypatch) -> None:
    from app import main as main_module

    class Store:
        orders = [
            {"id": 1, "product_id": 7, "status": "confirmed"},
            {"id": 2, "product_id": None, "status": "draft"},
        ]

        def _filtered(self, product_id=None, unassigned=False, **kwargs):
            orders = self.orders
            if unassigned:
                return [order for order in orders if order["product_id"] is None]
            if product_id is not None:
                return [order for order in orders if order["product_id"] == product_id]
            return orders

        def list_orders(self, limit=100, product_id=None, **kwargs):
            return self._filtered(product_id, **kwargs)

        def count_orders(self, product_id=None, **kwargs):
            return len(self._filtered(product_id, **kwargs))

        def order_statistics(self, product_id=None, **kwargs):
            return {"total_orders": len(self._filtered(product_id, **kwargs))}

        def order_product_counts(self):
            return {"7": 1, "unassigned": 1}

    monkeypatch.setattr(main_module, "call_history", Store())
    client = TestClient(main_module.app)

    response = client.get("/api/orders?unassigned=true")
    product_response = client.get("/api/orders?product_id=7")

    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert [order["id"] for order in response.json()["orders"]] == [2]
    assert [order["id"] for order in product_response.json()["orders"]] == [1]


def test_orders_export_forwards_all_active_filters_without_row_limit(monkeypatch) -> None:
    from app import main as main_module

    calls = []

    class Store:
        def list_orders(self, **kwargs):
            calls.append(kwargs)
            return []

    monkeypatch.setattr(main_module, "call_history", Store())
    client = TestClient(main_module.app)

    response = client.get(
        "/api/orders/export?status=confirmed&product_id=7&q=Yangon"
    )

    assert response.status_code == 200
    assert calls == [
        {
            "limit": None,
            "product_id": 7,
            "status": "confirmed",
            "query": "Yangon",
            "unassigned": False,
        }
    ]
    assert response.content.startswith(b"\xef\xbb\xbf")


def test_orders_excel_export_returns_real_workbook(monkeypatch) -> None:
    from app import main as main_module

    calls = []

    class Store:
        def list_orders(self, **kwargs):
            calls.append(kwargs)
            return [
                {
                    "id": 1,
                    "created_at": "2026-07-22T07:00:00+00:00",
                    "customer_name": "Daw Mya",
                    "customer_phone": "09789119333",
                    "product_name": "Venus BigOne",
                    "quantity": 1,
                    "unit_price": 120000,
                    "total_price": 120000,
                    "shipping_address": "Yangon",
                    "status": "confirmed",
                    "missing_fields": [],
                }
            ]

    monkeypatch.setattr(main_module, "call_history", Store())
    client = TestClient(main_module.app)

    response = client.get(
        "/api/orders/export.xlsx?status=confirmed&product_id=7&q=Yangon"
    )

    assert response.status_code == 200
    assert response.content.startswith(b"PK")
    assert response.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    assert "phieu-dong-goi-" in response.headers["content-disposition"]
    assert calls == [
        {
            "limit": None,
            "product_id": 7,
            "status": "confirmed",
            "query": "Yangon",
            "unassigned": False,
        }
    ]
