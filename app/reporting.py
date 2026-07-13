import csv
import io
from datetime import datetime, timedelta

from sqlalchemy import select

from app.database import CallIntentRow, CallRecordingRow, db_session


def sales_report(days: int = 30) -> dict:
    since = datetime.utcnow() - timedelta(days=max(0, days))
    with db_session() as session:
        rows = session.scalars(
            select(CallRecordingRow).where(CallRecordingRow.started_at >= since)
        ).all()
        intents = {
            intent.recording_id: intent
            for intent in session.scalars(select(CallIntentRow)).all()
        }

    total = len(rows)
    inbound = sum(1 for row in rows if row.direction == "inbound")
    outbound = sum(1 for row in rows if row.direction.startswith("outbound"))
    completed = sum(1 for row in rows if row.status == "completed")
    active = sum(1 for row in rows if row.status == "active")
    failed = sum(1 for row in rows if row.status == "failed")
    order_intent = sum(1 for row in rows if _intent_for(row, intents) and _intent_for(row, intents).order_intent)
    order_complete = sum(1 for row in rows if row.sales_status == "order_complete")
    no_order = sum(1 for row in rows if row.sales_status == "no_order")
    total_minutes = round(sum(_duration_seconds(row) for row in rows) / 60, 1)

    return {
        "days": days,
        "total_calls": total,
        "inbound_calls": inbound,
        "outbound_calls": outbound,
        "completed_calls": completed,
        "active_calls": active,
        "failed_calls": failed,
        "order_intent_calls": order_intent,
        "order_complete_calls": order_complete,
        "no_order_calls": no_order,
        "conversion_rate": round(order_complete / total * 100, 1) if total else 0.0,
        "order_intent_rate": round(order_intent / total * 100, 1) if total else 0.0,
        "total_minutes": total_minutes,
        "by_direction": _count_by(rows, "direction"),
        "by_sales_status": _count_by(rows, "sales_status"),
        "by_call_status": _count_by(rows, "status"),
    }


def export_sales_csv(days: int = 30) -> str:
    since = datetime.utcnow() - timedelta(days=max(0, days))
    with db_session() as session:
        rows = session.scalars(
            select(CallRecordingRow).where(CallRecordingRow.started_at >= since).order_by(CallRecordingRow.started_at.desc())
        ).all()
        intents = {
            intent.recording_id: intent
            for intent in session.scalars(select(CallIntentRow)).all()
        }

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "recording_id",
            "direction",
            "call_status",
            "sales_status",
            "from_number",
            "to_number",
            "started_at",
            "ended_at",
            "duration_seconds",
            "customer_name",
            "intent_phone",
            "address",
            "order_intent",
            "product_name",
            "quantity",
            "combo",
            "confidence",
        ]
    )
    for row in rows:
        intent = intents.get(row.id)
        writer.writerow(
            [
                row.id,
                row.direction,
                row.status,
                row.sales_status,
                row.from_number,
                row.to_number,
                row.started_at.isoformat(timespec="seconds") if row.started_at else "",
                row.ended_at.isoformat(timespec="seconds") if row.ended_at else "",
                _duration_seconds(row),
                intent.customer_name if intent else "",
                intent.phone_number if intent else "",
                intent.address if intent else "",
                intent.order_intent if intent else False,
                intent.product_name if intent else "",
                intent.quantity if intent else "",
                intent.combo if intent else "",
                intent.confidence if intent else 0.0,
            ]
        )
    return output.getvalue()


def _duration_seconds(row: CallRecordingRow) -> int:
    if not row.started_at or not row.ended_at:
        return 0
    return max(0, int((row.ended_at - row.started_at).total_seconds()))


def _intent_for(row: CallRecordingRow, intents: dict[str, CallIntentRow]) -> CallIntentRow | None:
    return intents.get(row.id)


def _count_by(rows: list[CallRecordingRow], attr: str) -> dict:
    counts: dict[str, int] = {}
    for row in rows:
        key = getattr(row, attr) or "unknown"
        counts[key] = counts.get(key, 0) + 1
    return counts
