import re
import sqlite3
import threading
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


CUSTOMER_FIELDS = ("name", "phone", "address", "need", "notes")
INTEREST_STATUSES = ("needs_consultation", "no_need", "unknown")
OUTBOUND_REQUEST_STATUSES = (
    "queued",
    "started",
    "completed",
    "no_answer",
    "busy",
    "canceled",
    "failed",
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _clean(value: str) -> str:
    return value.strip(" \t\r\n,.;:-")


def classify_customer_interest(transcript: list[dict[str, Any]]) -> str:
    customer_text = " ".join(
        item.get("text", "").strip()
        for item in transcript
        if item.get("speaker") == "customer" and item.get("text", "").strip()
    )
    if not customer_text:
        return "unknown"

    ascii_text = customer_text.casefold()
    if any(
        phrase in ascii_text
        for phrase in (
            "chua co nhu cau",
            "khong can",
            "khong muon",
            "khong quan tam",
            "chua can",
            "chua muon",
            "chua quan tam",
        )
    ):
        return "no_need"
    if any(
        phrase in ascii_text
        for phrase in (
            "can tu van",
            "muon tu van",
            "tu van them",
            "muon mua",
            "can mua",
            "quan tam",
            "hoi them",
        )
    ):
        return "needs_consultation"

    no_need_patterns = (
        r"\bchưa (?:có )?nhu cầu\b",
        r"\bkhông (?:cần|muốn|quan tâm)\b",
        r"\bchưa (?:cần|muốn|quan tâm)\b",
        r"မလိုချင်",
        r"မလိုအပ်",
        r"မဝယ်ချင်",
    )
    if any(re.search(pattern, customer_text, flags=re.IGNORECASE) for pattern in no_need_patterns):
        return "no_need"

    consultation_patterns = (
        r"\b(?:cần|muốn) (?:được )?tư vấn\b",
        r"\btư vấn thêm\b",
        r"\b(?:muốn|cần) mua\b",
        r"\bquan tâm\b",
        r"\bhỏi thêm\b",
        r"ဝယ်ချင်",
        r"လိုချင်",
        r"အကြံဉာဏ်",
    )
    if any(
        re.search(pattern, customer_text, flags=re.IGNORECASE)
        for pattern in consultation_patterns
    ):
        return "needs_consultation"
    return "unknown"


def extract_customer_info(transcript: list[dict[str, Any]]) -> dict[str, str]:
    result = {field: "" for field in CUSTOMER_FIELDS}
    customer_text = " ".join(
        item.get("text", "").strip()
        for item in transcript
        if item.get("speaker") == "customer" and item.get("text", "").strip()
    )
    if not customer_text:
        return result

    patterns = {
        "name": (
            r"(?:tôi tên|tên tôi là|tên là|my name is)\s+"
            r"([^,.;]+?)(?=\s+(?:số điện thoại|điện thoại|phone|địa chỉ|address|tôi muốn)\b|[,.;]|$)"
        ),
        "phone": (
            r"(?:số điện thoại|điện thoại|phone)\s*(?:là|:)?\s*"
            r"(\+?\d[\d .-]{7,}\d)"
        ),
        "address": (
            r"(?:địa chỉ|address)\s*(?:là|:)?\s*"
            r"(.+?)(?=[.;]|\s+(?:tôi muốn|tôi cần|I want|I need)\b|$)"
        ),
        "need": (
            r"(?:tôi muốn|tôi cần|I want|I need)\s+"
            r"(.+?)(?=[.;]|\s+(?:địa chỉ|số điện thoại|phone)\b|$)"
        ),
    }
    for field, pattern in patterns.items():
        match = re.search(pattern, customer_text, flags=re.IGNORECASE)
        if match:
            result[field] = _clean(match.group(1))

    myanmar_patterns = {
        "name": (
            r"(?:ကျွန်တော့်နာမည်|ကျွန်မနာမည်|နာမည်)\s*(?:က|မှာ|သည်)?\s*"
            r"([^၊။,.;]+?)(?=\s*(?:ဖုန်း|လိပ်စာ)|[၊။,.;]|$)"
        ),
        "phone": r"(?:ဖုန်းနံပါတ်|ဖုန်း)\s*(?:က|မှာ|သည်|:)?\s*(\+?\d[\d .-]{7,}\d)",
        "address": (
            r"လိပ်စာ\s*(?:က|မှာ|သည်|:)?\s*"
            r"(.+?)(?=\s*(?:ဝယ်ချင်|လိုချင်)|[။;]|$)"
        ),
        "need": r"([^၊။,.;]+?(?:ဝယ်ချင်|လိုချင်)(?:ပါတယ်|တယ်)?)",
    }
    for field, pattern in myanmar_patterns.items():
        if result[field]:
            continue
        match = re.search(pattern, customer_text)
        if match:
            result[field] = _clean(match.group(1))
    return result


class CallHistoryStore:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _initialize(self) -> None:
        with self._lock, closing(self._connect()) as connection, connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS calls (
                    id TEXT PRIMARY KEY,
                    direction TEXT NOT NULL CHECK(direction IN ('inbound', 'outbound')),
                    provider TEXT NOT NULL,
                    status TEXT NOT NULL,
                    customer_phone TEXT NOT NULL DEFAULT '',
                    started_at TEXT NOT NULL,
                    ended_at TEXT,
                    customer_name TEXT NOT NULL DEFAULT '',
                    customer_address TEXT NOT NULL DEFAULT '',
                    customer_need TEXT NOT NULL DEFAULT '',
                    customer_notes TEXT NOT NULL DEFAULT '',
                    interest_status TEXT NOT NULL DEFAULT 'unknown'
                        CHECK(interest_status IN ('needs_consultation', 'no_need', 'unknown'))
                );
                CREATE TABLE IF NOT EXISTS transcripts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    call_id TEXT NOT NULL REFERENCES calls(id) ON DELETE CASCADE,
                    speaker TEXT NOT NULL CHECK(speaker IN ('customer', 'agent')),
                    text TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS outbound_call_requests (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    to_number TEXT NOT NULL,
                    from_number TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'queued',
                    call_sid TEXT NOT NULL DEFAULT '',
                    error TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_calls_started_at ON calls(started_at DESC);
                CREATE INDEX IF NOT EXISTS idx_transcripts_call_id ON transcripts(call_id, id);
                CREATE INDEX IF NOT EXISTS idx_outbound_requests_created_at
                    ON outbound_call_requests(created_at DESC);
                """
            )
            columns = {
                row["name"] for row in connection.execute("PRAGMA table_info(calls)").fetchall()
            }
            if "interest_status" not in columns:
                connection.execute(
                    "ALTER TABLE calls ADD COLUMN interest_status TEXT NOT NULL DEFAULT 'unknown'"
                )
            outbound_schema = connection.execute(
                """
                SELECT sql FROM sqlite_master
                WHERE type = 'table' AND name = 'outbound_call_requests'
                """
            ).fetchone()
            if outbound_schema and "CHECK(status IN ('queued', 'started', 'failed'))" in (
                outbound_schema["sql"] or ""
            ):
                connection.executescript(
                    """
                    ALTER TABLE outbound_call_requests RENAME TO outbound_call_requests_old;
                    CREATE TABLE outbound_call_requests (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        to_number TEXT NOT NULL,
                        from_number TEXT NOT NULL DEFAULT '',
                        status TEXT NOT NULL DEFAULT 'queued',
                        call_sid TEXT NOT NULL DEFAULT '',
                        error TEXT NOT NULL DEFAULT '',
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    );
                    INSERT INTO outbound_call_requests
                        (id, to_number, from_number, status, call_sid, error, created_at, updated_at)
                    SELECT id, to_number, from_number, status, call_sid, error, created_at, updated_at
                    FROM outbound_call_requests_old;
                    DROP TABLE outbound_call_requests_old;
                    CREATE INDEX IF NOT EXISTS idx_outbound_requests_created_at
                        ON outbound_call_requests(created_at DESC);
                    """
                )

    def create_outbound_request(
        self,
        to_number: str,
        from_number: str = "",
    ) -> dict[str, Any]:
        now = _now()
        with self._lock, closing(self._connect()) as connection, connection:
            cursor = connection.execute(
                """
                INSERT INTO outbound_call_requests
                    (to_number, from_number, status, created_at, updated_at)
                VALUES (?, ?, 'queued', ?, ?)
                """,
                (to_number.strip(), from_number.strip(), now, now),
            )
            request_id = int(cursor.lastrowid)
        return self.get_outbound_request(request_id) or {}

    def mark_outbound_request_started(self, request_id: int, call_sid: str = "") -> None:
        self._update_outbound_request(
            request_id,
            status="started",
            call_sid=call_sid,
            error="",
        )

    def mark_outbound_request_failed(self, request_id: int, error: str) -> None:
        self._update_outbound_request(
            request_id,
            status="failed",
            error=error,
        )

    def update_outbound_request_by_call_sid(self, call_sid: str, status: str) -> None:
        normalized_status = status.replace("-", "_")
        if normalized_status not in OUTBOUND_REQUEST_STATUSES:
            return
        with self._lock, closing(self._connect()) as connection, connection:
            connection.execute(
                """
                UPDATE outbound_call_requests
                SET status = ?, updated_at = ?
                WHERE call_sid = ?
                """,
                (normalized_status, _now(), call_sid),
            )

    def list_outbound_requests(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._lock, closing(self._connect()) as connection:
            rows = connection.execute(
                """
                SELECT * FROM outbound_call_requests
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (max(1, min(limit, 200)),),
            ).fetchall()
        return [self._outbound_request_summary(row) for row in rows]

    def get_outbound_request(self, request_id: int) -> dict[str, Any] | None:
        with self._lock, closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT * FROM outbound_call_requests WHERE id = ?",
                (request_id,),
            ).fetchone()
        return self._outbound_request_summary(row) if row else None

    def _update_outbound_request(
        self,
        request_id: int,
        *,
        status: str,
        call_sid: str | None = None,
        error: str | None = None,
    ) -> None:
        if status not in OUTBOUND_REQUEST_STATUSES:
            return
        assignments = ["status = ?", "updated_at = ?"]
        params: list[Any] = [status, _now()]
        if call_sid is not None:
            assignments.append("call_sid = ?")
            params.append(call_sid)
        if error is not None:
            assignments.append("error = ?")
            params.append(error)
        params.append(request_id)
        with self._lock, closing(self._connect()) as connection, connection:
            connection.execute(
                f"UPDATE outbound_call_requests SET {', '.join(assignments)} WHERE id = ?",
                params,
            )

    def start_call(
        self,
        call_id: str,
        direction: str,
        provider: str,
        customer_phone: str = "",
    ) -> None:
        normalized_direction = direction if direction in {"inbound", "outbound"} else "inbound"
        with self._lock, closing(self._connect()) as connection, connection:
            connection.execute(
                """
                INSERT INTO calls (id, direction, provider, status, customer_phone, started_at)
                VALUES (?, ?, ?, 'active', ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    direction=excluded.direction,
                    provider=excluded.provider,
                    status='active',
                    customer_phone=CASE
                        WHEN excluded.customer_phone <> '' THEN excluded.customer_phone
                        ELSE calls.customer_phone
                    END
                """,
                (call_id, normalized_direction, provider, customer_phone, _now()),
            )

    def add_transcript(self, call_id: str, speaker: str, text: str) -> None:
        clean_text = text.strip()
        if speaker not in {"customer", "agent"} or not clean_text:
            return
        with self._lock, closing(self._connect()) as connection, connection:
            connection.execute(
                "INSERT INTO transcripts (call_id, speaker, text, created_at) VALUES (?, ?, ?, ?)",
                (call_id, speaker, clean_text, _now()),
            )

    def finish_call(self, call_id: str) -> None:
        call = self.get_call(call_id)
        if not call:
            return
        extracted = extract_customer_info(call["transcript"])
        interest_status = classify_customer_interest(call["transcript"])
        phone = extracted["phone"] or call["customer"]["phone"]
        with self._lock, closing(self._connect()) as connection, connection:
            connection.execute(
                """
                UPDATE calls
                SET status='completed', ended_at=?, customer_name=?, customer_phone=?,
                    customer_address=?, customer_need=?, customer_notes=?, interest_status=?
                WHERE id=?
                """,
                (
                    _now(),
                    extracted["name"],
                    phone,
                    extracted["address"],
                    extracted["need"],
                    extracted["notes"],
                    interest_status,
                    call_id,
                ),
            )

    def list_calls(
        self,
        direction: str | None = None,
        query: str = "",
        interest_status: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if direction in {"inbound", "outbound"}:
            clauses.append("direction = ?")
            params.append(direction)
        if interest_status in INTEREST_STATUSES:
            clauses.append("interest_status = ?")
            params.append(interest_status)
        if query.strip():
            clauses.append(
                "(id LIKE ? OR customer_name LIKE ? OR customer_phone LIKE ? "
                "OR customer_address LIKE ? OR customer_need LIKE ?)"
            )
            needle = f"%{query.strip()}%"
            params.extend([needle] * 5)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(max(1, min(limit, 500)))
        with self._lock, closing(self._connect()) as connection:
            rows = connection.execute(
                f"SELECT * FROM calls {where} ORDER BY started_at DESC LIMIT ?",
                params,
            ).fetchall()
        return [self._call_summary(row) for row in rows]

    def get_call(self, call_id: str) -> dict[str, Any] | None:
        with self._lock, closing(self._connect()) as connection:
            row = connection.execute("SELECT * FROM calls WHERE id = ?", (call_id,)).fetchone()
            if not row:
                return None
            transcript_rows = connection.execute(
                "SELECT speaker, text, created_at FROM transcripts WHERE call_id = ? ORDER BY id",
                (call_id,),
            ).fetchall()
        result = self._call_summary(row)
        result["transcript"] = [dict(item) for item in transcript_rows]
        return result

    def sales_statistics(self) -> dict[str, Any]:
        with self._lock, closing(self._connect()) as connection:
            rows = connection.execute("SELECT * FROM calls").fetchall()
            transcript_rows = connection.execute(
                """
                SELECT call_id, COUNT(*) AS message_count
                FROM transcripts
                GROUP BY call_id
                """
            ).fetchall()

        calls = [self._call_summary(row) for row in rows]
        transcript_counts = {
            row["call_id"]: int(row["message_count"]) for row in transcript_rows
        }
        total_calls = len(calls)
        completed_calls = sum(1 for call in calls if call["status"] == "completed")
        active_calls = sum(1 for call in calls if call["status"] == "active")
        direction_counts = {"inbound": 0, "outbound": 0}
        completed_direction_counts = {"inbound": 0, "outbound": 0}
        interest_counts = {status: 0 for status in INTEREST_STATUSES}
        provider_counts: dict[str, int] = {}
        contacts_with_phone = 0
        contacts_with_need = 0
        total_duration = 0
        completed_with_duration = 0

        for call in calls:
            if call["direction"] in direction_counts:
                direction_counts[call["direction"]] += 1
            if call["interest_status"] in interest_counts:
                interest_counts[call["interest_status"]] += 1
            provider_counts[call["provider"]] = provider_counts.get(call["provider"], 0) + 1
            if call["customer"]["phone"]:
                contacts_with_phone += 1
            if call["customer"]["need"]:
                contacts_with_need += 1
            if call["status"] == "completed":
                if call["direction"] in completed_direction_counts:
                    completed_direction_counts[call["direction"]] += 1
                total_duration += call["duration_seconds"]
                completed_with_duration += 1

        total_transcript_messages = sum(transcript_counts.values())
        leads = interest_counts["needs_consultation"]
        return {
            "total_calls": total_calls,
            "active_calls": active_calls,
            "completed_calls": completed_calls,
            "direction_counts": direction_counts,
            "completed_direction_counts": completed_direction_counts,
            "interest_counts": interest_counts,
            "provider_counts": provider_counts,
            "contacts_with_phone": contacts_with_phone,
            "contacts_with_need": contacts_with_need,
            "total_transcript_messages": total_transcript_messages,
            "avg_duration_seconds": (
                round(total_duration / completed_with_duration)
                if completed_with_duration
                else 0
            ),
            "avg_messages_per_call": (
                round(total_transcript_messages / total_calls, 1) if total_calls else 0
            ),
            "lead_rate": round(leads / total_calls, 4) if total_calls else 0,
            "contact_capture_rate": (
                round(contacts_with_phone / total_calls, 4) if total_calls else 0
            ),
        }

    @staticmethod
    def _call_summary(row: sqlite3.Row) -> dict[str, Any]:
        ended_at = row["ended_at"]
        duration_seconds = 0
        if ended_at:
            started = datetime.fromisoformat(row["started_at"])
            ended = datetime.fromisoformat(ended_at)
            duration_seconds = max(0, int((ended - started).total_seconds()))
        return {
            "id": row["id"],
            "direction": row["direction"],
            "provider": row["provider"],
            "status": row["status"],
            "interest_status": row["interest_status"],
            "started_at": row["started_at"],
            "ended_at": ended_at,
            "duration_seconds": duration_seconds,
            "customer": {
                "name": row["customer_name"],
                "phone": row["customer_phone"],
                "address": row["customer_address"],
                "need": row["customer_need"],
                "notes": row["customer_notes"],
            },
        }

    @staticmethod
    def _outbound_request_summary(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "to_number": row["to_number"],
            "from_number": row["from_number"],
            "status": row["status"],
            "call_sid": row["call_sid"],
            "error": row["error"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }
