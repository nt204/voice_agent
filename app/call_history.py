import re
import sqlite3
import threading
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


CUSTOMER_FIELDS = ("name", "phone", "address", "need", "notes")
INTEREST_STATUSES = ("needs_consultation", "no_need", "unknown")


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
                CREATE INDEX IF NOT EXISTS idx_calls_started_at ON calls(started_at DESC);
                CREATE INDEX IF NOT EXISTS idx_transcripts_call_id ON transcripts(call_id, id);
                """
            )
            columns = {
                row["name"] for row in connection.execute("PRAGMA table_info(calls)").fetchall()
            }
            if "interest_status" not in columns:
                connection.execute(
                    "ALTER TABLE calls ADD COLUMN interest_status TEXT NOT NULL DEFAULT 'unknown'"
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
