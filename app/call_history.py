import re
import sqlite3
import threading
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from sqlalchemy import (
    CheckConstraint,
    Column,
    Float,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    create_engine,
    text as sql_text,
)
from sqlalchemy.engine import Connection, Engine

from app.order_extraction import analyze_call_with_gemini
from app.sales_analysis import analyze_call


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

metadata = MetaData()
calls_table = Table(
    "calls",
    metadata,
    Column("id", Text, primary_key=True),
    Column("direction", String(20), nullable=False),
    Column("provider", String(50), nullable=False),
    Column("status", String(30), nullable=False),
    Column("customer_phone", Text, nullable=False, server_default=""),
    Column("started_at", Text, nullable=False),
    Column("ended_at", Text),
    Column("customer_name", Text, nullable=False, server_default=""),
    Column("customer_address", Text, nullable=False, server_default=""),
    Column("customer_need", Text, nullable=False, server_default=""),
    Column("customer_notes", Text, nullable=False, server_default=""),
    Column("interest_status", String(30), nullable=False, server_default="unknown"),
    CheckConstraint("direction IN ('inbound', 'outbound')", name="ck_calls_direction"),
    CheckConstraint(
        "interest_status IN ('needs_consultation', 'no_need', 'unknown')",
        name="ck_calls_interest_status",
    ),
)
transcripts_table = Table(
    "transcripts",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("call_id", Text, ForeignKey("calls.id", ondelete="CASCADE"), nullable=False),
    Column("speaker", String(20), nullable=False),
    Column("text", Text, nullable=False),
    Column("created_at", Text, nullable=False),
    CheckConstraint("speaker IN ('customer', 'agent')", name="ck_transcripts_speaker"),
)
outbound_requests_table = Table(
    "outbound_call_requests",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("to_number", Text, nullable=False),
    Column("from_number", Text, nullable=False, server_default=""),
    Column("status", String(30), nullable=False, server_default="queued"),
    Column("call_sid", Text, nullable=False, server_default=""),
    Column("error", Text, nullable=False, server_default=""),
    Column("created_at", Text, nullable=False),
    Column("updated_at", Text, nullable=False),
)
analysis_table = Table(
    "call_analysis",
    metadata,
    Column("call_id", Text, ForeignKey("calls.id", ondelete="CASCADE"), primary_key=True),
    Column("intent_status", String(30), nullable=False, server_default="unknown"),
    Column("sentiment", String(30), nullable=False, server_default="unknown"),
    Column("urgency", String(30), nullable=False, server_default="unknown"),
    Column("objection", String(30), nullable=False, server_default="unknown"),
    Column("summary", Text, nullable=False, server_default=""),
    Column("next_action", Text, nullable=False, server_default=""),
    Column("confidence", Float, nullable=False, server_default="0"),
    Column("gender", String(30), nullable=False, server_default="unknown"),
    Column("gender_confidence", Float, nullable=False, server_default="0"),
    Column("age_range", String(30), nullable=False, server_default="unknown"),
    Column("age_confidence", Float, nullable=False, server_default="0"),
    Column("created_at", Text, nullable=False),
    Column("updated_at", Text, nullable=False),
)
orders_table = Table(
    "orders",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("call_id", Text, ForeignKey("calls.id", ondelete="CASCADE"), nullable=False),
    Column("customer_phone", Text, nullable=False, server_default=""),
    Column("customer_name", Text, nullable=False, server_default=""),
    Column("shipping_address", Text, nullable=False, server_default=""),
    Column("product_name", Text, nullable=False, server_default=""),
    Column("quantity", Integer, nullable=False, server_default="0"),
    Column("unit_price", Integer, nullable=False, server_default="0"),
    Column("total_price", Integer, nullable=False, server_default="0"),
    Column("status", String(30), nullable=False, server_default="draft"),
    Column("missing_fields", Text, nullable=False, server_default=""),
    Column("confidence", Float, nullable=False, server_default="0"),
    Column("created_at", Text, nullable=False),
    Column("updated_at", Text, nullable=False),
)
Index("idx_calls_started_at", calls_table.c.started_at)
Index("idx_transcripts_call_id", transcripts_table.c.call_id, transcripts_table.c.id)
Index("idx_outbound_requests_created_at", outbound_requests_table.c.created_at)
Index("idx_orders_call_id", orders_table.c.call_id)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _parse_iso_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _clean(value: str) -> str:
    cleaned = value.strip(" \t\r\n,.;:-။၊")
    return re.sub(r"\s*(?:ပါရှင်|ပါတယ်|ပါ)$", "", cleaned).rstrip()


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

    if any(
        phrase in customer_text
        for phrase in (
            "မလိုချင်",
            "မဝယ်ချင်",
            "မလိုအပ်",
            "စိတ်မဝင်စား",
        )
    ):
        return "no_need"
    if any(
        phrase in customer_text
        for phrase in (
            "စိတ်ဝင်စား",
            "သိချင်",
            "မေးချင်",
            "အကြံ",
            "ဝယ်ချင်",
            "ဝယ်မယ်",
            "ယူမယ်",
            "မှာမယ်",
            "အော်ဒါ",
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
    if not result["phone"]:
        match = re.search(r"(?:ဖုန်းနံပါတ်|ဖုန်း)?\s*(\+?[\d၀-၉][\d၀-၉ .-]{7,}[\d၀-၉])", customer_text)
        if match:
            result["phone"] = _clean(match.group(1)).translate(str.maketrans("၀၁၂၃၄၅၆၇၈၉", "0123456789"))
    if not result["address"]:
        match = re.search(r"လိပ်စာ\s*(?:က|မှာ|:)?\s*(.+?)(?=[။;]|\s*(?:ဖုန်း|ဝယ်ချင်|လိုချင်|မှာမယ်)|$)", customer_text)
        if match:
            result["address"] = _clean(match.group(1))
    return result


class SQLiteCallHistoryStore:
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
                CREATE TABLE IF NOT EXISTS call_analysis (
                    call_id TEXT PRIMARY KEY REFERENCES calls(id) ON DELETE CASCADE,
                    intent_status TEXT NOT NULL DEFAULT 'unknown',
                    sentiment TEXT NOT NULL DEFAULT 'unknown',
                    urgency TEXT NOT NULL DEFAULT 'unknown',
                    objection TEXT NOT NULL DEFAULT 'unknown',
                    summary TEXT NOT NULL DEFAULT '',
                    next_action TEXT NOT NULL DEFAULT '',
                    confidence REAL NOT NULL DEFAULT 0,
                    gender TEXT NOT NULL DEFAULT 'unknown',
                    gender_confidence REAL NOT NULL DEFAULT 0,
                    age_range TEXT NOT NULL DEFAULT 'unknown',
                    age_confidence REAL NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS orders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    call_id TEXT NOT NULL REFERENCES calls(id) ON DELETE CASCADE,
                    customer_phone TEXT NOT NULL DEFAULT '',
                    customer_name TEXT NOT NULL DEFAULT '',
                    shipping_address TEXT NOT NULL DEFAULT '',
                    product_name TEXT NOT NULL DEFAULT '',
                    quantity INTEGER NOT NULL DEFAULT 0,
                    unit_price INTEGER NOT NULL DEFAULT 0,
                    total_price INTEGER NOT NULL DEFAULT 0,
                    status TEXT NOT NULL DEFAULT 'draft',
                    missing_fields TEXT NOT NULL DEFAULT '',
                    confidence REAL NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_calls_started_at ON calls(started_at DESC);
                CREATE INDEX IF NOT EXISTS idx_transcripts_call_id ON transcripts(call_id, id);
                CREATE INDEX IF NOT EXISTS idx_outbound_requests_created_at
                    ON outbound_call_requests(created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_orders_call_id ON orders(call_id);
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
            self._backfill_outbound_request_calls(connection)

    def _backfill_outbound_request_calls(self, connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            INSERT INTO calls (
                id, direction, provider, status, customer_phone, started_at, ended_at
            )
            SELECT
                call_sid,
                'outbound',
                'telnyx',
                CASE
                    WHEN status IN ('queued', 'started') THEN 'active'
                    WHEN status = 'completed' THEN 'completed'
                    ELSE 'failed'
                END,
                to_number,
                created_at,
                CASE
                    WHEN status IN ('completed', 'no_answer', 'busy', 'canceled', 'failed')
                    THEN updated_at
                    ELSE NULL
                END
            FROM outbound_call_requests
            WHERE call_sid <> ''
              AND status IN ('queued', 'started', 'completed', 'no_answer', 'busy', 'canceled', 'failed')
              AND NOT EXISTS (
                  SELECT 1 FROM calls WHERE calls.id = outbound_call_requests.call_sid
              )
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

    def update_outbound_request_by_call_sid(
        self,
        call_sid: str,
        status: str,
        customer_phone: str = "",
        started_at: str = "",
        ended_at: str = "",
    ) -> None:
        normalized_status = status.replace("-", "_")
        if normalized_status not in OUTBOUND_REQUEST_STATUSES:
            return
        call_status = self._call_status_from_outbound_status(normalized_status)
        with self._lock, closing(self._connect()) as connection, connection:
            connection.execute(
                """
                UPDATE outbound_call_requests
                SET status = ?, updated_at = ?
                WHERE call_sid = ?
                """,
                (normalized_status, _now(), call_sid),
            )
            if call_status:
                connection.execute(
                    """
                    INSERT INTO calls (
                        id, direction, provider, status, customer_phone, started_at, ended_at
                    )
                    VALUES (?, 'outbound', 'telnyx', ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        status=excluded.status,
                        customer_phone=CASE
                            WHEN excluded.customer_phone <> '' THEN excluded.customer_phone
                            ELSE calls.customer_phone
                        END,
                        ended_at=CASE
                            WHEN excluded.ended_at IS NOT NULL THEN excluded.ended_at
                            ELSE calls.ended_at
                        END
                    """,
                    (
                        call_sid,
                        call_status,
                        customer_phone.strip(),
                        started_at.strip() or _now(),
                        ended_at.strip() or None,
                    ),
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

    @staticmethod
    def _call_status_from_outbound_status(status: str) -> str | None:
        if status in {"started", "queued"}:
            return "active"
        if status == "completed":
            return "completed"
        if status in {"no_answer", "busy", "canceled", "failed"}:
            return "failed"
        return None

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

    def update_customer_transcript_by_index(
        self, call_id: str, customer_turn_index: int, new_text: str
    ) -> None:
        clean_text = new_text.strip()
        if not clean_text:
            return
        with self._lock, closing(self._connect()) as connection, connection:
            cursor = connection.execute(
                """
                UPDATE transcripts
                SET text = ?
                WHERE id = (
                    SELECT id FROM transcripts
                    WHERE call_id = ? AND speaker = 'customer'
                    ORDER BY id ASC
                    LIMIT 1 OFFSET ?
                )
                """,
                (clean_text, call_id, customer_turn_index),
            )
            if cursor.rowcount == 0:
                connection.execute(
                    "INSERT INTO transcripts (call_id, speaker, text, created_at) VALUES (?, 'customer', ?, ?)",
                    (call_id, clean_text, _now()),
                )

    def finish_call(self, call_id: str) -> None:
        call = self.get_call(call_id)
        if not call:
            return
        extracted = extract_customer_info(call["transcript"])
        interest_status = classify_customer_interest(call["transcript"])
        fallback_phone = call["customer"]["phone"]
        sales_result = analyze_call(call["transcript"], fallback_phone=fallback_phone)
        sales_result = analyze_call_with_gemini(
            call["transcript"],
            fallback_phone=fallback_phone,
            fallback_result=sales_result,
        )
        sales_customer = sales_result["customer"]
        phone = extracted["phone"] or call["customer"]["phone"]
        phone = sales_customer["phone"] or phone
        address = extracted["address"] or sales_customer["address"]
        need = extracted["need"] or sales_customer["need"]
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
                    address,
                    need,
                    extracted["notes"],
                    interest_status,
                    call_id,
                ),
            )
            self._save_analysis(connection, call_id, sales_result)

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
            analysis_row = connection.execute(
                "SELECT * FROM call_analysis WHERE call_id = ?",
                (call_id,),
            ).fetchone()
            order_row = connection.execute(
                "SELECT * FROM orders WHERE call_id = ? ORDER BY id DESC LIMIT 1",
                (call_id,),
            ).fetchone()
        result = self._call_summary(row)
        result["transcript"] = [dict(item) for item in transcript_rows]
        result["analysis"] = self._analysis_summary(analysis_row) if analysis_row else None
        result["order"] = self._order_summary(order_row) if order_row else None
        return result

    def list_orders(self, limit: int = 100) -> list[dict[str, Any]]:
        with self._lock, closing(self._connect()) as connection:
            rows = connection.execute(
                """
                SELECT
                    orders.*,
                    calls.direction,
                    calls.provider,
                    calls.customer_need,
                    calls.started_at AS call_started_at
                FROM orders
                JOIN calls ON calls.id = orders.call_id
                ORDER BY orders.created_at DESC, orders.id DESC
                LIMIT ?
                """,
                (max(1, min(limit, 500)),),
            ).fetchall()
        return [self._order_summary(row) for row in rows]

    def _save_analysis(
        self,
        connection: sqlite3.Connection,
        call_id: str,
        result: dict[str, Any],
    ) -> None:
        now = _now()
        analysis = result["analysis"]
        customer = result["customer"]
        gender = customer.get("gender", "unknown")
        gender_confidence = customer.get("gender_confidence", 0.0)
        age_range = customer.get("age_range", "unknown")
        age_confidence = customer.get("age_confidence", 0.0)
        connection.execute(
            """
            INSERT INTO call_analysis (
                call_id, intent_status, sentiment, urgency, objection, summary,
                next_action, confidence, gender, gender_confidence, age_range,
                age_confidence, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(call_id) DO UPDATE SET
                intent_status=excluded.intent_status,
                sentiment=excluded.sentiment,
                urgency=excluded.urgency,
                objection=excluded.objection,
                summary=excluded.summary,
                next_action=excluded.next_action,
                confidence=excluded.confidence,
                gender=excluded.gender,
                gender_confidence=excluded.gender_confidence,
                age_range=excluded.age_range,
                age_confidence=excluded.age_confidence,
                updated_at=excluded.updated_at
            """,
            (
                call_id,
                analysis["intent_status"],
                analysis["sentiment"],
                analysis["urgency"],
                analysis["objection"],
                analysis["summary"],
                analysis["next_action"],
                analysis["confidence"],
                gender,
                gender_confidence,
                age_range,
                age_confidence,
                now,
                now,
            ),
        )

        connection.execute("DELETE FROM orders WHERE call_id = ?", (call_id,))
        order = result.get("order")
        if not order:
            return
        connection.execute(
            """
            INSERT INTO orders (
                call_id, customer_phone, customer_name, shipping_address,
                product_name, quantity, unit_price, total_price, status,
                missing_fields, confidence, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                call_id,
                order["customer_phone"],
                order["customer_name"],
                order["shipping_address"],
                order["product_name"],
                order["quantity"],
                order["unit_price"],
                order["total_price"],
                order["status"],
                ",".join(order["missing_fields"]),
                order["confidence"],
                now,
                now,
            ),
        )

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
            started = _parse_iso_datetime(row["started_at"])
            ended = _parse_iso_datetime(ended_at)
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

    @staticmethod
    def _analysis_summary(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "intent_status": row["intent_status"],
            "sentiment": row["sentiment"],
            "urgency": row["urgency"],
            "objection": row["objection"],
            "summary": row["summary"],
            "next_action": row["next_action"],
            "confidence": row["confidence"],
            "gender": row["gender"],
            "gender_confidence": row["gender_confidence"],
            "age_range": row["age_range"],
            "age_confidence": row["age_confidence"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    @staticmethod
    def _order_summary(row: sqlite3.Row) -> dict[str, Any]:
        missing_fields = [
            field for field in row["missing_fields"].split(",") if field
        ]
        result = {
            "id": row["id"],
            "call_id": row["call_id"],
            "customer_phone": row["customer_phone"],
            "customer_name": row["customer_name"],
            "shipping_address": row["shipping_address"],
            "product_name": row["product_name"],
            "quantity": row["quantity"],
            "unit_price": row["unit_price"],
            "total_price": row["total_price"],
            "status": row["status"],
            "missing_fields": missing_fields,
            "confidence": row["confidence"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }
        keys = set(row.keys())
        if "direction" in keys:
            result["call"] = {
                "direction": row["direction"],
                "provider": row["provider"],
                "need": row["customer_need"],
                "started_at": row["call_started_at"],
            }
        return result


from app.sql_call_history import SqlAlchemyCallHistoryStore as CallHistoryStore
