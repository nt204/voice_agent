from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import desc, func, select

from app.call_recording import _recording_root
from app.database import CallIntentRow, CallRecordingRow, db_session


RECORDING_DIRECTIONS = {"inbound", "outbound", "mixed", "logs"}


def recordings_root() -> Path:
    return _recording_root()


def list_recordings() -> list[dict]:
    with db_session() as session:
        rows = session.scalars(
            select(CallRecordingRow).order_by(desc(CallRecordingRow.started_at))
        ).all()
        intents = {
            intent.recording_id: intent
            for intent in session.scalars(select(CallIntentRow)).all()
        }
        return [_recording_item(row, intents.get(row.id)) for row in rows]


def recording_path(direction: str, filename: str) -> Path:
    if direction not in RECORDING_DIRECTIONS:
        raise ValueError("Invalid recording direction")
    path = recordings_root() / direction / Path(filename).name
    root = recordings_root().resolve()
    resolved = path.resolve()
    if not resolved.is_relative_to(root):
        raise ValueError("Invalid recording path")
    return resolved


def delete_recording(recording_id: str) -> int:
    deleted_files = 0
    row_found = False
    with db_session() as session:
        row = session.get(CallRecordingRow, Path(recording_id).name)
        if row:
            row_found = True
            for raw_path in (row.inbound_path, row.outbound_path, row.mixed_path, row.log_path):
                path = Path(raw_path)
                if path.exists():
                    path.unlink()
                    deleted_files += 1
            session.delete(row)
    return deleted_files if deleted_files else int(row_found)


def cleanup_recordings(days: int) -> dict[str, int]:
    cutoff = datetime.utcnow() - timedelta(days=max(0, days))
    deleted_recordings = 0
    deleted_files = 0
    with db_session() as session:
        rows = session.scalars(
            select(CallRecordingRow).where(CallRecordingRow.started_at < cutoff)
        ).all()
        for row in rows:
            for raw_path in (row.inbound_path, row.outbound_path, row.mixed_path, row.log_path):
                path = Path(raw_path)
                if path.exists():
                    path.unlink()
                    deleted_files += 1
            session.delete(row)
            deleted_recordings += 1
    return {"deleted_recordings": deleted_recordings, "deleted_files": deleted_files}


def storage_summary() -> dict:
    with db_session() as session:
        count = session.scalar(select(func.count()).select_from(CallRecordingRow)) or 0
        inbound = session.scalar(select(func.coalesce(func.sum(CallRecordingRow.inbound_bytes), 0))) or 0
        outbound = session.scalar(select(func.coalesce(func.sum(CallRecordingRow.outbound_bytes), 0))) or 0
        mixed = session.scalar(select(func.coalesce(func.sum(CallRecordingRow.mixed_bytes), 0))) or 0
        logs = session.scalar(select(func.coalesce(func.sum(CallRecordingRow.log_bytes), 0))) or 0
    total_bytes = int(inbound + outbound + mixed + logs)
    return {
        "count": int(count),
        "total_bytes": total_bytes,
        "total_mb": round(total_bytes / 1024 / 1024, 2),
    }


def _recording_item(row: CallRecordingRow, intent: CallIntentRow | None = None) -> dict:
    total_bytes = int(row.inbound_bytes + row.outbound_bytes + row.mixed_bytes + row.log_bytes)
    latest = row.ended_at or row.started_at
    return {
        "id": row.id,
        "call_id": row.call_id,
        "stream_id": row.stream_id,
        "phone": row.from_number or row.id,
        "to": row.to_number,
        "direction": row.direction,
        "timestamp": row.started_at.strftime("%Y%m%d-%H%M%S") if row.started_at else "",
        "started_at": row.started_at.isoformat(timespec="seconds") if row.started_at else "",
        "ended_at": row.ended_at.isoformat(timespec="seconds") if row.ended_at else "",
        "latest_mtime": latest.timestamp() if latest else 0.0,
        "latest_time": latest.isoformat(timespec="seconds") if latest else "",
        "status": row.status,
        "sales_status": row.sales_status,
        "codec": row.codec,
        "sample_rate": row.sample_rate,
        "intent": _intent_info(intent),
        "files": {
            "inbound": _file_info(Path(row.inbound_path), "inbound"),
            "outbound": _file_info(Path(row.outbound_path), "outbound"),
            "mixed": _file_info(Path(row.mixed_path), "mixed") if row.mixed_path else None,
            "log": _file_info(Path(row.log_path), "logs"),
        },
        "sizes": {
            "inbound": row.inbound_bytes,
            "outbound": row.outbound_bytes,
            "mixed": row.mixed_bytes,
            "log": row.log_bytes,
        },
        "total_bytes": total_bytes,
    }


def _file_info(path: Path, direction: str) -> dict | None:
    if not path.exists():
        return None
    return {
        "name": path.name,
        "bytes": path.stat().st_size,
        "url": f"/admin/file/{direction}/{path.name}",
    }


def _intent_info(intent: CallIntentRow | None) -> dict:
    if not intent:
        return {
            "customer_name": None,
            "phone_number": None,
            "address": None,
            "order_intent": False,
            "product_name": None,
            "quantity": None,
            "combo": None,
            "confidence": 0.0,
            "missing_fields": [],
            "updated_at": "",
        }
    return {
        "customer_name": intent.customer_name,
        "phone_number": intent.phone_number,
        "address": intent.address,
        "order_intent": intent.order_intent,
        "product_name": intent.product_name,
        "quantity": intent.quantity,
        "combo": intent.combo,
        "confidence": intent.confidence,
        "missing_fields": _json_list(intent.missing_fields),
        "updated_at": intent.updated_at.isoformat(timespec="seconds") if intent.updated_at else "",
    }


def _json_list(value: str) -> list:
    import json

    try:
        parsed = json.loads(value or "[]")
    except json.JSONDecodeError:
        return []
    return parsed if isinstance(parsed, list) else []
