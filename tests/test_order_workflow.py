from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.call_history import CallHistoryStore, calls_table, orders_table
from app.order_workflow import order_statistics, validate_order_update


def _complete_order(**overrides):
    order = {
        "status": "ready_to_confirm",
        "customer_phone": "09789119333",
        "shipping_address": "No. 12 Pyay Road, Yangon",
        "product_name": "Venus BigOne Combo 2",
        "quantity": 2,
        "unit_price": 105000,
        "total_price": 210000,
        "missing_fields": [],
    }
    order.update(overrides)
    return order


def test_order_update_rejects_skipped_transition_and_incomplete_confirmation() -> None:
    with pytest.raises(ValueError, match="Cannot move order"):
        validate_order_update(_complete_order(), {"status": "shipping"})

    incomplete = _complete_order(
        status="missing_info",
        customer_phone="",
        missing_fields=["customer_phone"],
    )
    with pytest.raises(ValueError, match="customer_phone"):
        validate_order_update(incomplete, {"status": "ready_to_confirm"})


def test_order_update_accepts_valid_confirmation_and_normalizes_missing_fields() -> None:
    update = validate_order_update(
        _complete_order(status="missing_info", missing_fields=["customer_phone"]),
        {
            "customer_phone": "09789119333",
            "missing_fields": [],
            "status": "ready_to_confirm",
        },
    )

    assert update["status"] == "ready_to_confirm"
    assert update["missing_fields"] == ""


def test_order_statistics_separates_review_confirmation_and_packing() -> None:
    stats = order_statistics(
        [
            _complete_order(status="draft"),
            _complete_order(status="missing_info"),
            _complete_order(status="ready_to_confirm"),
            _complete_order(status="confirmed", quantity=3, total_price=300000),
            _complete_order(status="shipping", total_price=200000),
            _complete_order(status="completed", total_price=500000),
            _complete_order(status="cancelled", total_price=999999),
        ]
    )

    assert stats["needs_review"] == 2
    assert stats["awaiting_confirmation"] == 1
    assert stats["waiting_to_pack"] == 1
    assert "units_to_pack" not in stats
    assert "cod_pending" not in stats
    assert "overdue_confirmed" not in stats


def test_store_filters_before_pagination_and_validates_updates(tmp_path) -> None:
    store = CallHistoryStore(tmp_path / "orders.db")
    now = datetime.now(timezone.utc).isoformat()
    with store.engine.begin() as connection:
        for index, status in enumerate(("confirmed", "cancelled", "confirmed"), start=1):
            call_id = f"order-page-{index}"
            connection.execute(
                calls_table.insert().values(
                    id=call_id,
                    direction="outbound",
                    provider="telnyx",
                    status="completed",
                    started_at=now,
                )
            )
            connection.execute(
                orders_table.insert().values(
                    call_id=call_id,
                    customer_phone=f"0978911933{index}",
                    shipping_address="Yangon address",
                    product_name="Venus BigOne",
                    quantity=1,
                    unit_price=120000,
                    total_price=120000,
                    status=status,
                    created_at=f"2026-07-2{index}T01:00:00+00:00",
                    updated_at=now,
                )
            )

    first = store.list_orders(limit=1, status="confirmed")
    second = store.list_orders(limit=1, status="confirmed", offset=1)

    assert store.count_orders(status="confirmed") == 2
    assert len(first) == len(second) == 1
    assert first[0]["id"] != second[0]["id"]

    with pytest.raises(ValueError, match="Cannot move order"):
        store.update_order(first[0]["id"], {"status": "shipping"})

    packed = store.update_order(first[0]["id"], {"status": "packed"})
    assert packed["status"] == "packed"
