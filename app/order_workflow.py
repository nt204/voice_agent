from __future__ import annotations

from typing import Any, Iterable, Mapping


ORDER_STATUSES = (
    "missing_info",
    "ready_to_confirm",
    "confirmed",
    "packed",
    "shipping",
    "completed",
    "cancelled",
)
LEGACY_ORDER_STATUSES = ("draft",)
ALL_ORDER_STATUSES = (*ORDER_STATUSES, *LEGACY_ORDER_STATUSES)

ORDER_STATUS_TRANSITIONS: dict[str, set[str]] = {
    "draft": {"draft", "missing_info", "ready_to_confirm", "confirmed", "cancelled"},
    "missing_info": {"missing_info", "ready_to_confirm", "cancelled"},
    "ready_to_confirm": {"missing_info", "ready_to_confirm", "confirmed", "cancelled"},
    "confirmed": {"ready_to_confirm", "confirmed", "packed", "cancelled"},
    "packed": {"confirmed", "packed", "shipping", "cancelled"},
    "shipping": {"packed", "shipping", "completed", "cancelled"},
    "completed": {"shipping", "completed"},
    "cancelled": {"missing_info", "ready_to_confirm", "cancelled"},
}

REQUIRED_ORDER_FIELDS = (
    "customer_phone",
    "shipping_address",
    "product_name",
    "quantity",
    "total_price",
)
COMPLETE_ORDER_STATUSES = {
    "ready_to_confirm",
    "confirmed",
    "packed",
    "shipping",
    "completed",
}


def parse_missing_fields(value: Any) -> list[str]:
    if isinstance(value, str):
        fields = value.split(",")
    elif isinstance(value, Iterable) and not isinstance(value, (bytes, bytearray, Mapping)):
        fields = value
    else:
        fields = []
    return list(
        dict.fromkeys(
            str(field).strip()
            for field in fields
            if str(field).strip()
        )
    )


def canonical_missing_fields(order: Mapping[str, Any]) -> list[str]:
    missing = parse_missing_fields(order.get("missing_fields"))
    for field in REQUIRED_ORDER_FIELDS:
        value = order.get(field)
        empty = not str(value or "").strip()
        if field in {"quantity", "total_price"}:
            try:
                empty = int(value or 0) <= 0
            except (TypeError, ValueError):
                empty = True
        if empty and field not in missing:
            missing.append(field)
        if not empty and field in missing:
            missing.remove(field)
    return missing


def validate_order_update(
    current: Mapping[str, Any], payload: Mapping[str, Any]
) -> dict[str, Any]:
    allowed_fields = {
        "customer_name",
        "customer_phone",
        "shipping_address",
        "product_name",
        "quantity",
        "unit_price",
        "total_price",
        "status",
        "missing_fields",
    }
    unknown = sorted(set(payload) - allowed_fields)
    if unknown:
        raise ValueError(f"Unsupported order fields: {', '.join(unknown)}")

    update: dict[str, Any] = {}
    for field in (
        "customer_name",
        "customer_phone",
        "shipping_address",
        "product_name",
    ):
        if field in payload:
            update[field] = str(payload.get(field) or "").strip()

    for field in ("quantity", "unit_price", "total_price"):
        if field not in payload:
            continue
        value = payload.get(field)
        if isinstance(value, bool):
            raise ValueError(f"{field} must be a number")
        try:
            parsed = int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{field} must be a number") from exc
        minimum = 1 if field == "quantity" else 0
        if parsed < minimum:
            raise ValueError(f"{field} must be at least {minimum}")
        update[field] = parsed

    if "missing_fields" in payload:
        update["missing_fields"] = ",".join(parse_missing_fields(payload["missing_fields"]))

    old_status = str(current.get("status") or "draft").strip()
    new_status = str(payload.get("status", old_status) or "").strip()
    if new_status not in ALL_ORDER_STATUSES:
        raise ValueError(f"Unsupported order status: {new_status or '(empty)'}")
    allowed_transitions = ORDER_STATUS_TRANSITIONS.get(old_status, {old_status})
    if new_status not in allowed_transitions:
        raise ValueError(f"Cannot move order from {old_status} to {new_status}")
    if "status" in payload:
        update["status"] = new_status

    merged = dict(current)
    merged.update(update)
    missing = canonical_missing_fields(merged)
    if new_status in COMPLETE_ORDER_STATUSES and missing:
        raise ValueError(
            "Complete the required order fields before using this status: "
            + ", ".join(missing)
        )
    if new_status in COMPLETE_ORDER_STATUSES and int(merged.get("total_price") or 0) <= 0:
        raise ValueError("total_price must be greater than 0 for a complete order")
    return update


def order_statistics(orders: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    rows = list(orders)
    counts = {status: 0 for status in ALL_ORDER_STATUSES}
    unknown_count = 0

    for order in rows:
        status = str(order.get("status") or "draft")
        if status in counts:
            counts[status] += 1
        else:
            unknown_count += 1

    return {
        "total_orders": len(rows),
        "status_counts": counts,
        "unknown_status": unknown_count,
        "needs_review": counts["draft"] + counts["missing_info"],
        "awaiting_confirmation": counts["ready_to_confirm"],
        "waiting_to_pack": counts["confirmed"],
    }
