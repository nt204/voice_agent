import threading
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, func, select, text
from sqlalchemy.engine import Connection

from app.call_history import (
    INTEREST_STATUSES,
    OUTBOUND_REQUEST_STATUSES,
    SQLiteCallHistoryStore,
    _now,
    analysis_table,
    calls_table,
    classify_customer_interest,
    extract_customer_info,
    metadata,
    orders_table,
    outbound_requests_table,
    transcripts_table,
)
from app.order_extraction import analyze_call_with_gemini
from app.sales_analysis import analyze_call


class SqlAlchemyCallHistoryStore:
    def __init__(self, database: str | Path) -> None:
        self.database_url, self.db_path = self._database_location(database)
        connect_args = {"check_same_thread": False, "timeout": 10} if self.database_url.startswith("sqlite") else {}
        self.engine = create_engine(
            self.database_url,
            pool_pre_ping=True,
            connect_args=connect_args,
        )
        self._lock = threading.RLock()
        self._initialize()

    @staticmethod
    def _database_location(database: str | Path) -> tuple[str, Path | None]:
        raw = str(database)
        if "://" in raw:
            return raw, None
        path = Path(database).resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        return f"sqlite:///{path.as_posix()}", path

    def _initialize(self) -> None:
        metadata.create_all(self.engine)
        with self.engine.begin() as connection:
            self._backfill_outbound_request_calls(connection)

    def _backfill_outbound_request_calls(self, connection: Connection) -> None:
        connection.execute(
            text(
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
                FROM outbound_call_requests AS request
                WHERE call_sid <> ''
                  AND status IN ('queued', 'started', 'completed', 'no_answer', 'busy', 'canceled', 'failed')
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
                """
            )
        )

    def migrate_from_sqlite(self, source_path: str | Path) -> dict[str, int]:
        source_path = Path(source_path)
        if not source_path.exists():
            return {}
        source = SqlAlchemyCallHistoryStore(source_path)
        with self._lock, self.engine.begin() as target_connection:
            has_data = target_connection.scalar(select(func.count()).select_from(calls_table))
            has_requests = target_connection.scalar(
                select(func.count()).select_from(outbound_requests_table)
            )
            if has_data or has_requests:
                return {}

            table_order = (
                calls_table,
                outbound_requests_table,
                transcripts_table,
                analysis_table,
                orders_table,
            )
            counts: dict[str, int] = {}
            with source.engine.connect() as source_connection:
                for table in table_order:
                    rows = [dict(row) for row in source_connection.execute(select(table)).mappings()]
                    if table in {outbound_requests_table, transcripts_table, orders_table}:
                        for row in rows:
                            row.pop("id", None)
                    if rows:
                        target_connection.execute(table.insert(), rows)
                    counts[table.name] = len(rows)
            return counts

    def create_outbound_request(
        self,
        to_number: str,
        from_number: str = "",
    ) -> dict[str, Any]:
        now = _now()
        with self._lock, self.engine.begin() as connection:
            result = connection.execute(
                outbound_requests_table.insert().values(
                    to_number=to_number.strip(),
                    from_number=from_number.strip(),
                    status="queued",
                    created_at=now,
                    updated_at=now,
                )
            )
            request_id = int(result.inserted_primary_key[0])
        return self.get_outbound_request(request_id) or {}

    def mark_outbound_request_started(self, request_id: int, call_sid: str = "") -> None:
        self._update_outbound_request(request_id, status="started", call_sid=call_sid, error="")
        request = self.get_outbound_request(request_id)
        if call_sid and request:
            self.update_outbound_request_by_call_sid(
                call_sid,
                "started",
                customer_phone=request["to_number"],
                started_at=request["created_at"],
            )

    def mark_outbound_request_failed(self, request_id: int, error: str) -> None:
        self._update_outbound_request(request_id, status="failed", error=error)

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
        with self._lock, self.engine.begin() as connection:
            connection.execute(
                text(
                    """
                    UPDATE outbound_call_requests
                    SET status = :status, updated_at = :updated_at
                    WHERE call_sid = :call_sid
                    """
                ),
                {"status": normalized_status, "updated_at": _now(), "call_sid": call_sid},
            )
            if call_status:
                connection.execute(
                    text(
                        """
                        INSERT INTO calls (
                            id, direction, provider, status, customer_phone, started_at, ended_at
                        )
                        VALUES (
                            :call_sid, 'outbound', 'telnyx', :status, :customer_phone,
                            :started_at, :ended_at
                        )
                        ON CONFLICT(id) DO UPDATE SET
                            status=excluded.status,
                            started_at=CASE
                                WHEN :replace_started_at THEN excluded.started_at
                                ELSE calls.started_at
                            END,
                            customer_phone=CASE
                                WHEN excluded.customer_phone <> '' THEN excluded.customer_phone
                                ELSE calls.customer_phone
                            END,
                            ended_at=CASE
                                WHEN excluded.ended_at IS NOT NULL THEN excluded.ended_at
                                ELSE calls.ended_at
                            END
                        """
                    ),
                    {
                        "call_sid": call_sid,
                        "status": call_status,
                        "customer_phone": customer_phone.strip(),
                        "started_at": started_at.strip() or _now(),
                        "replace_started_at": bool(started_at.strip()),
                        "ended_at": ended_at.strip() or None,
                    },
                )

    def list_outbound_requests(self, limit: int = 50) -> list[dict[str, Any]]:
        with self.engine.connect() as connection:
            rows = connection.execute(
                select(outbound_requests_table)
                .order_by(outbound_requests_table.c.created_at.desc())
                .limit(max(1, min(limit, 200)))
            ).mappings().all()
        return [self._outbound_request_summary(row) for row in rows]

    def get_outbound_request(self, request_id: int) -> dict[str, Any] | None:
        with self.engine.connect() as connection:
            row = connection.execute(
                select(outbound_requests_table).where(outbound_requests_table.c.id == request_id)
            ).mappings().first()
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
        values: dict[str, Any] = {"status": status, "updated_at": _now()}
        if call_sid is not None:
            values["call_sid"] = call_sid
        if error is not None:
            values["error"] = error
        with self._lock, self.engine.begin() as connection:
            connection.execute(
                outbound_requests_table.update()
                .where(outbound_requests_table.c.id == request_id)
                .values(**values)
            )

    @staticmethod
    def _call_status_from_outbound_status(status: str) -> str | None:
        return SQLiteCallHistoryStore._call_status_from_outbound_status(status)

    def start_call(
        self,
        call_id: str,
        direction: str,
        provider: str,
        customer_phone: str = "",
    ) -> None:
        normalized_direction = direction if direction in {"inbound", "outbound"} else "inbound"
        with self._lock, self.engine.begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO calls (id, direction, provider, status, customer_phone, started_at)
                    VALUES (:id, :direction, :provider, 'active', :customer_phone, :started_at)
                    ON CONFLICT(id) DO UPDATE SET
                        direction=excluded.direction,
                        provider=excluded.provider,
                        status='active',
                        customer_phone=CASE
                            WHEN excluded.customer_phone <> '' THEN excluded.customer_phone
                            ELSE calls.customer_phone
                        END
                    """
                ),
                {
                    "id": call_id,
                    "direction": normalized_direction,
                    "provider": provider,
                    "customer_phone": customer_phone,
                    "started_at": _now(),
                },
            )

    def add_transcript(self, call_id: str, speaker: str, text_value: str) -> None:
        clean_text = text_value.strip()
        if speaker not in {"customer", "agent"} or not clean_text:
            return
        with self._lock, self.engine.begin() as connection:
            connection.execute(
                transcripts_table.insert().values(
                    call_id=call_id,
                    speaker=speaker,
                    text=clean_text,
                    created_at=_now(),
                )
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
        phone = sales_customer["phone"] or extracted["phone"] or call["customer"]["phone"]
        address = extracted["address"] or sales_customer["address"]
        need = extracted["need"] or sales_customer["need"]
        with self._lock, self.engine.begin() as connection:
            connection.execute(
                calls_table.update()
                .where(calls_table.c.id == call_id)
                .values(
                    status="completed",
                    ended_at=_now(),
                    customer_name=extracted["name"],
                    customer_phone=phone,
                    customer_address=address,
                    customer_need=need,
                    customer_notes=extracted["notes"],
                    interest_status=interest_status,
                )
            )
            self._save_analysis(connection, call_id, sales_result)

    def list_calls(
        self,
        direction: str | None = None,
        query: str = "",
        interest_status: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        statement = select(calls_table)
        if direction in {"inbound", "outbound"}:
            statement = statement.where(calls_table.c.direction == direction)
        if interest_status in INTEREST_STATUSES:
            statement = statement.where(calls_table.c.interest_status == interest_status)
        if query.strip():
            needle = f"%{query.strip()}%"
            statement = statement.where(
                calls_table.c.id.like(needle)
                | calls_table.c.customer_name.like(needle)
                | calls_table.c.customer_phone.like(needle)
                | calls_table.c.customer_address.like(needle)
                | calls_table.c.customer_need.like(needle)
            )
        statement = statement.order_by(calls_table.c.started_at.desc()).limit(max(1, min(limit, 500)))
        with self.engine.connect() as connection:
            rows = connection.execute(statement).mappings().all()
        return [self._call_summary(row) for row in rows]

    def get_call(self, call_id: str) -> dict[str, Any] | None:
        with self.engine.connect() as connection:
            row = connection.execute(
                select(calls_table).where(calls_table.c.id == call_id)
            ).mappings().first()
            if not row:
                return None
            transcript_rows = connection.execute(
                select(
                    transcripts_table.c.speaker,
                    transcripts_table.c.text,
                    transcripts_table.c.created_at,
                )
                .where(transcripts_table.c.call_id == call_id)
                .order_by(transcripts_table.c.id)
            ).mappings().all()
            analysis_row = connection.execute(
                select(analysis_table).where(analysis_table.c.call_id == call_id)
            ).mappings().first()
            order_row = connection.execute(
                select(orders_table)
                .where(orders_table.c.call_id == call_id)
                .order_by(orders_table.c.id.desc())
                .limit(1)
            ).mappings().first()
        result = self._call_summary(row)
        result["transcript"] = [dict(item) for item in transcript_rows]
        result["analysis"] = self._analysis_summary(analysis_row) if analysis_row else None
        result["order"] = self._order_summary(order_row) if order_row else None
        return result

    def list_orders(self, limit: int = 100) -> list[dict[str, Any]]:
        statement = (
            select(
                orders_table,
                calls_table.c.direction,
                calls_table.c.provider,
                calls_table.c.customer_need,
                calls_table.c.started_at.label("call_started_at"),
            )
            .join(calls_table, calls_table.c.id == orders_table.c.call_id)
            .order_by(orders_table.c.created_at.desc(), orders_table.c.id.desc())
            .limit(max(1, min(limit, 500)))
        )
        with self.engine.connect() as connection:
            rows = connection.execute(statement).mappings().all()
        return [self._order_summary(row) for row in rows]

    def _save_analysis(
        self,
        connection: Connection,
        call_id: str,
        result: dict[str, Any],
    ) -> None:
        now = _now()
        analysis = result["analysis"]
        customer = result["customer"]
        connection.execute(
            text(
                """
                INSERT INTO call_analysis (
                    call_id, intent_status, sentiment, urgency, objection, summary,
                    next_action, confidence, gender, gender_confidence, age_range,
                    age_confidence, created_at, updated_at
                )
                VALUES (
                    :call_id, :intent_status, :sentiment, :urgency, :objection, :summary,
                    :next_action, :confidence, :gender, :gender_confidence, :age_range,
                    :age_confidence, :created_at, :updated_at
                )
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
                """
            ),
            {
                "call_id": call_id,
                **analysis,
                "gender": customer["gender"],
                "gender_confidence": customer["gender_confidence"],
                "age_range": customer["age_range"],
                "age_confidence": customer["age_confidence"],
                "created_at": now,
                "updated_at": now,
            },
        )
        connection.execute(orders_table.delete().where(orders_table.c.call_id == call_id))
        order = result.get("order")
        if not order:
            return
        connection.execute(
            orders_table.insert().values(
                call_id=call_id,
                customer_phone=order["customer_phone"],
                customer_name=order["customer_name"],
                shipping_address=order["shipping_address"],
                product_name=order["product_name"],
                quantity=order["quantity"],
                unit_price=order["unit_price"],
                total_price=order["total_price"],
                status=order["status"],
                missing_fields=",".join(order["missing_fields"]),
                confidence=order["confidence"],
                created_at=now,
                updated_at=now,
            )
        )

    def sales_statistics(self) -> dict[str, Any]:
        with self.engine.connect() as connection:
            rows = connection.execute(select(calls_table)).mappings().all()
            transcript_rows = connection.execute(
                select(
                    transcripts_table.c.call_id,
                    func.count().label("message_count"),
                ).group_by(transcripts_table.c.call_id)
            ).mappings().all()
        calls = [self._call_summary(row) for row in rows]
        transcript_counts = {
            row["call_id"]: int(row["message_count"]) for row in transcript_rows
        }
        total_calls = len(calls)
        completed_calls = sum(call["status"] == "completed" for call in calls)
        active_calls = sum(call["status"] == "active" for call in calls)
        direction_counts = {"inbound": 0, "outbound": 0}
        completed_direction_counts = {"inbound": 0, "outbound": 0}
        interest_counts = {status: 0 for status in INTEREST_STATUSES}
        provider_counts: dict[str, int] = {}
        contacts_with_phone = 0
        contacts_with_need = 0
        total_duration = 0
        completed_with_duration = 0
        for call in calls:
            direction_counts[call["direction"]] += 1
            interest_counts[call["interest_status"]] += 1
            provider_counts[call["provider"]] = provider_counts.get(call["provider"], 0) + 1
            contacts_with_phone += bool(call["customer"]["phone"])
            contacts_with_need += bool(call["customer"]["need"])
            if call["status"] == "completed":
                completed_direction_counts[call["direction"]] += 1
                total_duration += call["duration_seconds"]
                completed_with_duration += 1
        total_messages = sum(transcript_counts.values())
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
            "total_transcript_messages": total_messages,
            "avg_duration_seconds": round(total_duration / completed_with_duration) if completed_with_duration else 0,
            "avg_messages_per_call": round(total_messages / total_calls, 1) if total_calls else 0,
            "lead_rate": round(leads / total_calls, 4) if total_calls else 0,
            "contact_capture_rate": round(contacts_with_phone / total_calls, 4) if total_calls else 0,
        }

    _call_summary = staticmethod(SQLiteCallHistoryStore._call_summary)
    _outbound_request_summary = staticmethod(SQLiteCallHistoryStore._outbound_request_summary)
    _analysis_summary = staticmethod(SQLiteCallHistoryStore._analysis_summary)
    _order_summary = staticmethod(SQLiteCallHistoryStore._order_summary)
