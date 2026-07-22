from pathlib import Path

from fastapi.testclient import TestClient


def test_orders_page_groups_and_exports_orders_by_product() -> None:
    html = Path("app/static/orders.html").read_text(encoding="utf-8")
    source = Path("app/static/orders.js").read_text(encoding="utf-8")

    assert 'id="orderProductTabs"' in html
    assert "Quản lý theo sản phẩm" in html
    assert 'fetch("/api/products")' in source
    assert "ordersForActiveProduct" in source
    assert 'params.set("product_id", activeProductFilter)' in source
    assert 'params.set("unassigned", "true")' in source
    assert "o.product?.name" in source


def test_orders_api_can_filter_unassigned_orders(monkeypatch) -> None:
    from app import main as main_module

    class Store:
        def list_orders(self, limit=100, product_id=None):
            orders = [
                {"id": 1, "product_id": 7, "status": "confirmed"},
                {"id": 2, "product_id": None, "status": "draft"},
            ]
            if product_id is not None:
                return [order for order in orders if order["product_id"] == product_id]
            return orders

    monkeypatch.setattr(main_module, "call_history", Store())
    client = TestClient(main_module.app)

    response = client.get("/api/orders?unassigned=true")
    product_response = client.get("/api/orders?product_id=7")

    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert [order["id"] for order in response.json()["orders"]] == [2]
    assert [order["id"] for order in product_response.json()["orders"]] == [1]
